from datetime import UTC, datetime, timedelta
from hashlib import sha256
from json import dumps
from uuid import uuid4

from sqlalchemy import and_, or_, select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models import Task

MAX_ATTEMPTS = 3
LEASE_DURATION = timedelta(minutes=15)


def enqueue_task(db: Session, pet_id: int, kind: str, idempotency_key: str, payload: dict) -> Task:
    """Queue from a trusted business service after pet, media and quota checks."""
    key = sha256(dumps([pet_id, kind, idempotency_key]).encode()).hexdigest()
    values = {
        'id': uuid4().hex,
        'pet_id': pet_id,
        'type': kind,
        'status': 'pending',
        'request_key': key,
        'payload': payload,
        'attempts': 0,
    }
    if db.get_bind().dialect.name == 'sqlite':
        statement = sqlite_insert(Task).values(**values).on_conflict_do_nothing(index_elements=['request_key'])
    else:
        statement = mysql_insert(Task).values(**values).on_duplicate_key_update(request_key=Task.request_key)
    db.execute(statement)
    task = db.scalars(
        select(Task).where(Task.request_key == key).with_for_update().execution_options(populate_existing=True)
    ).one()
    if dumps(task.payload, sort_keys=True) != dumps(payload, sort_keys=True):
        raise ValueError('Idempotency key was already used with a different payload')
    return task


def requeue_task(db: Session, task_id: str) -> bool:
    """User-initiated retry: a terminally failed task gets a fresh attempt budget."""
    return (
        db.execute(
            update(Task)
            .where(Task.id == task_id, Task.status == 'failed')
            .values(status='pending', attempts=0, lease_until=None, result=None)
        ).rowcount
        == 1
    )


def claim_task(db: Session, task_id: str, *, now: datetime | None = None) -> int | None:
    now = now if now is not None else datetime.now(UTC).replace(tzinfo=None)
    expired = and_(Task.status == 'running', Task.lease_until <= now)
    claimed = db.execute(
        update(Task)
        .where(
            Task.id == task_id,
            or_(Task.status == 'pending', expired),
            Task.attempts < MAX_ATTEMPTS,
        )
        .values(status='running', attempts=Task.attempts + 1, lease_until=now + LEASE_DURATION)
    ).rowcount
    if claimed == 1:
        return db.scalar(select(Task.attempts).where(Task.id == task_id))
    db.execute(
        update(Task)
        .where(Task.id == task_id, expired, Task.attempts >= MAX_ATTEMPTS)
        .values(status='failed', lease_until=None)
    )
    return None


def finish_task(
    db: Session, task_id: str, attempt: int, result: dict | None = None, *, now: datetime | None = None
) -> bool:
    now = now if now is not None else datetime.now(UTC).replace(tzinfo=None)
    status = 'succeeded' if result is not None else ('pending' if attempt < MAX_ATTEMPTS else 'failed')
    return (
        db.execute(
            update(Task)
            .where(
                Task.id == task_id,
                Task.status == 'running',
                Task.attempts == attempt,
                Task.lease_until > now,
            )
            .values(status=status, result=result, lease_until=None)
        ).rowcount
        == 1
    )
