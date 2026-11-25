"""读取分身结果（ARCHITECTURE：GET /pets/{id}/avatar 底图+片段+状态）。"""

import unittest
from datetime import timedelta
from uuid import uuid4

from sqlalchemy.orm import Session
from test_auth_api import AuthAPIFixture

from app.core.security import utcnow
from app.models import Task

ACTIONS = ('idle', 'happy', 'sad', 'sick', 'crouch', 'look_left', 'look_right')


class FakeStorage:
    def asset_url(self, key, version_id):
        return f'https://fake.local/{key}?v={version_id}'


def make_result(ready_actions=ACTIONS):
    clips = {}
    for action in ACTIONS:
        if action in ready_actions:
            clips[action] = {'status': 'ready', 'key': f'avatars/1/task/{action}.mp4', 'version_id': f'v-{action}'}
        else:
            clips[action] = {'status': 'failed'}
    return {
        'base_image': {'key': 'avatars/1/task/base.png', 'version_id': 'v-base'},
        'clips': clips,
        'ready_count': len(ready_actions),
        'usable': len(ready_actions) >= 5,
    }


class AvatarReadTests(AuthAPIFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.headers = {'Authorization': f'Bearer {self.login().json()["access_token"]}'}
        self.client.post(
            '/api/v1/consents', headers=self.headers, json={'privacy': 'p1', 'terms': 't1'}
        ).raise_for_status()
        self.pet_id = self.client.post('/api/v1/pets', headers=self.headers, json={'name': '团团'}).json()['id']
        self.client.app.state.photo_storage = FakeStorage()

    def insert_task(self, status, result=None, pet_id=None, created_at=None):
        task_id = uuid4().hex
        with Session(self.engine) as db, db.begin():
            db.add(
                Task(
                    id=task_id,
                    pet_id=pet_id if pet_id is not None else self.pet_id,
                    type='avatar_batch',
                    status=status,
                    request_key=uuid4().hex,
                    payload={'media_id': uuid4().hex},
                    result=result,
                    attempts=1,
                    created_at=created_at if created_at is not None else utcnow(),
                )
            )
        return task_id

    def read(self, pet_id=None, headers=None):
        return self.client.get(
            f'/api/v1/pets/{pet_id if pet_id is not None else self.pet_id}/avatar',
            headers=self.headers if headers is None else headers,
        )

    def test_requires_login(self):
        self.assertEqual(self.read(headers={}).status_code, 401)

    def test_requires_consent(self):
        from app.services.identity import create_email_account

        with Session(self.engine) as db, db.begin():
            create_email_account(db, 'noconsent3@example.com', self.password, self.now)
        headers = {'Authorization': f'Bearer {self.login("noconsent3@example.com").json()["access_token"]}'}
        response = self.read(headers=headers)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['code'], 'CONSENT_REQUIRED')

    def test_never_submitted_404(self):
        response = self.read()
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['code'], 'NOT_FOUND')

    def test_pending_task_returns_placeholder_fallback(self):
        task_id = self.insert_task('pending')
        response = self.read()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        body = response.json()
        self.assertEqual(body['task_id'], task_id)
        self.assertEqual(body['status'], 'pending')
        self.assertIsNone(body['base_image'])
        self.assertFalse(body['usable'])
        self.assertEqual(body['ready_count'], 0)
        self.assertEqual(set(body['clips']), set(ACTIONS))
        self.assertTrue(all(clip == {'status': 'pending', 'url': None} for clip in body['clips'].values()))
        self.assertEqual(body['placeholder_manifest']['body_type'], 'standard')

    def test_failed_task_marks_clips_failed(self):
        self.insert_task('failed')
        body = self.read().json()
        self.assertEqual(body['status'], 'failed')
        self.assertTrue(all(clip['status'] == 'failed' for clip in body['clips'].values()))
        self.assertFalse(body['usable'])

    def test_succeeded_task_presigns_assets(self):
        task_id = self.insert_task('succeeded', make_result(ready_actions=('idle', 'happy', 'sad', 'sick', 'crouch')))
        body = self.read().json()
        self.assertEqual(body['task_id'], task_id)
        self.assertEqual(body['status'], 'succeeded')
        self.assertEqual(body['base_image']['url'], 'https://fake.local/avatars/1/task/base.png?v=v-base')
        self.assertEqual(body['ready_count'], 5)
        self.assertTrue(body['usable'])
        self.assertEqual(body['clips']['idle']['url'], 'https://fake.local/avatars/1/task/idle.mp4?v=v-idle')
        self.assertEqual(body['clips']['look_left'], {'status': 'failed', 'url': None})

    def test_succeeded_without_storage_503(self):
        self.insert_task('succeeded', make_result())
        self.client.app.state.photo_storage = None
        response = self.read()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['code'], 'MEDIA_UNAVAILABLE')

    def test_latest_task_wins(self):
        self.insert_task('failed', created_at=utcnow() - timedelta(minutes=1))
        latest = self.insert_task('succeeded', make_result())
        body = self.read().json()
        self.assertEqual(body['task_id'], latest)
        self.assertEqual(body['status'], 'succeeded')

    def test_other_users_pet_404(self):
        from app.services.identity import create_email_account

        with Session(self.engine) as db, db.begin():
            create_email_account(db, 'other@example.com', self.password, self.now)
        headers = {'Authorization': f'Bearer {self.login("other@example.com").json()["access_token"]}'}
        self.client.post('/api/v1/consents', headers=headers, json={'privacy': 'p1', 'terms': 't1'}).raise_for_status()
        self.insert_task('succeeded', make_result())
        self.assertEqual(self.read(headers=headers).status_code, 404)


if __name__ == '__main__':
    unittest.main()
