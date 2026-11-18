from datetime import timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, Path, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth import APIError, get_db, utcnow
from app.media import DOWNLOAD_SECONDS, FORMATS, MAX_PHOTO_BYTES, UPLOAD_SECONDS, storage_unavailable
from app.models import MediaUpload, Pet, User
from app.pet_api import consented_user, owned_pet

router = APIRouter(prefix='/api/v1/media')


class PresignPhoto(BaseModel):
    model_config = ConfigDict(extra='forbid')

    pet_id: int = Field(strict=True, gt=0, le=2147483647)
    content_type: str = Field(max_length=64)
    size_bytes: int = Field(strict=True)


@router.post('/presign', status_code=201)
def presign_photo(data: PresignPhoto, request: Request, response: Response,
                  user: User = Depends(consented_user), db: Session = Depends(get_db)):
    owned_pet(data.pet_id, user, db)
    if data.content_type not in FORMATS or not 0 < data.size_bytes <= MAX_PHOTO_BYTES:
        raise APIError(422, 'MEDIA_INVALID', '仅支持 10 MiB 以内的 JPG、PNG 或 HEIC 照片')
    storage = request.app.state.photo_storage
    if storage is None:
        raise storage_unavailable()
    photo = MediaUpload(id=uuid4().hex, **data.model_dump(), expires_at=utcnow() + timedelta(seconds=UPLOAD_SECONDS))
    upload = storage.presign(photo)
    db.add(photo)
    db.commit()
    response.headers['Cache-Control'] = 'no-store'
    return {'media_id': photo.id, 'expires_in': UPLOAD_SECONDS, 'upload': upload}


def owned_photo(media_id: str = Path(pattern=r'^[0-9a-f]{32}$'),
                user: User = Depends(consented_user), db: Session = Depends(get_db)):
    photo = db.scalar(select(MediaUpload).join(Pet, Pet.id == MediaUpload.pet_id).where(
        MediaUpload.id == media_id, Pet.user_id == user.id, Pet.status == 'active',
    ))
    if photo is None:
        raise APIError(404, 'NOT_FOUND', '未找到照片上传记录')
    return photo


@router.post('/{media_id}/complete')
def complete_photo(request: Request, response: Response, photo: MediaUpload = Depends(owned_photo),
                   db: Session = Depends(get_db)):
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
        db.execute(update(MediaUpload).where(MediaUpload.id == media_id, MediaUpload.version_id.is_(None))
                   .values(version_id=version))
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
    return {'download_url': storage.download_url(photo), 'expires_in': DOWNLOAD_SECONDS}
