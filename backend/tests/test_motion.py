"""F14 萌宠动图：配置校验、GIF 规格、占位生成、提交与读取接口。"""
import asyncio
import io
import unittest
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from uuid import uuid4

from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import worker
from app.core.security import utcnow
from app.models import Base, MediaUpload, Pet, Task, User
from app.providers.motion import PlaceholderMotionProvider
from app.services.motion import generate_motion, load_motion_config, verify_gif
from test_auth_api import AuthAPIFixture
from test_avatar_read import FakeStorage
from test_worker import FakeAssets

BACKEND = Path(__file__).resolve().parents[1]
RULES = BACKEND / 'rules'
SMALL = {'seconds': 1.5, 'fps': 6, 'height': 160}


def small_config(**overrides):
    config = load_motion_config(RULES)
    config = dict(config)
    config['actions'] = config['actions'][:3]
    config['min_ready'] = 2
    config['height'] = 160
    config['max_seconds'] = 2
    config.update(overrides)
    return config


def make_photo(color=(180, 120, 80), size=(200, 200)):
    buffer = io.BytesIO()
    Image.new('RGB', size, color).save(buffer, 'PNG')
    return buffer.getvalue()


def make_gif(frames=3, duration=100, loop=0, size=(80, 80)):
    images = [Image.new('RGB', size, (200, 140 + index, 60)) for index in range(frames)]
    buffer = io.BytesIO()
    images[0].save(buffer, 'GIF', save_all=True, append_images=images[1:],
                   duration=duration, loop=loop, optimize=False)
    return buffer.getvalue()


def motion_result(actions=('idle', 'happy'), ready=('idle', 'happy')):
    gifs = {}
    for action in actions:
        if action in ready:
            gifs[action] = {'status': 'ready', 'key': f'motions/1/task/{action}.gif', 'version_id': f'v-{action}',
                            'width': 160, 'height': 160, 'frames': 9, 'duration_s': 1.5, 'bytes': 128}
        else:
            gifs[action] = {'status': 'failed'}
    return {'base_image': {'key': 'motions/1/task/base.png', 'version_id': 'v-base'},
            'gifs': gifs, 'ready_count': len(ready), 'usable': len(ready) >= 2, 'config_version': 'mo-test'}


class MotionConfigTests(unittest.TestCase):
    def test_loads_rule_file(self):
        config = load_motion_config(RULES)
        self.assertIn('idle', config['actions'])
        self.assertEqual(config['health']['urgent'], 'sick')
        self.assertLessEqual(config['max_seconds'], 10)

    def test_missing_file_returns_none(self):
        with TemporaryDirectory() as tmp:
            self.assertIsNone(load_motion_config(Path(tmp)))

    def test_rejects_unknown_action_reference(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'motion.yaml'
            config = load_motion_config(RULES)
            config['health'] = {'normal': 'dance'}
            import yaml
            path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding='utf-8')
            with self.assertRaises(RuntimeError):
                load_motion_config(Path(tmp))

    def test_rejects_min_ready_above_action_count(self):
        with TemporaryDirectory() as tmp:
            config = load_motion_config(RULES)
            config['min_ready'] = len(config['actions']) + 1
            import yaml
            (Path(tmp) / 'motion.yaml').write_text(yaml.safe_dump(config, allow_unicode=True), encoding='utf-8')
            with self.assertRaises(RuntimeError):
                load_motion_config(Path(tmp))

    def test_rejects_oversized_duration_cap(self):
        with TemporaryDirectory() as tmp:
            config = load_motion_config(RULES)
            config['max_seconds'] = 30
            import yaml
            (Path(tmp) / 'motion.yaml').write_text(yaml.safe_dump(config, allow_unicode=True), encoding='utf-8')
            with self.assertRaises(RuntimeError):
                load_motion_config(Path(tmp))


class GifSpecTests(unittest.TestCase):
    def test_accepts_looping_gif_within_limits(self):
        spec = verify_gif(make_gif(), max_seconds=2, max_height=480)
        self.assertEqual(spec['height'], 80)
        self.assertAlmostEqual(spec['duration_s'], 0.3, places=2)

    def test_rejects_duration_over_limit(self):
        with self.assertRaises(ValueError):
            verify_gif(make_gif(frames=3, duration=1000), max_seconds=2, max_height=480)

    def test_rejects_non_gif(self):
        with self.assertRaises(ValueError):
            verify_gif(make_photo(), max_seconds=2, max_height=480)

    def test_rejects_non_looping_gif(self):
        with self.assertRaises(ValueError):
            verify_gif(make_gif(loop=1), max_seconds=2, max_height=480)

    def test_rejects_oversized_height(self):
        with self.assertRaises(ValueError):
            verify_gif(make_gif(size=(200, 200)), max_seconds=2, max_height=160)


class PlaceholderProviderTests(unittest.TestCase):
    def test_enchant_returns_png(self):
        asset = asyncio.run(PlaceholderMotionProvider(**SMALL).enchant(make_photo(), prompt='萌化'))
        self.assertEqual(asset.content_type, 'image/png')
        self.assertEqual(Image.open(io.BytesIO(asset.data)).format, 'PNG')

    def test_animate_returns_playable_gif(self):
        provider = PlaceholderMotionProvider(**SMALL)
        base = asyncio.run(provider.enchant(make_photo(), prompt='萌化'))
        for action in ('idle', 'happy', 'sleep'):
            asset = asyncio.run(provider.animate(base.data, prompt=f'{action} 动作', seconds=2))
            spec = verify_gif(asset.data, max_seconds=2, max_height=160)
            self.assertEqual(asset.content_type, 'image/gif')
            self.assertGreaterEqual(spec['frames'], 2)
            self.assertLessEqual(spec['duration_s'], 2.1)


class MotionGenerationTests(unittest.TestCase):
    def setUp(self):
        self.assets = FakeAssets(photo=make_photo())
        self.task = SimpleNamespace(pet_id=1, id='c' * 32, payload={})

    def test_generates_base_and_all_actions(self):
        config = small_config()
        result = asyncio.run(generate_motion(self.task, SimpleNamespace(version_id='v1', object_key='photos/1/p'), config=config,
                                             assets=self.assets,
                                             provider=PlaceholderMotionProvider(**SMALL)))
        self.assertEqual(result['base_image']['key'], f"motions/1/{'c' * 32}/base.png")
        self.assertEqual(set(result['gifs']), set(config['actions']))
        self.assertEqual(result['ready_count'], len(config['actions']))
        self.assertTrue(result['usable'])
        self.assertEqual(self.assets.objects[result['base_image']['key']][1], 'image/png')
        for action in config['actions']:
            entry = result['gifs'][action]
            self.assertEqual(entry['status'], 'ready')
            self.assertEqual(self.assets.objects[entry['key']][1], 'image/gif')
            self.assertLessEqual(entry['duration_s'], config['max_seconds'] + 0.1)

    def test_failed_action_does_not_block_others(self):
        class FailingProvider(PlaceholderMotionProvider):
            async def animate(self, image, *, prompt, seconds):
                if prompt.startswith('happy'):
                    raise RuntimeError('provider down')
                return await super().animate(image, prompt=prompt, seconds=seconds)

        config = small_config()
        result = asyncio.run(generate_motion(self.task, SimpleNamespace(version_id='v1', object_key='photos/1/p'), config=config,
                                             assets=self.assets, provider=FailingProvider(**SMALL)))
        self.assertEqual(result['gifs']['happy']['status'], 'failed')
        self.assertEqual(result['ready_count'], len(config['actions']) - 1)
        self.assertTrue(result['usable'])

    def test_oversized_gif_marks_action_failed(self):
        class OversizedProvider(PlaceholderMotionProvider):
            async def animate(self, image, *, prompt, seconds):
                from app.providers.base import GeneratedAsset
                return GeneratedAsset(make_gif(size=(200, 200)), 'image/gif')

        config = small_config()
        result = asyncio.run(generate_motion(self.task, SimpleNamespace(version_id='v1', object_key='photos/1/p'), config=config,
                                             assets=self.assets, provider=OversizedProvider(**SMALL)))
        self.assertTrue(all(gif['status'] == 'failed' for gif in result['gifs'].values()))
        self.assertFalse(result['usable'])

    def test_unverified_media_is_rejected(self):
        with self.assertRaises(ValueError):
            asyncio.run(generate_motion(self.task, SimpleNamespace(version_id=None), config=small_config(),
                                        assets=self.assets, provider=PlaceholderMotionProvider(**SMALL)))


class MotionAPITests(AuthAPIFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.headers = {'Authorization': f"Bearer {self.login().json()['access_token']}"}
        self.client.post('/api/v1/consents', headers=self.headers,
                         json={'privacy': 'p1', 'terms': 't1'}).raise_for_status()
        self.pet_id = self.client.post('/api/v1/pets', headers=self.headers, json={'name': '团团'}).json()['id']

    def make_media(self, pet_id=None, verified=True):
        media_id = uuid4().hex
        with Session(self.engine) as db, db.begin():
            db.add(MediaUpload(id=media_id, pet_id=pet_id if pet_id is not None else self.pet_id,
                               content_type='image/png', size_bytes=1024,
                               expires_at=utcnow() + timedelta(minutes=10),
                               version_id='version-1' if verified else None))
        return media_id

    def submit(self, media_id=None, pet_id=None, headers=None):
        return self.client.post(f'/api/v1/pets/{pet_id if pet_id is not None else self.pet_id}/motion',
                                json={'media_id': media_id if media_id is not None else self.make_media()},
                                headers=self.headers if headers is None else headers)

    def read(self, pet_id=None):
        return self.client.get(f'/api/v1/pets/{pet_id if pet_id is not None else self.pet_id}/motion',
                               headers=self.headers)

    def insert_task(self, status='succeeded', result=None):
        task_id = uuid4().hex
        with Session(self.engine) as db, db.begin():
            db.add(Task(id=task_id, pet_id=self.pet_id, type='motion_batch', status=status,
                        request_key=uuid4().hex, payload={'media_id': uuid4().hex},
                        result=result if result is not None else motion_result(), attempts=1))
        return task_id

    def test_requires_login_and_consent(self):
        self.assertEqual(self.submit(headers={}).status_code, 401)
        from app.services.identity import create_email_account, verify_email
        with Session(self.engine) as db, db.begin():
            token = create_email_account(db, 'noconsent-motion@example.com', self.password, self.now)
            verify_email(db, token, self.now)
        headers = {'Authorization': f"Bearer {self.login('noconsent-motion@example.com').json()['access_token']}"}
        response = self.submit(headers=headers)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['code'], 'CONSENT_REQUIRED')

    def test_unknown_or_foreign_pet_is_not_found(self):
        self.assertEqual(self.submit(pet_id=999999).status_code, 404)
        from app.services.identity import create_email_account, verify_email
        with Session(self.engine) as db, db.begin():
            token = create_email_account(db, 'other-motion@example.com', self.password, self.now)
            verify_email(db, token, self.now)
        headers = {'Authorization': f"Bearer {self.login('other-motion@example.com').json()['access_token']}"}
        self.client.post('/api/v1/consents', headers=headers, json={'privacy': 'p1', 'terms': 't1'}).raise_for_status()
        self.assertEqual(self.submit(pet_id=self.pet_id, headers=headers).status_code, 404)

    def test_media_checks(self):
        other_pet = self.client.post('/api/v1/pets', headers=self.headers, json={'name': '二猫'}).json()['id']
        self.assertEqual(self.submit(media_id=self.make_media(pet_id=other_pet)).status_code, 404)
        response = self.submit(media_id=self.make_media(verified=False))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['code'], 'MEDIA_NOT_VERIFIED')
        self.assertEqual(self.submit(media_id='not-a-media-id').status_code, 400)

    def test_submission_creates_task_and_returns_config(self):
        response = self.submit()
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        body = response.json()
        self.assertEqual(body['status'], 'pending')
        self.assertIn('idle', body['config']['actions'])
        self.assertNotIn('style_prompt', body['config'])
        with Session(self.engine) as db:
            task = db.get(Task, body['task_id'])
            self.assertEqual(task.type, 'motion_batch')
            self.assertEqual(task.payload['config_version'], body['config']['version'])

    def test_inflight_submission_merges(self):
        first = self.submit()
        second = self.submit()
        self.assertEqual(second.status_code, 202)
        self.assertEqual(second.json()['task_id'], first.json()['task_id'])
        with Session(self.engine) as db:
            self.assertEqual(len(db.scalars(select(Task).where(Task.type == 'motion_batch')).all()), 1)

    def test_failed_task_requeues_on_resubmit(self):
        media_id = self.make_media()
        task_id = self.submit(media_id=media_id).json()['task_id']
        with Session(self.engine) as db, db.begin():
            db.get(Task, task_id).status = 'failed'
        again = self.submit(media_id=media_id)
        self.assertEqual(again.status_code, 202)
        self.assertEqual(again.json()['task_id'], task_id)
        self.assertEqual(again.json()['status'], 'pending')

    def test_read_before_submission_is_not_found(self):
        self.assertEqual(self.read().status_code, 404)

    def test_read_pending_lists_every_action(self):
        self.submit()
        body = self.read().raise_for_status().json()
        self.assertEqual(body['status'], 'pending')
        self.assertEqual(set(body['gifs']), set(body['config']['actions']))
        self.assertTrue(all(gif['status'] == 'pending' and gif['url'] is None for gif in body['gifs'].values()))
        self.assertFalse(body['usable'])

    def test_read_succeeded_returns_versioned_urls(self):
        self.insert_task()
        self.client.app.state.photo_storage = FakeStorage()
        body = self.read().raise_for_status().json()
        self.assertEqual(body['base_image']['url'], 'https://fake.local/motions/1/task/base.png?v=v-base')
        self.assertEqual(body['gifs']['idle']['url'], 'https://fake.local/motions/1/task/idle.gif?v=v-idle')
        self.assertEqual(body['gifs']['idle']['duration_s'], 1.5)
        self.assertTrue(body['usable'])

    def test_read_succeeded_without_storage_is_unavailable(self):
        self.insert_task()
        self.client.app.state.photo_storage = None
        response = self.read()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['code'], 'MEDIA_UNAVAILABLE')

    def test_config_endpoint_and_missing_config(self):
        body = self.client.get('/api/v1/config/motion', headers=self.headers).raise_for_status().json()
        self.assertIn('gestures', body)
        self.client.app.state.motion_config = None
        response = self.client.get('/api/v1/config/motion', headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['code'], 'MOTION_UNAVAILABLE')
        self.assertEqual(self.read().status_code, 503)


class MotionWorkerTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.assets = FakeAssets(photo=make_photo())
        self.media_id = uuid4().hex
        self.task_id = uuid4().hex
        with Session(self.engine) as db, db.begin():
            db.add(User(id=1, nickname='测试用户'))
            db.add(Pet(id=1, user_id=1, name='团团'))
            db.add(MediaUpload(id=self.media_id, pet_id=1, content_type='image/png', size_bytes=1024,
                               expires_at=utcnow() + timedelta(minutes=10), version_id='v-photo'))
            db.add(Task(id=self.task_id, pet_id=1, type='motion_batch', status='pending',
                        request_key=uuid4().hex, attempts=0,
                        payload={'media_id': self.media_id, 'config_version': 'mo-test'}))

    def context(self):
        return {'engine': self.engine, 'assets': self.assets, 'motion_config': small_config(),
                'motion_provider': PlaceholderMotionProvider(**SMALL)}

    def test_run_task_succeeds(self):
        asyncio.run(worker.run_task(self.context(), self.task_id))
        with Session(self.engine) as db:
            task = db.get(Task, self.task_id)
            self.assertEqual(task.status, 'succeeded')
            self.assertTrue(task.result['usable'])
            self.assertIn(task.result['base_image']['key'], self.assets.objects)

    def test_provider_failure_retries(self):
        class BrokenProvider:
            async def enchant(self, photo, *, prompt):
                raise RuntimeError('provider down')

            async def animate(self, image, *, prompt, seconds):
                raise RuntimeError('provider down')

        context = self.context()
        context['motion_provider'] = BrokenProvider()
        asyncio.run(worker.run_task(context, self.task_id))
        with Session(self.engine) as db:
            task = db.get(Task, self.task_id)
            self.assertEqual(task.status, 'pending')
            self.assertEqual(task.attempts, 1)


if __name__ == '__main__':
    unittest.main()
