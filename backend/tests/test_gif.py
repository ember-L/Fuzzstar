"""T17 F13 GIF 导出（480p≤5s、水印「绒星 · AI 参考」、仅导出运行时不播）。"""

import asyncio
import json
import os
import subprocess
import unittest
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from test_auth_api import AuthAPIFixture
from test_avatar_read import FakeStorage, make_result
from test_worker import FakeAssets

from app import worker
from app.core.security import utcnow
from app.models import Base, Pet, Task, User
from app.services import gif

BACKEND = Path(__file__).resolve().parents[1]
CLIP_PATH = BACKEND / 'assets' / 'placeholders' / 'standard' / 'idle.mp4'


def probe(path):
    out = subprocess.run(
        [
            'ffprobe',
            '-v',
            'error',
            '-show_entries',
            'format=format_name,duration',
            '-show_entries',
            'stream=codec_type,width,height',
            '-of',
            'json',
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return json.loads(out)


class GifLogicTests(unittest.TestCase):
    def test_resolve_font_env_override(self):
        with TemporaryDirectory() as tmp:
            font = Path(tmp) / 'font.ttc'
            font.write_bytes(b'dummy')
            with patch.dict(os.environ, {'GIF_WATERMARK_FONT': str(font)}):
                self.assertEqual(gif.resolve_watermark_font(), str(font))

    def test_resolve_font_missing_raises(self):
        with patch.object(gif, 'FONT_CANDIDATES', []), patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                gif.resolve_watermark_font()

    def test_build_filter_watermark_and_spec(self):
        text = gif.build_gif_filter('/tmp/font.ttc')
        for fragment in ('drawtext', '绒星 · AI 参考', 'scale=-2:480', 'palettegen', 'fps=12'):
            self.assertIn(fragment, text)

    def test_export_gif_spec(self):
        assets = FakeAssets()
        assets.objects['avatars/1/task/idle.mp4'] = (CLIP_PATH.read_bytes(), 'video/mp4', 'v-idle')
        task = SimpleNamespace(
            pet_id=1,
            id='b' * 32,
            payload={
                'avatar_task_id': 'a' * 32,
                'action': 'idle',
                'clip_key': 'avatars/1/task/idle.mp4',
                'clip_version_id': 'v-idle',
            },
        )
        result = asyncio.run(gif.export_gif(task, assets=assets))
        key = f'gifs/1/{"b" * 32}/idle.gif'
        self.assertEqual(result['key'], key)
        data, content_type, version = assets.objects[key]
        self.assertEqual(content_type, 'image/gif')
        self.assertEqual(result['version_id'], version)
        self.assertEqual(result['bytes'], len(data))
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / 'out.gif'
            out.write_bytes(data)
            info = probe(out)
            self.assertIn('gif', info['format']['format_name'])
            video = next(s for s in info['streams'] if s['codec_type'] == 'video')
            self.assertEqual(video['height'], 480)
            self.assertLessEqual(float(info['format']['duration']), 5.0)


class GifAPITests(AuthAPIFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.headers = {'Authorization': f'Bearer {self.login().json()["access_token"]}'}
        self.client.post(
            '/api/v1/consents', headers=self.headers, json={'privacy': 'p1', 'terms': 't1'}
        ).raise_for_status()
        self.pet_id = self.client.post('/api/v1/pets', headers=self.headers, json={'name': '团团'}).json()['id']

    def insert_avatar(self, status='succeeded', result=None, created_at=None):
        task_id = uuid4().hex
        with Session(self.engine) as db, db.begin():
            db.add(
                Task(
                    id=task_id,
                    pet_id=self.pet_id,
                    type='avatar_batch',
                    status=status,
                    request_key=uuid4().hex,
                    payload={'media_id': uuid4().hex},
                    result=result if result is not None else make_result(),
                    attempts=1,
                    created_at=created_at if created_at is not None else utcnow(),
                )
            )
        return task_id

    def share(self, action='idle', pet_id=None, headers=None):
        return self.client.post(
            f'/api/v1/pets/{pet_id if pet_id is not None else self.pet_id}/share/gif',
            json={'action': action},
            headers=self.headers if headers is None else headers,
        )

    def test_requires_login(self):
        self.assertEqual(self.share(headers={}).status_code, 401)

    def test_requires_consent(self):
        from app.services.identity import create_email_account, verify_email

        with Session(self.engine) as db, db.begin():
            token = create_email_account(db, 'noconsent-gif@example.com', self.password, self.now)
            verify_email(db, token, self.now)
        headers = {'Authorization': f'Bearer {self.login("noconsent-gif@example.com").json()["access_token"]}'}
        response = self.share(headers=headers)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['code'], 'CONSENT_REQUIRED')

    def test_unknown_pet_404(self):
        self.assertEqual(self.share(pet_id=999999).status_code, 404)

    def test_no_avatar_404(self):
        response = self.share()
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['code'], 'NOT_FOUND')

    def test_action_not_ready_409(self):
        self.insert_avatar(result=make_result(ready_actions=('idle',)), created_at=utcnow() - timedelta(minutes=1))
        response = self.share('happy')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['code'], 'AVATAR_NOT_READY')
        self.insert_avatar(status='pending', result=None)
        self.assertEqual(self.share('idle').status_code, 409)

    def test_invalid_action_400(self):
        self.insert_avatar()
        response = self.share('dance')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'VALIDATION_ERROR')

    def test_share_success_merge_and_distinct_actions(self):
        avatar_id = self.insert_avatar()
        first = self.share('idle')
        self.assertEqual(first.status_code, 202)
        self.assertEqual(first.json()['status'], 'pending')
        merge = self.share('idle')
        self.assertEqual(merge.status_code, 200)
        self.assertEqual(merge.json()['task_id'], first.json()['task_id'])
        other = self.share('happy')
        self.assertEqual(other.status_code, 202)
        self.assertNotEqual(other.json()['task_id'], first.json()['task_id'])
        with Session(self.engine) as db:
            task = db.get(Task, first.json()['task_id'])
            self.assertEqual(task.type, 'gif_export')
            self.assertEqual(task.payload['avatar_task_id'], avatar_id)
            self.assertEqual(task.payload['clip_key'], 'avatars/1/task/idle.mp4')
            self.assertEqual(task.payload['clip_version_id'], 'v-idle')

    def test_other_users_pet_404(self):
        from app.services.identity import create_email_account, verify_email

        self.insert_avatar()
        with Session(self.engine) as db, db.begin():
            token = create_email_account(db, 'other-gif@example.com', self.password, self.now)
            verify_email(db, token, self.now)
        headers = {'Authorization': f'Bearer {self.login("other-gif@example.com").json()["access_token"]}'}
        self.client.post('/api/v1/consents', headers=headers, json={'privacy': 'p1', 'terms': 't1'}).raise_for_status()
        self.assertEqual(self.share(headers=headers).status_code, 404)

    def test_failed_task_requeues_on_resubmit(self):
        self.insert_avatar()
        first = self.share('idle')
        task_id = first.json()['task_id']
        with Session(self.engine) as db, db.begin():
            db.get(Task, task_id).status = 'failed'
        again = self.share('idle')
        self.assertEqual(again.status_code, 202)
        self.assertEqual(again.json()['task_id'], task_id)
        self.assertEqual(again.json()['status'], 'pending')

    def test_task_download_url_for_succeeded_gif(self):
        task_id = uuid4().hex
        with Session(self.engine) as db, db.begin():
            db.add(
                Task(
                    id=task_id,
                    pet_id=self.pet_id,
                    type='gif_export',
                    status='succeeded',
                    request_key=uuid4().hex,
                    payload={'action': 'idle'},
                    result={'key': 'gifs/1/x/idle.gif', 'version_id': 'gv', 'bytes': 10},
                    attempts=1,
                )
            )
        self.client.app.state.photo_storage = FakeStorage()
        body = self.client.get(f'/api/v1/tasks/{task_id}', headers=self.headers).raise_for_status().json()
        self.assertEqual(body['download_url'], 'https://fake.local/gifs/1/x/idle.gif?v=gv')
        self.client.app.state.photo_storage = None
        response = self.client.get(f'/api/v1/tasks/{task_id}', headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['code'], 'MEDIA_UNAVAILABLE')


class GifWorkerTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.assets = FakeAssets()
        self.assets.objects['avatars/1/task/idle.mp4'] = (CLIP_PATH.read_bytes(), 'video/mp4', 'v-idle')
        self.task_id = uuid4().hex
        with Session(self.engine) as db, db.begin():
            db.add(User(id=1, nickname='测试用户'))
            db.add(Pet(id=1, user_id=1, name='团团'))
            db.add(
                Task(
                    id=self.task_id,
                    pet_id=1,
                    type='gif_export',
                    status='pending',
                    request_key=uuid4().hex,
                    attempts=0,
                    payload={
                        'avatar_task_id': 'a' * 32,
                        'action': 'idle',
                        'clip_key': 'avatars/1/task/idle.mp4',
                        'clip_version_id': 'v-idle',
                    },
                )
            )

    def test_run_task_gif_export_succeeds(self):
        asyncio.run(worker.run_task({'engine': self.engine, 'assets': self.assets}, self.task_id))
        with Session(self.engine) as db:
            task = db.get(Task, self.task_id)
            self.assertEqual(task.status, 'succeeded')
            self.assertEqual(task.result['key'], f'gifs/1/{self.task_id}/idle.gif')
            self.assertIn(task.result['key'], self.assets.objects)

    def test_missing_clip_retries(self):
        self.assets.objects.clear()
        asyncio.run(worker.run_task({'engine': self.engine, 'assets': self.assets}, self.task_id))
        with Session(self.engine) as db:
            task = db.get(Task, self.task_id)
            self.assertEqual(task.status, 'pending')
            self.assertEqual(task.attempts, 1)


if __name__ == '__main__':
    unittest.main()
