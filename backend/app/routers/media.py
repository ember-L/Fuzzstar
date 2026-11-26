from datetime import timedelta
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Path, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import consented_user, owned_pet
from app.core.errors import APIError
from app.core.security import utcnow
from app.models import MediaUpload, Pet, User
from app.services.media import (
    AUDIO_FORMATS,
    DOWNLOAD_SECONDS,
    FORMATS,
    MAX_AUDIO_BYTES,
    MAX_PHOTO_BYTES,
    MAX_VIDEO_BYTES,
    UPLOAD_SECONDS,
    VIDEO_FORMATS,
    LocalPhotoStorage,
    storage_unavailable,
)

router = APIRouter(prefix='/api/v1/media')


class PresignPhoto(BaseModel):
    model_config = ConfigDict(extra='forbid')

    pet_id: int = Field(strict=True, gt=0, le=2147483647)
    kind: Literal['photo', 'video', 'audio'] = 'photo'
    content_type: str = Field(max_length=64)
    size_bytes: int = Field(strict=True)


def local_origin(request: Request, storage) -> str | None:
    """本地存储时用客户端本次请求的 host 回指文件地址。

    模拟器（10.0.2.2）、局域网手机、localhost 都能访问自己正在使用的地址，
    避免配置里的 SERVER_HOST 与客户端实际可达地址不一致导致上传/下载失败。
    """
    if not isinstance(storage, LocalPhotoStorage):
        return None
    return str(request.base_url).rstrip('/')


@router.post('/presign', status_code=201)
def presign_photo(
    data: PresignPhoto,
    request: Request,
    response: Response,
    user: User = Depends(consented_user),
    db: Session = Depends(get_db),
):
    owned_pet(data.pet_id, user, db)
    if data.kind == 'video':
        if data.content_type not in VIDEO_FORMATS or not 0 < data.size_bytes <= MAX_VIDEO_BYTES:
            raise APIError(422, 'MEDIA_INVALID', '仅支持 50 MiB 以内的 MP4 或 MOV 视频')
    elif data.kind == 'audio':
        if data.content_type not in AUDIO_FORMATS or not 0 < data.size_bytes <= MAX_AUDIO_BYTES:
            raise APIError(422, 'MEDIA_INVALID', '仅支持 10 MiB 以内的 M4A、MP3、WAV 或 WebM 音频')
    elif data.content_type not in FORMATS or not 0 < data.size_bytes <= MAX_PHOTO_BYTES:
        raise APIError(422, 'MEDIA_INVALID', '仅支持 10 MiB 以内的 JPG、PNG 或 HEIC 照片')
    storage = request.app.state.photo_storage
    if storage is None:
        raise storage_unavailable()
    photo = MediaUpload(id=uuid4().hex, **data.model_dump(), expires_at=utcnow() + timedelta(seconds=UPLOAD_SECONDS))
    upload = storage.presign(photo)
    origin = local_origin(request, storage)
    if origin:
        upload['url'] = f'{origin}/api/v1/media/local-upload/{photo.id}'
    db.add(photo)
    db.commit()
    response.headers['Cache-Control'] = 'no-store'
    return {'media_id': photo.id, 'expires_in': UPLOAD_SECONDS, 'upload': upload}


def owned_photo(
    media_id: str = Path(pattern=r'^[0-9a-f]{32}$'), user: User = Depends(consented_user), db: Session = Depends(get_db)
):
    photo = db.scalar(
        select(MediaUpload)
        .join(Pet, Pet.id == MediaUpload.pet_id)
        .where(
            MediaUpload.id == media_id,
            Pet.user_id == user.id,
            Pet.status == 'active',
        )
    )
    if photo is None:
        raise APIError(404, 'NOT_FOUND', '未找到照片上传记录')
    return photo


@router.post('/{media_id}/complete')
def complete_photo(
    request: Request, response: Response, photo: MediaUpload = Depends(owned_photo), db: Session = Depends(get_db)
):
    media_id = photo.id
    if photo.version_id is None:
        if photo.expires_at <= utcnow():
            raise APIError(410, 'MEDIA_EXPIRED', '上传已过期，请重新申请')
        storage = request.app.state.photo_storage
        if storage is None:
            raise storage_unavailable()
        version = storage.verify(photo)
        if photo.expires_at <= utcnow():
            raise APIError(410, 'MEDIA_EXPIRED', '上传已过期，请重新申请')
        # First successful verification wins, even if the signed POST is reused.
        db.execute(
            update(MediaUpload)
            .where(MediaUpload.id == media_id, MediaUpload.version_id.is_(None))
            .values(version_id=version)
        )
        db.commit()
    response.headers['Cache-Control'] = 'no-store'
    return {'media_id': media_id, 'status': 'verified'}


@router.get('/{media_id}')
def get_photo(request: Request, response: Response, photo: MediaUpload = Depends(owned_photo)):
    if photo.version_id is None:
        raise APIError(409, 'MEDIA_NOT_VERIFIED', '请先上传并确认照片')
    storage = request.app.state.photo_storage
    if storage is None:
        raise storage_unavailable()
    response.headers['Cache-Control'] = 'no-store'
    url = storage.download_url(photo)
    origin = local_origin(request, storage)
    if origin:
        url = f'{origin}/api/v1/media/local-file/{photo.id}'
    return {'download_url': url, 'expires_in': DOWNLOAD_SECONDS}


# ── 本地存储端点（开发环境无 S3 时降级）────────────────────────────────
# 前端直传不带 Authorization（与 S3 直传一致），故这两个端点无鉴权；
# 安全性由 media_id 的 128 位随机串保证，且 complete / 下载均要求 version_id 已验证。


@router.post('/local-upload/{media_id}')
async def local_upload(media_id: str, request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    storage = request.app.state.photo_storage
    if not isinstance(storage, LocalPhotoStorage):
        raise storage_unavailable()
    photo = db.get(MediaUpload, media_id)
    if photo is None:
        raise APIError(404, 'NOT_FOUND', '未找到上传记录')
    if photo.expires_at <= utcnow():
        raise APIError(410, 'MEDIA_EXPIRED', '上传已过期，请重新申请')
    storage.save(media_id, await file.read())
    return {'ok': True}


@router.get('/local-file/{media_id}')
def local_file(media_id: str, request: Request, db: Session = Depends(get_db)):
    storage = request.app.state.photo_storage
    if not isinstance(storage, LocalPhotoStorage):
        raise storage_unavailable()
    photo = db.get(MediaUpload, media_id)
    if photo is None or photo.version_id is None:
        raise APIError(404, 'NOT_FOUND', '未找到媒体')
    path = storage.path_for(media_id)
    if not path.exists():
        raise APIError(404, 'NOT_FOUND', '文件不存在')
    return FileResponse(path, media_type=photo.content_type)
