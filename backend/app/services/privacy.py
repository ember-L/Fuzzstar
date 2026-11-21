"""T17 F12-4: account deletion with 15-day grace and physical purge (PIPL)."""
from datetime import datetime, timedelta

from sqlalchemy import delete, or_, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models import (AiUsageLog, AuthSession, ChatMessage, ChatSession, Consent, DeletionJob,
                        DietRecord, HealthEvent, HealthScreening, MediaUpload, Pet, RefreshToken,
                        RequestIdempotency, ScreeningMedia, ScreeningSymptom, Task, UsageCounter,
                        User, UserCredential, VerificationMail, WeightRecord)

PURGE_DELAY = timedelta(days=15)


def request_deletion(db: Session, user_id: int, *, now: datetime) -> tuple[DeletionJob, bool]:
    """Freeze the account and schedule physical purge; idempotent while pending."""
    job = db.scalar(select(DeletionJob).where(DeletionJob.user_id == user_id, DeletionJob.status == 'pending'))
    if job is not None:
        return job, False
    job = DeletionJob(user_id=user_id, status='pending', requested_at=now, purge_after=now + PURGE_DELAY)
    db.add(job)
    user = db.get(User, user_id)
    user.status = 'deletion_pending'
    db.execute(update(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
               .values(revoked_at=now))
    db.flush()
    return job, True


def _delete_oss_objects(db: Session, user_id: int, storage) -> None:
    pet_ids = select(Pet.id).where(Pet.user_id == user_id)
    for media in db.scalars(select(MediaUpload).where(MediaUpload.pet_id.in_(pet_ids))).all():
        kwargs = {'Bucket': storage.bucket, 'Key': media.object_key}
        if media.version_id is not None:
            kwargs['VersionId'] = media.version_id
        storage.client.delete_object(**kwargs)
    tasks = db.scalars(select(Task).where(Task.pet_id.in_(pet_ids),
                                          Task.type.in_(['avatar_batch', 'gif_export']),
                                          Task.result.is_not(None))).all()
    for task in tasks:
        result = task.result or {}
        entries = []
        base = result.get('base_image')
        if isinstance(base, dict) and base.get('key'):
            entries.append(base)
        for clip in (result.get('clips') or {}).values():
            if isinstance(clip, dict) and clip.get('status') == 'ready' and clip.get('key'):
                entries.append(clip)
        if result.get('key'):  # gif_export result
            entries.append(result)
        for entry in entries:
            kwargs = {'Bucket': storage.bucket, 'Key': entry['key']}
            if entry.get('version_id'):
                kwargs['VersionId'] = entry['version_id']
            storage.client.delete_object(**kwargs)


def purge_user_data(db: Session, user_id: int, *, storage, now: datetime) -> bool:
    """Physically remove all user data once the grace period elapsed. Caller commits."""
    job = db.scalar(select(DeletionJob).where(DeletionJob.user_id == user_id, DeletionJob.status == 'pending'))
    if job is None or job.purge_after > now:
        return False
    if storage is None:
        raise RuntimeError('object storage is required for account purge')
    _delete_oss_objects(db, user_id, storage)
    pet_ids = select(Pet.id).where(Pet.user_id == user_id)
    task_ids = select(Task.id).where(Task.pet_id.in_(pet_ids))
    session_ids = select(ChatSession.id).where(ChatSession.user_id == user_id)
    screening_ids = select(HealthScreening.id).where(HealthScreening.user_id == user_id)
    credential_ids = select(UserCredential.id).where(UserCredential.user_id == user_id)
    auth_session_ids = select(AuthSession.id).where(AuthSession.user_id == user_id)
    db.execute(delete(ChatMessage).where(ChatMessage.session_id.in_(session_ids)))
    db.execute(delete(ChatSession).where(ChatSession.user_id == user_id))
    db.execute(delete(ScreeningMedia).where(ScreeningMedia.screening_id.in_(screening_ids)))
    db.execute(delete(ScreeningSymptom).where(ScreeningSymptom.screening_id.in_(screening_ids)))
    db.execute(delete(HealthScreening).where(HealthScreening.user_id == user_id))
    db.execute(delete(HealthEvent).where(HealthEvent.pet_id.in_(pet_ids)))
    db.execute(delete(DietRecord).where(DietRecord.pet_id.in_(pet_ids)))
    db.execute(delete(WeightRecord).where(WeightRecord.pet_id.in_(pet_ids)))
    # Audit keeps anonymous aggregates only (AC-12-4).
    db.execute(update(AiUsageLog).where(or_(AiUsageLog.user_id == user_id, AiUsageLog.task_id.in_(task_ids)))
               .values(user_id=None, task_id=None))
    db.execute(delete(Task).where(Task.pet_id.in_(pet_ids)))
    db.execute(delete(MediaUpload).where(MediaUpload.pet_id.in_(pet_ids)))
    db.execute(delete(Pet).where(Pet.user_id == user_id))
    db.execute(delete(RequestIdempotency).where(RequestIdempotency.user_id == user_id))
    db.execute(delete(UsageCounter).where(UsageCounter.user_id == user_id))
    db.execute(delete(RefreshToken).where(RefreshToken.session_id.in_(auth_session_ids)))
    db.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
    db.execute(delete(VerificationMail).where(VerificationMail.credential_id.in_(credential_ids)))
    db.execute(delete(UserCredential).where(UserCredential.user_id == user_id))
    db.execute(delete(Consent).where(Consent.user_id == user_id))
    db.delete(job)
    user = db.get(User, user_id)
    if user is not None:
        db.delete(user)
    db.flush()
    return True


def purge_due(engine: Engine, *, storage, now: datetime) -> list[int]:
    """Sweep due deletion jobs; each purge runs in its own transaction."""
    with Session(engine) as db:
        due = db.scalars(select(DeletionJob.user_id).where(DeletionJob.status == 'pending',
                                                           DeletionJob.purge_after <= now)).all()
    purged = []
    for user_id in due:
        with Session(engine) as db, db.begin():
            if purge_user_data(db, user_id, storage=storage, now=now):
                purged.append(user_id)
    return purged
