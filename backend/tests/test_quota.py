"""T17 F11 每日配额与只读权益（FRD F11-1/2/3，AC-11-1/2/3）。"""
import unittest
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.security import utcnow
from app.models import Base, MediaUpload, UsageCounter, User
from app.providers.fake import FakeLLMProvider
from app.services.quota import QuotaExceeded, consume_quota, quota_limits, quota_snapshot
from test_auth_api import AuthAPIFixture


def make_engine():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return engine


class QuotaLogicTests(unittest.TestCase):
    def setUp(self):
        self.engine = make_engine()
        with Session(self.engine) as db, db.begin():
            db.add(User(id=1, nickname='测试用户'))
        self.now = utcnow()

    def test_limits_defaults_and_env_hot_adjust(self):
        self.assertEqual(quota_limits({}), {'screening': 10, 'avatar_gen': 3, 'chat_msg': 50})
        self.assertEqual(quota_limits({'QUOTA_SCREENING': '2'})['screening'], 2)
        self.assertEqual(quota_limits({'QUOTA_SCREENING': 'abc'})['screening'], 10)
        self.assertEqual(quota_limits({'QUOTA_SCREENING': '0'})['screening'], 10)

    def test_consume_increments_and_raises_over_limit(self):
        with Session(self.engine) as db, db.begin():
            for i in range(10):
                self.assertEqual(consume_quota(db, 1, 'screening', now=self.now, env={}), i + 1)
        with Session(self.engine) as db, db.begin():
            with self.assertRaises(QuotaExceeded) as ctx:
                consume_quota(db, 1, 'screening', now=self.now, env={})
            self.assertEqual(ctx.exception.metric, 'screening')
            self.assertEqual(ctx.exception.limit, 10)
            db.rollback()
        with Session(self.engine) as db:
            count = db.scalar(select(UsageCounter.count).where(UsageCounter.user_id == 1,
                                                               UsageCounter.metric == 'screening'))
            self.assertEqual(count, 10)

    def test_consume_resets_on_new_day(self):
        yesterday = self.now - timedelta(days=1)
        with Session(self.engine) as db, db.begin():
            for _ in range(10):
                consume_quota(db, 1, 'screening', now=yesterday, env={})
        with Session(self.engine) as db, db.begin():
            self.assertEqual(consume_quota(db, 1, 'screening', now=self.now, env={}), 1)

    def test_snapshot_matches_counters(self):
        with Session(self.engine) as db, db.begin():
            for _ in range(3):
                consume_quota(db, 1, 'screening', now=self.now, env={})
            consume_quota(db, 1, 'avatar_gen', now=self.now, env={})
            snap = quota_snapshot(db, 1, now=self.now, env={})
        self.assertEqual(snap['day'], self.now.date().isoformat())
        self.assertEqual(snap['metrics']['screening'], {'used': 3, 'limit': 10})
        self.assertEqual(snap['metrics']['avatar_gen'], {'used': 1, 'limit': 3})
        self.assertEqual(snap['metrics']['chat_msg'], {'used': 0, 'limit': 50})


class QuotaFixture(AuthAPIFixture):
    def setUp(self):
        super().setUp()
        self.headers = {'Authorization': f"Bearer {self.login().json()['access_token']}"}
        self.client.post('/api/v1/consents', headers=self.headers, json={'privacy': 'p1', 'terms': 't1'}).raise_for_status()
        self.pet_id = self.client.post('/api/v1/pets', headers=self.headers, json={'name': '团团'}).json()['id']
        self.app.state.chat_llm_provider = FakeLLMProvider(reply='{"reply": "喵～我在呢", "emotion": "happy"}')
        self.session_id = self.client.post(f'/api/v1/pets/{self.pet_id}/chat/sessions',
                                           headers=self.headers).json()['session_id']

    @property
    def app(self):
        return self.client.app

    def quota(self):
        return self.client.get('/api/v1/quota', headers=self.headers).raise_for_status().json()

    def submit_screening(self, body=None):
        return self.client.post(f'/api/v1/pets/{self.pet_id}/screenings', headers=self.headers,
                                json=body if body is not None else {'spirit': 'normal', 'appetite': 'normal'})

    def make_media(self, kind='photo'):
        media_id = uuid4().hex
        content_type = 'image/png' if kind == 'photo' else 'audio/wav'
        with Session(self.engine) as db, db.begin():
            db.add(MediaUpload(id=media_id, pet_id=self.pet_id, kind=kind, content_type=content_type,
                               size_bytes=1024, expires_at=utcnow() + timedelta(minutes=10), version_id='version-1'))
        return media_id

    def send_text(self, content='喵呜', key=None):
        headers = dict(self.headers)
        if key:
            headers['Idempotency-Key'] = key
        return self.client.post(f'/api/v1/chat/sessions/{self.session_id}/messages', headers=headers,
                                json={'kind': 'text', 'content': content})


class QuotaAPITests(QuotaFixture, unittest.TestCase):
    def test_quota_requires_auth(self):
        self.assertEqual(self.client.get('/api/v1/quota').status_code, 401)

    def test_quota_endpoint_shape(self):
        data = self.quota()
        self.assertEqual(data['metrics'], {'screening': {'used': 0, 'limit': 10},
                                           'avatar_gen': {'used': 0, 'limit': 3},
                                           'chat_msg': {'used': 0, 'limit': 50}})

    def test_screening_11th_429_redline_exempt_and_counter_exact(self):
        for _ in range(10):
            self.assertEqual(self.submit_screening().status_code, 201)
        blocked = self.submit_screening()
        self.assertEqual(blocked.status_code, 429)
        body = blocked.json()
        self.assertEqual(body['code'], 'QUOTA_EXCEEDED')
        self.assertIn('明日再试', body['message'])
        self.assertEqual(body['detail']['metric'], 'screening')
        redline = self.submit_screening({'spirit': 'normal', 'appetite': 'normal',
                                         'redline_options': ['open_mouth_breathing']})
        self.assertEqual(redline.status_code, 201)
        self.assertEqual(redline.json()['state'], 'urgent')
        self.assertEqual(self.quota()['metrics']['screening'], {'used': 10, 'limit': 10})

    def test_screening_env_hot_adjust(self):
        with patch.dict('os.environ', {'QUOTA_SCREENING': '2'}):
            self.assertEqual(self.submit_screening().status_code, 201)
            self.assertEqual(self.submit_screening().status_code, 201)
            self.assertEqual(self.submit_screening().status_code, 429)
            self.assertEqual(self.quota()['metrics']['screening']['limit'], 2)

    def settle_task(self, task_id):
        from app.models import Task
        with Session(self.engine) as db, db.begin():
            task = db.get(Task, task_id)
            task.status = 'succeeded'

    def test_avatar_quota_counts_new_tasks_not_merges(self):
        first = self.client.post(f'/api/v1/pets/{self.pet_id}/avatar', headers=self.headers,
                                 json={'media_id': self.make_media()})
        self.assertEqual(first.status_code, 202)
        merge = self.client.post(f'/api/v1/pets/{self.pet_id}/avatar', headers=self.headers,
                                 json={'media_id': self.make_media()})
        self.assertEqual(merge.status_code, 202)
        self.assertEqual(merge.json()['task_id'], first.json()['task_id'])
        self.assertEqual(self.quota()['metrics']['avatar_gen']['used'], 1)
        self.settle_task(first.json()['task_id'])
        for _ in range(2):
            response = self.client.post(f'/api/v1/pets/{self.pet_id}/avatar', headers=self.headers,
                                        json={'media_id': self.make_media()})
            self.assertEqual(response.status_code, 202)
            self.settle_task(response.json()['task_id'])
        blocked = self.client.post(f'/api/v1/pets/{self.pet_id}/avatar', headers=self.headers,
                                   json={'media_id': self.make_media()})
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked.json()['code'], 'QUOTA_EXCEEDED')
        self.assertEqual(self.quota()['metrics']['avatar_gen'], {'used': 3, 'limit': 3})

    def test_chat_quota_text_only_and_replay_not_double_counted(self):
        with patch.dict('os.environ', {'QUOTA_CHAT': '3'}):
            self.assertEqual(self.send_text('第一句', key='k1').status_code, 201)
            replay = self.send_text('第一句', key='k1')
            self.assertEqual(replay.status_code, 201)
            self.assertEqual(replay.headers.get('Idempotent-Replay'), 'true')
            self.assertEqual(self.quota()['metrics']['chat_msg']['used'], 1)
            self.assertEqual(self.send_text('第二句').status_code, 201)
            self.assertEqual(self.send_text('第三句').status_code, 201)
            blocked = self.send_text('第四句')
            self.assertEqual(blocked.status_code, 429)
            self.assertIn('明日再试', blocked.json()['message'])
            audio = self.client.post(f'/api/v1/chat/sessions/{self.session_id}/messages', headers=self.headers,
                                     json={'kind': 'audio', 'media_id': self.make_media(kind='audio')})
            self.assertEqual(audio.status_code, 202)
            self.assertEqual(self.quota()['metrics']['chat_msg'], {'used': 3, 'limit': 3})


class PlansTests(QuotaFixture, unittest.TestCase):
    def test_plans_requires_auth(self):
        self.assertEqual(self.client.get('/api/v1/plans').status_code, 401)

    def test_plans_catalog_free_pro_without_prices(self):
        data = self.client.get('/api/v1/plans', headers=self.headers).raise_for_status().json()
        codes = {p['code'] for p in data['items']}
        self.assertEqual(codes, {'free', 'pro'})
        for plan in data['items']:
            self.assertIn('entitlements', plan)
            self.assertNotIn('price', plan)

    def test_entitlement_defaults_to_free_test_period(self):
        data = self.client.get('/api/v1/me/entitlement', headers=self.headers).raise_for_status().json()
        self.assertEqual(data['plan'], 'free')
        self.assertEqual(data['status'], 'active')
        self.assertEqual(data['message'], '测试期免费')


if __name__ == '__main__':
    unittest.main()
