"""T17 F12-4: account deletion, login freeze and 15-day physical purge."""

import unittest
from datetime import timedelta

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from test_auth_api import AuthAPIFixture

from app.core.security import utcnow
from app.models import (
    AiUsageLog,
    AuthSession,
    Base,
    ChatMessage,
    ChatSession,
    Consent,
    DeletionJob,
    DietRecord,
    HealthScreening,
    MediaUpload,
    Pet,
    RefreshToken,
    RequestIdempotency,
    Task,
    User,
    UserCredential,
    WeightRecord,
)
from app.services.consents import grant_consent
from app.services.identity import create_email_account, verify_email
from app.services.privacy import PURGE_DELAY, purge_due, purge_user_data, request_deletion
from app.services.sessions import create_session
from app.services.tasks import enqueue_task


class FakePurgeClient:
    def __init__(self):
        self.deletes = []

    def delete_object(self, **kwargs):
        self.deletes.append(kwargs)
        return {}


class FakePurgeStorage:
    def __init__(self):
        self.bucket = 'test-bucket'
        self.client = FakePurgeClient()


class PrivacyAPITests(AuthAPIFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        tokens = self.login().json()
        self.access = tokens['access_token']
        self.refresh_token = tokens['refresh_token']
        self.headers = {'Authorization': f'Bearer {self.access}'}
        self.client.post('/api/v1/consents', json={'privacy': 'p1', 'terms': 't1'}, headers=self.headers)
        self.pet_id = self.client.post('/api/v1/pets', json={'name': '团团'}, headers=self.headers).json()['id']

    def delete_me(self):
        return self.client.delete('/api/v1/me', headers=self.headers)

    def test_delete_me_requires_auth(self):
        self.assertEqual(self.client.delete('/api/v1/me').status_code, 401)

    def test_delete_me_schedules_purge_and_freezes_account(self):
        before = utcnow()
        response = self.delete_me()
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        body = response.json()
        self.assertEqual(body['status'], 'pending')
        purge_after = body['purge_after']
        with Session(self.engine) as db:
            job = db.scalar(select(DeletionJob))
            self.assertIsNotNone(job)
            self.assertEqual(job.status, 'pending')
            self.assertEqual(job.purge_after.isoformat(), purge_after)
            self.assertGreaterEqual(job.purge_after, before + PURGE_DELAY - timedelta(seconds=5))
            self.assertLessEqual(job.purge_after, before + PURGE_DELAY + timedelta(seconds=5))
            user = db.scalar(select(User).where(User.id == job.user_id))
            self.assertEqual(user.status, 'deletion_pending')
            sessions = db.scalars(select(AuthSession).where(AuthSession.user_id == user.id)).all()
            self.assertTrue(sessions)
            self.assertTrue(all(s.revoked_at is not None for s in sessions))

    def test_delete_me_is_idempotent(self):
        first = self.delete_me()
        second = self.delete_me()
        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()['purge_after'], first.json()['purge_after'])
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(DeletionJob)), 1)

    def test_frozen_account_rejects_login_refresh_and_access(self):
        self.delete_me()
        self.assertEqual(self.login().status_code, 401)
        self.assertEqual(self.refresh(self.refresh_token).status_code, 401)
        self.assertEqual(self.me(self.access).status_code, 401)

    def test_data_retained_in_db_until_purge(self):
        self.delete_me()
        with Session(self.engine) as db:
            self.assertIsNotNone(db.scalar(select(Pet).where(Pet.id == self.pet_id)))
            self.assertIsNotNone(db.scalar(select(User).where(User.status == 'deletion_pending')))

    def test_other_user_can_still_login(self):
        with Session(self.engine) as db, db.begin():
            token = create_email_account(db, 'other@example.com', self.password, self.now)
            verify_email(db, token, self.now)
        self.delete_me()
        self.assertEqual(self.login('other@example.com').status_code, 200)


def make_engine():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return engine


class PurgeFixture(unittest.TestCase):
    def setUp(self):
        self.engine = make_engine()
        self.addCleanup(self.engine.dispose)
        self.now = utcnow()
        self.storage = FakePurgeStorage()
        with Session(self.engine) as db, db.begin():
            token = create_email_account(db, 'purge@example.com', 'Strong123', self.now)
            verify_email(db, token, self.now)
            credential = db.scalar(select(UserCredential).where(UserCredential.identifier == 'purge@example.com'))
            self.user_id = credential.user_id
            create_session(db, self.user_id, self.now)
            grant_consent(db, self.user_id, 'privacy', 'p1', True)
            pet = Pet(user_id=self.user_id, name='团团')
            db.add(pet)
            db.flush()
            self.pet_id = pet.id
            media = MediaUpload(
                id='a' * 32,
                pet_id=self.pet_id,
                kind='photo',
                content_type='image/png',
                size_bytes=10,
                expires_at=self.now + timedelta(hours=1),
                version_id='mv1',
            )
            db.add(media)
            task = enqueue_task(db, self.pet_id, 'avatar_batch', 'key-1', {'media_id': media.id})
            task.status = 'succeeded'
            task.result = {
                'base_image': {'key': f'avatars/{self.pet_id}/{task.id}/base.png', 'version_id': 'bv1'},
                'clips': {
                    'idle': {
                        'status': 'ready',
                        'key': f'avatars/{self.pet_id}/{task.id}/idle.mp4',
                        'version_id': 'cv1',
                    },
                    'happy': {'status': 'failed'},
                },
                'ready_count': 1,
                'usable': False,
            }
            self.task_id = task.id
            chat = ChatSession(pet_id=self.pet_id, user_id=self.user_id)
            db.add(chat)
            db.flush()
            db.add(ChatMessage(session_id=chat.id, role='user', kind='text', content='你好', task_id=task.id))
            db.add(
                HealthScreening(
                    pet_id=self.pet_id,
                    user_id=self.user_id,
                    state='observe',
                    spirit='normal',
                    appetite='normal',
                    triage_json={},
                    rules_version='sx-1',
                    task_id=task.id,
                )
            )
            db.add(DietRecord(pet_id=self.pet_id, food_type='dry', amount_g=50, fed_at=self.now))
            db.add(WeightRecord(pet_id=self.pet_id, weight_kg=4.0, measured_at=self.now))
            db.add(
                AiUsageLog(
                    user_id=self.user_id,
                    task_id=task.id,
                    provider='fake',
                    model='fake',
                    kind='llm',
                    tokens_in=10,
                    tokens_out=5,
                )
            )
            db.add(RequestIdempotency(user_id=self.user_id, key='k1', request_hash='h1'))
            other = create_email_account(db, 'keep@example.com', 'Strong123', self.now)
            verify_email(db, other, self.now)
            other_cred = db.scalar(select(UserCredential).where(UserCredential.identifier == 'keep@example.com'))
            self.other_user_id = other_cred.user_id
            db.add(Pet(user_id=self.other_user_id, name='保留'))
            self.job, created = request_deletion(db, self.user_id, now=self.now)
            self.assertTrue(created)
            self.job_id = self.job.id
            self.purge_after = self.job.purge_after

    def purge(self, now=None, storage=None):
        with Session(self.engine) as db, db.begin():
            return purge_user_data(
                db, self.user_id, storage=storage or self.storage, now=now or self.purge_after + timedelta(seconds=1)
            )


class PurgeTests(PurgeFixture):
    def test_not_due_job_is_not_purged(self):
        self.assertFalse(self.purge(now=self.purge_after - timedelta(seconds=1)))
        with Session(self.engine) as db:
            self.assertIsNotNone(db.get(User, self.user_id))

    def test_missing_storage_raises_for_retry(self):
        with self.assertRaises(RuntimeError):
            with Session(self.engine) as db, db.begin():
                purge_user_data(db, self.user_id, storage=None, now=self.purge_after + timedelta(seconds=1))
        with Session(self.engine) as db:
            self.assertIsNotNone(db.get(User, self.user_id))

    def test_purge_removes_all_user_data_and_oss_objects(self):
        self.assertTrue(self.purge())
        with Session(self.engine) as db:
            for model in (
                Task,
                MediaUpload,
                ChatSession,
                ChatMessage,
                HealthScreening,
                DietRecord,
                WeightRecord,
                Consent,
                AuthSession,
                RequestIdempotency,
                DeletionJob,
            ):
                self.assertEqual(db.scalar(select(func.count()).select_from(model)), 0, model.__name__)
            self.assertEqual(db.scalar(select(func.count()).select_from(RefreshToken)), 0)
            self.assertIsNone(db.get(User, self.user_id))
            self.assertIsNone(db.scalar(select(UserCredential).where(UserCredential.user_id == self.user_id)))
            self.assertIsNone(db.scalar(select(Pet).where(Pet.user_id == self.user_id)))
            self.assertIsNotNone(db.get(User, self.other_user_id))
            logs = db.scalars(select(AiUsageLog)).all()
            self.assertEqual(len(logs), 1)
            self.assertIsNone(logs[0].user_id)
            self.assertIsNone(logs[0].task_id)
            self.assertEqual(logs[0].tokens_in, 10)
            self.assertIsNotNone(db.scalar(select(Pet).where(Pet.user_id == self.other_user_id)))
        keys = {(d['Key'], d.get('VersionId')) for d in self.storage.client.deletes}
        self.assertIn((f'photos/{self.pet_id}/{"a" * 32}', 'mv1'), keys)
        self.assertIn((f'avatars/{self.pet_id}/{self.task_id}/base.png', 'bv1'), keys)
        self.assertIn((f'avatars/{self.pet_id}/{self.task_id}/idle.mp4', 'cv1'), keys)
        self.assertEqual(len(keys), 3)
        self.assertTrue(all(d['Bucket'] == 'test-bucket' for d in self.storage.client.deletes))

    def test_purge_without_prior_request_is_noop(self):
        with Session(self.engine) as db, db.begin():
            db.delete(db.get(DeletionJob, self.job_id))
        self.assertFalse(self.purge())
        with Session(self.engine) as db:
            self.assertIsNotNone(db.get(User, self.user_id))

    def test_purge_due_sweep_processes_only_due_jobs(self):
        purged = purge_due(self.engine, storage=self.storage, now=self.purge_after - timedelta(seconds=1))
        self.assertEqual(purged, [])
        purged = purge_due(self.engine, storage=self.storage, now=self.purge_after + timedelta(seconds=1))
        self.assertEqual(purged, [self.user_id])
        with Session(self.engine) as db:
            self.assertIsNone(db.get(User, self.user_id))
            self.assertIsNotNone(db.get(User, self.other_user_id))


class TrainingConsentTests(AuthAPIFixture, unittest.TestCase):
    """F12-3：训练同意默认 false、单独授权、拒绝不影响功能。"""

    def setUp(self):
        super().setUp()
        self.headers = {'Authorization': f'Bearer {self.login().json()["access_token"]}'}
        self.client.post('/api/v1/consents', json={'privacy': 'p1', 'terms': 't1'}, headers=self.headers)

    def test_training_defaults_to_false(self):
        state = self.client.get('/api/v1/consents', headers=self.headers).raise_for_status().json()
        self.assertTrue(state['granted'])
        self.assertFalse(state['training_granted'])

    def test_training_grant_and_revoke(self):
        granted = self.client.post('/api/v1/consents/training', json={'granted': True}, headers=self.headers)
        self.assertEqual(granted.status_code, 200)
        self.assertTrue(granted.json()['training_granted'])
        state = self.client.get('/api/v1/consents', headers=self.headers).raise_for_status().json()
        self.assertTrue(state['training_granted'])
        revoked = self.client.post('/api/v1/consents/training', json={'granted': False}, headers=self.headers)
        self.assertFalse(revoked.json()['training_granted'])
        state = self.client.get('/api/v1/consents', headers=self.headers).raise_for_status().json()
        self.assertFalse(state['training_granted'])
        self.assertTrue(state['granted'])  # 拒绝训练不影响基础功能同意

    def test_training_requires_basic_consent(self):
        with Session(self.engine) as db, db.begin():
            token = create_email_account(db, 'noconsent-training@example.com', self.password, self.now)
            verify_email(db, token, self.now)
        headers = {'Authorization': f'Bearer {self.login("noconsent-training@example.com").json()["access_token"]}'}
        response = self.client.post('/api/v1/consents/training', json={'granted': True}, headers=headers)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['code'], 'CONSENT_REQUIRED')

    def test_training_requires_auth(self):
        self.assertEqual(self.client.post('/api/v1/consents/training', json={'granted': True}).status_code, 401)

    def test_training_rejects_extra_fields(self):
        response = self.client.post(
            '/api/v1/consents/training', json={'granted': True, 'version': 'x'}, headers=self.headers
        )
        self.assertEqual(response.status_code, 400)


if __name__ == '__main__':
    unittest.main()
