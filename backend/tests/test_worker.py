import asyncio
import os
import unittest
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.security import utcnow
from app.models import Base, MediaUpload, Pet, Task, User
from app.services.tasks import claim_task, enqueue_task, finish_task
from app.services.avatars import ACTIONS, generate_avatar
from app.providers.fake import FakeImageProvider, FakeVideoProvider
from app import worker


class FakeAssets:
    def __init__(self, photo=b'photo-bytes'):
        self.photo = photo
        self.objects = {}
        self.reads = []

    async def read_photo(self, media):
        self.reads.append((media.object_key, media.version_id))
        return self.photo

    async def read_object(self, key, version_id):
        self.reads.append((key, version_id))
        return self.objects[key][0]

    async def write(self, key, data, content_type):
        version = f'version-{len(self.objects) + 1}'
        self.objects[key] = (data, content_type, version)
        return version

    async def presign_url(self, key, version_id):
        return f'https://fake.local/{key}?v={version_id}'


class FakeRedis:
    def __init__(self):
        self.jobs = []

    async def enqueue_job(self, function, *args, _job_id=None, **kwargs):
        self.jobs.append((function, args, _job_id))


def make_engine():
    from sqlalchemy.pool import StaticPool
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return engine


def seed_task(engine, *, media_verified=True, pet_id=1):
    with Session(engine) as db, db.begin():
        db.add(User(id=1, nickname='测试用户'))
        db.add(Pet(id=pet_id, user_id=1, name='团团', species='cat', status='active'))
        media_id = uuid4().hex
        db.add(MediaUpload(id=media_id, pet_id=pet_id, content_type='image/png', size_bytes=9,
                           expires_at=utcnow() + timedelta(minutes=10),
                           version_id='version-1' if media_verified else None))
        task = enqueue_task(db, pet_id, 'avatar_batch', media_id, {'media_id': media_id})
        return task.id, media_id


class GenerateAvatarTests(unittest.TestCase):
    def setUp(self):
        self.engine = make_engine()
        self.addCleanup(self.engine.dispose)
        self.task_id, self.media_id = seed_task(self.engine)
        self.assets = FakeAssets()
        self.image = FakeImageProvider()
        self.video = FakeVideoProvider()

    def run_generate(self):
        with Session(self.engine) as db:
            task = db.get(Task, self.task_id)
            media = db.get(MediaUpload, self.media_id)
            return asyncio.run(generate_avatar(task, media, assets=self.assets,
                                               image_provider=self.image, video_provider=self.video))

    def test_produces_base_and_seven_ready_clips(self):
        result = self.run_generate()
        self.assertTrue(result['usable'])
        self.assertEqual(result['ready_count'], 7)
        self.assertEqual(set(result['clips']), set(ACTIONS))
        self.assertTrue(all(clip['status'] == 'ready' for clip in result['clips'].values()))
        self.assertEqual(len(self.assets.objects), 8)
        self.assertEqual(len(self.image.calls), 1)
        self.assertEqual(len(self.video.calls), 7)
        self.assertEqual(self.assets.reads, [(f'photos/1/{self.media_id}', 'version-1')])

    def test_single_clip_failure_does_not_block_others(self):
        self.video = FakeVideoProvider(fail_actions={'sad'})
        result = self.run_generate()
        self.assertEqual(result['ready_count'], 6)
        self.assertTrue(result['usable'])
        self.assertEqual(result['clips']['sad']['status'], 'failed')

    def test_below_threshold_is_not_usable(self):
        self.video = FakeVideoProvider(fail_actions={'sad', 'sick', 'crouch'})
        result = self.run_generate()
        self.assertEqual(result['ready_count'], 4)
        self.assertFalse(result['usable'])

    def test_base_image_failure_propagates(self):
        class Broken:
            async def edit(self, photo, prompt):
                raise RuntimeError('edit failed')
        with self.assertRaises(RuntimeError):
            asyncio.run(generate_avatar(self._task(), self._media(), assets=self.assets,
                                        image_provider=Broken(), video_provider=self.video))

    def _task(self):
        with Session(self.engine) as db:
            return db.get(Task, self.task_id)

    def _media(self):
        with Session(self.engine) as db:
            return db.get(MediaUpload, self.media_id)


class RunTaskTests(unittest.TestCase):
    def setUp(self):
        self.engine = make_engine()
        self.addCleanup(self.engine.dispose)
        self.task_id, self.media_id = seed_task(self.engine)
        self.ctx = {'engine': self.engine, 'assets': FakeAssets(),
                    'image_provider': FakeImageProvider(), 'video_provider': FakeVideoProvider()}

    def status(self):
        with Session(self.engine) as db:
            task = db.get(Task, self.task_id)
            return task.status, task.attempts, task.result

    def test_run_task_claims_generates_and_finishes(self):
        asyncio.run(worker.run_task(self.ctx, self.task_id))
        status, attempts, result = self.status()
        self.assertEqual((status, attempts), ('succeeded', 1))
        self.assertTrue(result['usable'])

    def test_failure_requeues_until_attempts_exhausted(self):
        class Broken:
            async def edit(self, photo, prompt):
                raise RuntimeError('edit failed')
        self.ctx['image_provider'] = Broken()
        for expected in (('pending', 1), ('pending', 2), ('failed', 3)):
            asyncio.run(worker.run_task(self.ctx, self.task_id))
            status, attempts, _ = self.status()
            self.assertEqual((status, attempts), expected)

    def test_unclaimable_task_is_ignored(self):
        with Session(self.engine) as db, db.begin():
            attempt = claim_task(db, self.task_id)
            finish_task(db, self.task_id, attempt, result={'done': True})
        asyncio.run(worker.run_task(self.ctx, self.task_id))
        status, attempts, result = self.status()
        self.assertEqual((status, attempts, result), ('succeeded', 1, {'done': True}))

    def test_unknown_task_type_fails_after_retries(self):
        with Session(self.engine) as db, db.begin():
            db.add(Task(id=uuid4().hex, pet_id=1, type='mystery', status='pending',
                        request_key=uuid4().hex, payload={}, attempts=0))
            mystery = db.scalars(select(Task).where(Task.type == 'mystery')).one().id
        for _ in range(3):
            asyncio.run(worker.run_task(self.ctx, mystery))
        with Session(self.engine) as db:
            self.assertEqual(db.get(Task, mystery).status, 'failed')


class SweepTests(unittest.TestCase):
    def setUp(self):
        self.engine = make_engine()
        self.addCleanup(self.engine.dispose)
        self.redis = FakeRedis()
        self.ctx = {'engine': self.engine, 'redis': self.redis}

    def test_dispatches_pending_and_expired_lease_tasks(self):
        pending, _ = seed_task(self.engine)
        with Session(self.engine) as db, db.begin():
            expired = enqueue_task(db, 1, 'avatar_batch', 'expired-key', {'media_id': 'x'})
            expired_id = expired.id
            claim_task(db, expired_id, now=utcnow() - timedelta(minutes=20))
        asyncio.run(worker.sweep(self.ctx))
        dispatched = {args[0] for _, args, _ in self.redis.jobs}
        self.assertEqual(dispatched, {pending, expired_id})
        self.assertTrue(all(function == 'run_task' for function, _, _ in self.redis.jobs))

    def test_exhausted_expired_task_is_failed_not_dispatched(self):
        task_id, _ = seed_task(self.engine)
        with Session(self.engine) as db:
            for _ in range(3):
                with db.begin():
                    attempt = claim_task(db, task_id, now=utcnow() - timedelta(minutes=20))
                    finish_task(db, task_id, attempt, now=utcnow() - timedelta(minutes=20))
        asyncio.run(worker.sweep(self.ctx))
        with Session(self.engine) as db:
            self.assertEqual(db.get(Task, task_id).status, 'failed')
        self.assertEqual(self.redis.jobs, [])

    def test_cleans_expired_unverified_media_only(self):
        _, fresh_media = seed_task(self.engine)
        with Session(self.engine) as db, db.begin():
            db.add(MediaUpload(id=uuid4().hex, pet_id=1, content_type='image/png', size_bytes=1,
                               expires_at=utcnow() - timedelta(hours=2), version_id=None))
            stale = db.scalars(select(MediaUpload).where(MediaUpload.version_id.is_(None))).all()
            stale_id = [m.id for m in stale if m.id != fresh_media][0]
            db.add(MediaUpload(id=uuid4().hex, pet_id=1, content_type='image/png', size_bytes=1,
                               expires_at=utcnow() - timedelta(hours=2), version_id='version-9'))
        asyncio.run(worker.sweep(self.ctx))
        with Session(self.engine) as db:
            self.assertIsNone(db.get(MediaUpload, stale_id))
            self.assertIsNotNone(db.get(MediaUpload, fresh_media))
            self.assertEqual(len(db.scalars(select(MediaUpload).where(MediaUpload.version_id.is_not(None))).all()), 2)


@unittest.skipUnless(os.environ.get('REDIS_TEST_URL'), 'requires a disposable Redis instance')
class RedisIntegrationTests(unittest.TestCase):
    def test_worker_completes_avatar_task_through_real_redis(self):
        from arq import Worker
        from arq.connections import RedisSettings, create_pool

        engine = make_engine()
        self.addCleanup(engine.dispose)
        task_id, _ = seed_task(engine)
        settings = RedisSettings.from_dsn(os.environ['REDIS_TEST_URL'])

        async def scenario():
            pool = await create_pool(settings)
            try:
                await pool.enqueue_job('run_task', task_id, _job_id=f'test-task:{task_id}')

                async def on_startup(ctx):
                    ctx['engine'] = engine
                    ctx['assets'] = FakeAssets()
                    ctx['image_provider'] = FakeImageProvider()
                    ctx['video_provider'] = FakeVideoProvider()

                await Worker([worker.run_task], redis_settings=settings, max_tries=1,
                             burst=True, poll_delay=0.05, on_startup=on_startup).async_run()
            finally:
                await pool.aclose()

        asyncio.run(scenario())
        with Session(engine) as db:
            task = db.get(Task, task_id)
            self.assertEqual(task.status, 'succeeded')
            self.assertTrue(task.result['usable'])


class WorkerSettingsTests(unittest.TestCase):
    def test_concurrency_capped_at_two(self):
        # FRD 内测门槛：100 只宠物并发不雪崩，worker 并发限 2（FRD.md:357）。
        from app.worker import WorkerSettings
        self.assertEqual(WorkerSettings.max_jobs, 2)
        self.assertEqual(WorkerSettings.max_tries, 1)


if __name__ == '__main__':
    unittest.main()
