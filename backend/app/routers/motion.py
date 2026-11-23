"""萌宠动图（FRD F14）：照片提交、进度读取与动作资产下发。"""
from fastapi import APIRouter, Depends, Path, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import APIError
from app.models import MediaUpload, Pet, Task, User
from app.core.deps import consented_user, owned_pet
from app.services.media import storage_unavailable
from app.services.motion import motion_view
from app.services.quota import quota_gate
from app.services.tasks import enqueue_task, requeue_task

router = APIRouter(prefix='/api/v1/pets')
TASK_TYPE = 'motion_batch'
PUBLIC_KEYS = ('version', 'max_seconds', 'fps', 'height', 'standby', 'actions',
               'health', 'gestures', 'emotions', 'labels', 'status_labels', 'min_ready')


def require_motion_config(request: Request) -> dict:
    config = request.app.state.motion_config
    if config is None:
        raise APIError(503, 'MOTION_UNAVAILABLE', '萌宠动图配置缺失')
    return config


def public_config(config: dict) -> dict:
    return {key: config[key] for key in PUBLIC_KEYS if key in config}


class SubmitMotion(BaseModel):
    model_config = ConfigDict(extra='forbid')

    media_id: str = Field(pattern=r'^[0-9a-f]{32}$')


@router.post('/{pet_id}/motion', status_code=202)
def submit_motion(data: SubmitMotion, request: Request, response: Response,
                  pet_id: int = Path(gt=0, le=2147483647),
                  user: User = Depends(consented_user), db: Session = Depends(get_db)):
    """F14-1：同一宠物并发提交合并到进行中任务，单动作失败不影响其余动作。"""
    owned_pet(pet_id, user, db)
    config = require_motion_config(request)
    db.scalar(select(Pet).where(Pet.id == pet_id).with_for_update())
    photo = db.scalar(select(MediaUpload).where(MediaUpload.id == data.media_id, MediaUpload.pet_id == pet_id))
    if photo is None:
        raise APIError(404, 'NOT_FOUND', '未找到照片上传记录')
    if photo.version_id is None:
        raise APIError(409, 'MEDIA_NOT_VERIFIED', '请先上传并确认照片')
    task = db.scalar(select(Task).where(Task.pet_id == pet_id, Task.type == TASK_TYPE,
                                        Task.status.in_(('pending', 'running'))).order_by(Task.created_at))
    if task is None:
        quota_gate(db, user.id, 'avatar_gen')  # F14-1：与分身共用形象生成配额
        task = enqueue_task(db, pet_id, TASK_TYPE, f'{data.media_id}:{config["version"]}',
                            {'media_id': data.media_id, 'config_version': config['version']})
        if task.status == 'failed':
            requeue_task(db, task.id)
            db.refresh(task)
    db.commit()
    response.headers['Cache-Control'] = 'no-store'
    return {'task_id': task.id, 'status': task.status, 'config': public_config(config)}


@router.get('/{pet_id}/motion')
def read_motion(request: Request, response: Response,
                pet_id: int = Path(gt=0, le=2147483647),
                user: User = Depends(consented_user), db: Session = Depends(get_db)):
    owned_pet(pet_id, user, db)
    config = require_motion_config(request)
    task = db.scalar(select(Task).where(Task.pet_id == pet_id, Task.type == TASK_TYPE)
                     .order_by(Task.created_at.desc(), Task.id.desc()))
    if task is None:
        raise APIError(404, 'NOT_FOUND', '尚未提交萌宠动图生成')
    storage = request.app.state.photo_storage
    if storage is None and task.status == 'succeeded':
        raise storage_unavailable()
    payload = motion_view(task, config, storage)
    payload['config'] = public_config(config)
    response.headers['Cache-Control'] = 'no-store'
    return payload
