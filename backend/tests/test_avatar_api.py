import unittest
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session
from test_auth_api import AuthAPIFixture

from app.core.security import utcnow
from app.models import MediaUpload, Task
from app.services.identity import create_email_account
from app.services.tasks import claim_task, finish_task


class AvatarAPITests(AuthAPIFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.headers = {'Authorization': f'Bearer {self.login().json()["access_token"]}'}
        self.client.post(
            '/api/v1/consents', headers=self.headers, json={'privacy': 'p1', 'terms': 't1'}
        ).raise_for_status()
        self.pet_id = self.client.post('/api/v1/pets', headers=self.headers, json={'name': '团团'}).json()['id']

    def make_media(self, pet_id=None, verified=True):
        media_id = uuid4().hex
        with Session(self.engine) as db, db.begin():
            db.add(
                MediaUpload(
                    id=media_id,
                    pet_id=pet_id if pet_id is not None else self.pet_id,
                    content_type='image/png',
                    size_bytes=1024,
                    expires_at=utcnow() + timedelta(minutes=10),
                    version_id='version-1' if verified else None,
                )
            )
        return media_id

    def submit(self, media_id, pet_id=None, headers=None):
        return self.client.post(
            f'/api/v1/pets/{pet_id if pet_id is not None else self.pet_id}/avatar',
            json={'media_id': media_id},
            headers=self.headers if headers is None else headers,
        )

    def verified_account(self, email, consent=True):
        with Session(self.engine) as db, db.begin():
            create_email_account(db, email, self.password, self.now)
        headers = {'Authorization': f'Bearer {self.login(email).json()["access_token"]}'}
        if consent:
            self.client.post(
                '/api/v1/consents', headers=headers, json={'privacy': 'p1', 'terms': 't1'}
            ).raise_for_status()
        return headers

    def test_requires_login(self):
        response = self.submit(self.make_media(), headers={})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['code'], 'AUTH_REQUIRED')

    def test_requires_consent(self):
        headers = self.verified_account('noconsent@example.com', consent=False)
        response = self.submit(self.make_media(), headers=headers)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['code'], 'CONSENT_REQUIRED')

    def test_unknown_pet_is_not_found(self):
        response = self.submit(self.make_media(), pet_id=999999)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['code'], 'NOT_FOUND')

    def test_other_users_pet_is_not_found(self):
        headers = self.verified_account('other@example.com')
        other_pet = self.client.post('/api/v1/pets', headers=headers, json={'name': '别的猫'}).json()['id']
        response = self.submit(self.make_media(), pet_id=other_pet)
        self.assertEqual(response.status_code, 404)
        response = self.submit(self.make_media(pet_id=other_pet), headers=headers)
        self.assertEqual(response.status_code, 404)

    def test_media_from_another_pet_is_not_found(self):
        second_pet = self.client.post('/api/v1/pets', headers=self.headers, json={'name': '二猫'}).json()['id']
        response = self.submit(self.make_media(pet_id=second_pet))
        self.assertEqual(response.status_code, 404)

    def test_unverified_media_is_rejected(self):
        response = self.submit(self.make_media(verified=False))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['code'], 'MEDIA_NOT_VERIFIED')

    def test_invalid_body_is_rejected(self):
        self.assertEqual(self.submit('not-a-media-id').status_code, 400)
        response = self.client.post(
            f'/api/v1/pets/{self.pet_id}/avatar', headers=self.headers, json={'media_id': self.make_media(), 'extra': 1}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'VALIDATION_ERROR')

    def test_submission_creates_pending_avatar_task(self):
        media_id = self.make_media()
        response = self.submit(media_id)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        body = response.json()
        self.assertRegex(body['task_id'], r'^[0-9a-f]{32}$')
        self.assertEqual(body['status'], 'pending')
        with Session(self.engine) as db:
            task = db.get(Task, body['task_id'])
            self.assertEqual(
                (task.pet_id, task.type, task.payload), (self.pet_id, 'avatar_batch', {'media_id': media_id})
            )
        polled = self.client.get(f'/api/v1/tasks/{body["task_id"]}', headers=self.headers)
        self.assertEqual(polled.status_code, 200)
        self.assertEqual(polled.json()['status'], 'pending')

    def test_same_media_submission_is_idempotent(self):
        media_id = self.make_media()
        first, second = self.submit(media_id), self.submit(media_id)
        self.assertEqual(first.status_code, 202)
        self.assertEqual(first.json()['task_id'], second.json()['task_id'])
        with Session(self.engine) as db:
            self.assertEqual(len(db.scalars(select(Task).where(Task.pet_id == self.pet_id)).all()), 1)

    def test_concurrent_submission_merges_into_in_progress_task(self):
        first = self.submit(self.make_media()).json()
        second = self.submit(self.make_media()).json()
        self.assertEqual(first['task_id'], second['task_id'])
        with Session(self.engine) as db:
            self.assertEqual(len(db.scalars(select(Task).where(Task.pet_id == self.pet_id)).all()), 1)

    def test_new_media_after_success_creates_new_task(self):
        first = self.submit(self.make_media()).json()
        with Session(self.engine) as db, db.begin():
            attempt = claim_task(db, first['task_id'])
            self.assertTrue(finish_task(db, first['task_id'], attempt, result={'ok': True}))
        second = self.submit(self.make_media()).json()
        self.assertNotEqual(first['task_id'], second['task_id'])
        self.assertEqual(second['status'], 'pending')

    def test_succeeded_task_is_returned_with_result(self):
        media_id = self.make_media()
        first = self.submit(media_id).json()
        with Session(self.engine) as db, db.begin():
            attempt = claim_task(db, first['task_id'])
            self.assertTrue(finish_task(db, first['task_id'], attempt, result={'ok': True}))
        again = self.submit(media_id)
        self.assertEqual(again.json()['task_id'], first['task_id'])
        self.assertEqual(again.json()['status'], 'succeeded')
        polled = self.client.get(f'/api/v1/tasks/{first["task_id"]}', headers=self.headers).json()
        self.assertEqual(polled['result'], {'ok': True})

    def test_failed_task_requeues_when_user_resubmits(self):
        media_id = self.make_media()
        first = self.submit(media_id).json()
        with Session(self.engine) as db:
            for _ in range(3):
                with db.begin():
                    attempt = claim_task(db, first['task_id'])
                    self.assertIsNotNone(attempt)
                    self.assertTrue(finish_task(db, first['task_id'], attempt))
        with Session(self.engine) as db:
            self.assertEqual(db.get(Task, first['task_id']).status, 'failed')
        again = self.submit(media_id)
        self.assertEqual(again.status_code, 202)
        self.assertEqual(again.json()['task_id'], first['task_id'])
        self.assertEqual(again.json()['status'], 'pending')
        with Session(self.engine) as db:
            task = db.get(Task, first['task_id'])
            self.assertEqual((task.attempts, task.lease_until), (0, None))


if __name__ == '__main__':
    unittest.main()
