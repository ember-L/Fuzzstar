"""T18: structured access/worker/quota logs, redaction and denial audit."""
import asyncio
import json
import logging
import os
import unittest
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import utcnow
from app.models import ChatMessage, QuotaDenial
from app.observability import log_task_event
from test_auth_api import AuthAPIFixture
from test_worker import FakeAssets, FakeImageProvider, FakeVideoProvider, make_engine, seed_task


class LogCapture:
    def __init__(self, name):
        self.records = []
        self.handler = logging.Handler()
        self.handler.emit = lambda record: self.records.append(record.getMessage())
        self.logger = logging.getLogger(name)
        self.logger.addHandler(self.handler)
        self.logger.setLevel(logging.INFO)

    def parsed(self):
        return [json.loads(line) for line in self.records]

    def close(self):
        self.logger.removeHandler(self.handler)


class AccessLogTests(AuthAPIFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.capture = LogCapture('rongxing.access')
        self.addCleanup(self.capture.close)

    def test_health_log_fields_and_request_id_echo(self):
        response = self.client.get('/api/v1/health', headers={'X-Request-ID': 'req-123'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['x-request-id'], 'req-123')
        entry = self.capture.parsed()[-1]
        self.assertEqual(entry['event'], 'http')
        self.assertEqual(entry['request_id'], 'req-123')
        self.assertEqual(entry['method'], 'GET')
        self.assertEqual(entry['path'], '/api/v1/health')
        self.assertEqual(entry['status'], 200)
        self.assertGreaterEqual(entry['duration_ms'], 0)
        self.assertIsNone(entry['user_id'])

    def test_request_id_generated_when_absent_or_invalid(self):
        self.client.get('/api/v1/health')
        generated = self.capture.parsed()[-1]['request_id']
        self.assertRegex(generated, r'^[0-9a-f]{32}$')
        response = self.client.get('/api/v1/health', headers={'X-Request-ID': 'bad id!'})
        self.assertNotEqual(response.headers['x-request-id'], 'bad id!')
        self.assertRegex(response.headers['x-request-id'], r'^[0-9a-f]{32}$')

    def test_user_id_extracted_from_bearer(self):
        token = self.login().json()['access_token']
        self.me(token)
        entry = self.capture.parsed()[-1]
        self.assertEqual(entry['path'], '/api/v1/me')
        self.assertIsInstance(entry['user_id'], int)
        self.assertGreater(entry['user_id'], 0)

    def test_sensitive_values_never_logged(self):
        self.login()
        self.client.get('/api/v1/auth/verify-email?token=super-secret-token')
        self.client.post('/api/v1/auth/login', json={'email': 'cat@example.com', 'password': 'Strong123'})
        raw = '\n'.join(self.capture.records)
        for secret in ('Strong123', 'cat@example.com', 'super-secret-token', 'authorization', 'Bearer'):
            self.assertNotIn(secret, raw)
        for entry in self.capture.parsed():
            self.assertNotIn('?', entry['path'])


class QuotaDenialAuditTests(AuthAPIFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.capture = LogCapture('rongxing.quota')
        self.addCleanup(self.capture.close)
        self.headers = {'Authorization': 'Bearer ' + self.login().json()['access_token']}
        self.client.post('/api/v1/consents', json={'privacy': 'p1', 'terms': 't1'}, headers=self.headers)
        pet = self.client.post('/api/v1/pets', json={'name': '团团'}, headers=self.headers).json()
        self.pet_id = pet['id']
        session = self.client.post(f'/api/v1/pets/{self.pet_id}/chat/sessions', headers=self.headers).json()
        self.session_id = session['session_id']

    def send(self, text):
        return self.client.post(f'/api/v1/chat/sessions/{self.session_id}/messages',
                                json={'kind': 'text', 'content': text}, headers=self.headers)

    def test_denial_persisted_despite_business_rollback(self):
        with patch.dict(os.environ, {'QUOTA_CHAT': '1'}):
            self.assertEqual(self.send('第一条').status_code, 201)
            denied = self.send('第二条')
        self.assertEqual(denied.status_code, 429)
        self.assertEqual(denied.json()['code'], 'QUOTA_EXCEEDED')
        with Session(self.engine) as db:
            rows = db.execute(select(QuotaDenial)).scalars().all()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].metric, 'chat_msg')
            self.assertEqual(rows[0].day, utcnow().date())
            self.assertGreater(rows[0].user_id, 0)
            messages = db.execute(select(ChatMessage)).scalars().all()
            self.assertEqual(len(messages), 2)  # the denied message was rolled back
        entry = self.capture.parsed()[-1]
        self.assertEqual(entry['event'], 'quota_denied')
        self.assertEqual(entry['metric'], 'chat_msg')
        self.assertEqual(entry['limit'], 1)

    def test_successful_requests_leave_no_denial(self):
        self.assertEqual(self.send('你好').status_code, 201)
        with Session(self.engine) as db:
            self.assertEqual(db.execute(select(QuotaDenial)).scalars().all(), [])
        self.assertEqual(self.capture.records, [])


class WorkerEventLogTests(unittest.TestCase):
    def test_log_task_event_fields(self):
        capture = LogCapture('rongxing.worker')
        self.addCleanup(capture.close)
        log_task_event('claimed', task_id='a' * 32, task_type='avatar_batch', attempts=1)
        entry = capture.parsed()[-1]
        self.assertEqual(entry['event'], 'claimed')
        self.assertEqual(entry['task_id'], 'a' * 32)
        self.assertEqual(entry['task_type'], 'avatar_batch')
        self.assertEqual(entry['attempts'], 1)

    def test_run_task_emits_claimed_and_finished(self):
        from app.worker import run_task
        engine = make_engine()
        self.addCleanup(engine.dispose)
        task_id, _ = seed_task(engine)
        capture = LogCapture('rongxing.worker')
        self.addCleanup(capture.close)
        ctx = {'engine': engine, 'assets': FakeAssets(),
               'image_provider': FakeImageProvider(), 'video_provider': FakeVideoProvider()}
        asyncio.run(run_task(ctx, task_id))
        events = [entry['event'] for entry in capture.parsed()]
        self.assertIn('claimed', events)
        self.assertIn('finished', events)
        for entry in capture.parsed():
            self.assertEqual(entry['task_id'], task_id)


if __name__ == '__main__':
    unittest.main()
