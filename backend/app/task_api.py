from fastapi import APIRouter, Depends, Path, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import APIError, get_db
from app.models import Pet, Task, User
from app.pet_api import consented_user

router = APIRouter(prefix='/api/v1')


@router.get('/tasks/{task_id}')
def read_task(response: Response, task_id: str = Path(pattern=r'^[0-9a-f]{32}$'),
              user: User = Depends(consented_user), db: Session = Depends(get_db)):
    task = db.scalar(select(Task).join(Pet, Pet.id == Task.pet_id).where(
        Task.id == task_id, Pet.user_id == user.id, Pet.status == 'active',
    ))
    if task is None:
        raise APIError(404, 'NOT_FOUND', '未找到任务')
    response.headers['Cache-Control'] = 'no-store'
    return {'task_id': task.id, 'type': task.type, 'status': task.status, 'result': task.result}
