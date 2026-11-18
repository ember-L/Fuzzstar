from fastapi import APIRouter, Depends, Path, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import APIError, get_db
from app.avatar_assets_api import group_payload, placeholder_base_url, require_library
from app.media import storage_unavailable
from app.models import MediaUpload, Pet, Task, User
from app.pet_api import consented_user, owned_pet
from app.tasks import enqueue_task, requeue_task

router = APIRouter(prefix='/api/v1/pets')


class SubmitAvatar(BaseModel):
    model_config = ConfigDict(extra='forbid')

    media_id: str = Field(pattern=r'^[0-9a-f]{32}$')


@router.post('/{pet_id}/avatar', status_code=202)
def submit_avatar(data: SubmitAvatar, request: Request, response: Response,
                  pet_id: int = Path(gt=0, le=2147483647),
                  user: User = Depends(consented_user), db: Session = Depends(get_db)):
    pet = owned_pet(pet_id, user, db)
    library = require_library(request)
    # Serialize per pet so concurrent submissions merge into the in-progress task.
    db.scalar(select(Pet).where(Pet.id == pet_id).with_for_update())
    photo = db.scalar(select(MediaUpload).where(MediaUpload.id == data.media_id, MediaUpload.pet_id == pet_id))
    if photo is None:
        raise APIError(404, 'NOT_FOUND', '未找到照片上传记录')
    if photo.version_id is None:
        raise APIError(409, 'MEDIA_NOT_VERIFIED', '请先上传并确认照片')
    task = db.scalar(select(Task).where(Task.pet_id == pet_id, Task.type == 'avatar_batch',
                                        Task.status.in_(('pending', 'running'))).order_by(Task.created_at))
    if task is None:
        task = enqueue_task(db, pet_id, 'avatar_batch', data.media_id, {'media_id': data.media_id})
        if task.status == 'failed':
            # A user resubmitting a failed generation retries it with a fresh attempt budget.
            requeue_task(db, task.id)
            db.refresh(task)
    db.commit()
    response.headers['Cache-Control'] = 'no-store'
    return {'task_id': task.id, 'status': task.status,
            'placeholder_manifest': group_payload(library, pet.body_type, placeholder_base_url(request))}


@router.get('/{pet_id}/avatar')
def read_avatar(request: Request, response: Response,
                pet_id: int = Path(gt=0, le=2147483647),
                user: User = Depends(consented_user), db: Session = Depends(get_db)):
    pet = owned_pet(pet_id, user, db)
    library = require_library(request)
    task = db.scalar(select(Task).where(Task.pet_id == pet_id, Task.type == 'avatar_batch')
                     .order_by(Task.created_at.desc(), Task.id.desc()))
    if task is None:
        raise APIError(404, 'NOT_FOUND', '尚未提交分身生成')
    actions = library.manifest['actions']
    payload = {'task_id': task.id, 'status': task.status, 'body_type': pet.body_type,
               'placeholder_manifest': group_payload(library, pet.body_type, placeholder_base_url(request)),
               'base_image': None, 'clips': {}, 'ready_count': 0, 'usable': False}
    result = task.result if task.status == 'succeeded' else None
    if result:
        storage = request.app.state.photo_storage
        if storage is None:
            raise storage_unavailable()
        base_image = result.get('base_image')
        if base_image:
            payload['base_image'] = {'url': storage.asset_url(base_image['key'], base_image['version_id']),
                                     'version_id': base_image['version_id']}
        for action in actions:
            clip = result.get('clips', {}).get(action)
            if clip and clip.get('status') == 'ready':
                payload['clips'][action] = {'status': 'ready', 'url': storage.asset_url(clip['key'], clip['version_id']),
                                            'version_id': clip['version_id']}
            else:
                payload['clips'][action] = {'status': 'failed', 'url': None}
        payload['ready_count'] = result.get('ready_count', 0)
        payload['usable'] = result.get('usable', False)
    else:
        state = 'failed' if task.status == 'failed' else 'pending'
        payload['clips'] = {action: {'status': state, 'url': None} for action in actions}
    response.headers['Cache-Control'] = 'no-store'
    return payload
