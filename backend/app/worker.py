"""arq worker: DB-backed task execution with lease sweep and media cleanup.

Run with: REDIS_URL=... DATABASE_URL=... DASHSCOPE_API_KEY=... MEDIA_S3_*... arq app.worker.WorkerSettings
The DB tasks table is the source of truth; the sweep dispatches pending tasks and
reclaims expired leases every 5 seconds, so a Redis outage never loses a task.
"""
import asyncio
import os
from datetime import timedelta

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import create_engine, delete, or_, select
from sqlalchemy.orm import Session

from app.auth import utcnow
from app.avatars import S3Assets, generate_avatar
from app.models import MediaUpload, Task
from app.tasks import MAX_ATTEMPTS, claim_task, finish_task

MEDIA_CLEANUP_GRACE = timedelta(hours=1)


def _claim(engine, task_id):
    with Session(engine) as db, db.begin():
        return claim_task(db, task_id)


def _finish(engine, task_id, attempt, result):
    with Session(engine) as db, db.begin():
        return finish_task(db, task_id, attempt, result)


def _load(engine, task_id):
    with Session(engine) as db:
        task = db.get(Task, task_id)
        media = db.get(MediaUpload, task.payload.get('media_id')) if task.type == 'avatar_batch' else None
        return task, media


async def run_task(ctx, task_id):
    attempt = await asyncio.to_thread(_claim, ctx['engine'], task_id)
    if attempt is None:
        return
    try:
        task, media = await asyncio.to_thread(_load, ctx['engine'], task_id)
        if task.type != 'avatar_batch':
            raise ValueError(f'unsupported task type: {task.type}')
        result = await generate_avatar(task, media, assets=ctx['assets'],
                                       image_provider=ctx['image_provider'], video_provider=ctx['video_provider'])
    except Exception:
        await asyncio.to_thread(_finish, ctx['engine'], task_id, attempt, None)
        return
    await asyncio.to_thread(_finish, ctx['engine'], task_id, attempt, result)


def _sweep_db(engine):
    now = utcnow()
    with Session(engine) as db, db.begin():
        rows = db.scalars(select(Task).where(or_(
            Task.status == 'pending',
            (Task.status == 'running') & (Task.lease_until <= now),
        ))).all()
        dispatch = []
        for task in rows:
            if task.status == 'running' and task.attempts >= MAX_ATTEMPTS:
                claim_task(db, task.id, now=now)  # exhausted lease -> failed
            else:
                dispatch.append(task.id)
        db.execute(delete(MediaUpload).where(MediaUpload.version_id.is_(None),
                                             MediaUpload.expires_at <= now - MEDIA_CLEANUP_GRACE))
        return dispatch


async def sweep(ctx):
    task_ids = await asyncio.to_thread(_sweep_db, ctx['engine'])
    for task_id in task_ids:
        await ctx['redis'].enqueue_job('run_task', task_id, _job_id=f'rongxing-task:{task_id}')


def _providers_from_env():
    from app.providers.dashscope import DashScopeImageProvider, DashScopeVideoProvider
    key = os.environ.get('DASHSCOPE_API_KEY', '')
    if not key:
        raise RuntimeError('DASHSCOPE_API_KEY is required for the avatar worker')
    return DashScopeImageProvider(key), DashScopeVideoProvider(key)


async def startup(ctx):
    ctx['engine'] = create_engine(os.environ['DATABASE_URL'], hide_parameters=True)
    assets = S3Assets.from_env()
    if assets is None:
        raise RuntimeError('MEDIA_S3_* settings are required for the avatar worker')
    ctx['assets'] = assets
    ctx['image_provider'], ctx['video_provider'] = _providers_from_env()


async def shutdown(ctx):
    ctx['engine'].dispose()


class WorkerSettings:
    functions = [run_task]
    cron_jobs = [cron(sweep, second=set(range(0, 60, 5)))]
    on_startup = startup
    on_shutdown = shutdown
    max_tries = 1  # the retry budget lives in the DB attempts column
    keep_result = 3600
    redis_settings = RedisSettings.from_dsn(os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379'))
