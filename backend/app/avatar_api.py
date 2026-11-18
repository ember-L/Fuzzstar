from fastapi import APIRouter, Depends, Path, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import APIError, get_db
from app.models import MediaUpload, Pet, Task, User
from app.pet_api import consented_user, owned_pet
from app.tasks import enqueue_task, requeue_task

router = APIRouter(prefix='/api/v1/pets')


class SubmitAvatar(BaseModel):
    model_config = ConfigDict(extra='forbid')

    media_id: str = Field(pattern=r'^[0-9a-f]{32}$')


@router.post('/{pet_id}/avatar', status_code=202)
def submit_avatar(data: SubmitAvatar, response: Response,
                  pet_id: int = Path(gt=0, le=2147483647),
                  user: User = Depends(consented_user), db: Session = Depends(get_db)):
    owned_pet(pet_id, user, db)
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
    return {'task_id': task.id, 'status': task.status}
