import os
import unittest
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import main
from app.core.security import utcnow
from app.models import (
    AdminAuditLog,
    AiUsageLog,
    AuthSession,
    Base,
    ChatMessage,
    ChatSession,
    DeletionJob,
    DietRecord,
    HealthScreening,
    QuotaDenial,
    ScreeningSymptom,
    Task,
    User,
    UserCredential,
    WeightRecord,
)
from app.services.identity import create_email_account, verify_email
from app.services.pets import PetInput, create_pet

ADMIN_EMAIL = 'ops@example.com'
ADMIN_PASSWORD = 'Admin12345'
OWNER_EMAIL = 'owner@example.com'
OWNER_PASSWORD = 'Owner12345'


class AdminAPIFixture:
    key = 'admin-test-signing-key-32-bytes-or-more'

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.url = 'sqlite:///' + str(Path(directory.name) / 'admin.db')
        self.engine = create_engine(self.url)
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.now = utcnow()
        self._seed()
        self.env = {
            'DATABASE_URL': self.url,
            'JWT_SECRET': self.key,
            'ADMIN_EMAILS': ADMIN_EMAIL,
            'PRIVACY_VERSION': 'p1',
            'TERMS_VERSION': 't1',
            'PRIVACY_URL': 'https://example.com/privacy',
            'TERMS_URL': 'https://example.com/terms',
        }
        with patch.dict(os.environ, self.env):
            self.client = TestClient(main.create_dev_app())
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def _user(self, db, email, password, *, nickname, status='active'):
        token = create_email_account(db, email, password, self.now)
        verify_email(db, token, self.now)
        user = db.scalar(
            select(User)
            .join(
                UserCredential,
                UserCredential.user_id == User.id,
            )
            .where(UserCredential.identifier == email)
        )
        user.nickname = nickname
        user.status = status
        db.flush()
        return user

    def _seed(self):
        with Session(self.engine) as db, db.begin():
            admin = self._user(db, ADMIN_EMAIL, ADMIN_PASSWORD, nickname='运营小灯')
            owner = self._user(db, OWNER_EMAIL, OWNER_PASSWORD, nickname='团团的铲屎官')
            other = self._user(db, 'other@example.com', 'Other12345', nickname='另一位主人')
            self._user(db, 'paused@example.com', 'Paused12345', nickname='停用账号', status='suspended')
            deleting = self._user(db, 'bye@example.com', 'Bye123456', nickname='注销账号', status='deletion_pending')
            db.add(
                DeletionJob(
                    user_id=deleting.id,
                    status='pending',
                    requested_at=self.now,
                    purge_after=self.now + timedelta(days=15),
                )
            )
            pet = create_pet(
                db,
                owner.id,
                PetInput(
                    name='团团',
                    breed='中华田园猫',
                    sex='female',
                    birth_date=(self.now.date() - timedelta(days=900)),
                    neutered=True,
                ),
            )
            redline = HealthScreening(
                pet_id=pet.id,
                user_id=owner.id,
                state='urgent',
                redline_hit=True,
                spirit='markedly_down',
                appetite='refused',
                triage_json={'redlines': ['breathing'], 'symptom_grades': {'vomiting': 'vet'}},
                rules_version='sx-test+rl-test',
                created_at=self.now - timedelta(hours=2),
            )
            normal = HealthScreening(
                pet_id=pet.id,
                user_id=owner.id,
                state='normal',
                redline_hit=False,
                spirit='normal',
                appetite='normal',
                triage_json={'redlines': [], 'symptom_grades': {}},
                rules_version='sx-test+rl-test',
                created_at=self.now - timedelta(days=2),
            )
            db.add_all([redline, normal])
            db.flush()
            db.add(
                ScreeningSymptom(
                    screening_id=redline.id,
                    symptom_code='vomiting',
                    duration='>24h',
                    frequency='>6',
                    severe=True,
                    notes='测试备注',
                )
            )
            db.add(
                DietRecord(
                    pet_id=pet.id, food_type='dry', amount_g=35, kcal_est=120, fed_at=self.now - timedelta(hours=3)
                )
            )
            db.add(WeightRecord(pet_id=pet.id, weight_kg=4.2, measured_at=self.now - timedelta(days=1)))
            chat = ChatSession(pet_id=pet.id, user_id=owner.id)
            db.add(chat)
            db.flush()
            db.add(
                ChatMessage(
                    session_id=chat.id,
                    role='user',
                    kind='text',
                    content='团团今天好吗？',
                    created_at=self.now - timedelta(hours=1),
                )
            )
            db.add(
                AiUsageLog(
                    user_id=owner.id,
                    provider='dashscope',
                    model='qwen-plus',
                    kind='chat',
                    tokens_in=120,
                    tokens_out=64,
                    cost_est=0.0123,
                    created_at=self.now - timedelta(hours=1),
                )
            )
            db.add(
                QuotaDenial(
                    user_id=owner.id, metric='screening', day=self.now.date(), created_at=self.now - timedelta(hours=1)
                )
            )
            db.add(
                Task(
                    id='t' * 32,
                    pet_id=pet.id,
                    type='avatar_batch',
                    status='failed',
                    request_key='r' * 32,
                    payload={},
                    attempts=2,
                    created_at=self.now - timedelta(hours=4),
                    updated_at=self.now - timedelta(hours=3),
                )
            )
            self.admin_id = admin.id
            self.owner_id = owner.id
            self.other_id = other.id
            self.deleting_id = deleting.id
            self.pet_id = pet.id
            self.redline_id = redline.id
            self.normal_id = normal.id

    def login(self, email=ADMIN_EMAIL, password=ADMIN_PASSWORD):
        return self.client.post('/api/v1/auth/login', json={'email': email, 'password': password})

    def headers(self, email=ADMIN_EMAIL, password=ADMIN_PASSWORD):
        response = self.login(email, password)
        self.assertEqual(response.status_code, 200, response.text)
        return {'Authorization': f'Bearer {response.json()["access_token"]}'}


class AdminAPITests(AdminAPIFixture, unittest.TestCase):
    def test_admin_session_requires_configured_admin(self):
        self.assertEqual(self.client.get('/api/v1/admin/session').status_code, 401)
        headers = self.headers(OWNER_EMAIL, OWNER_PASSWORD)
        response = self.client.get('/api/v1/admin/session', headers=headers)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['code'], 'ADMIN_REQUIRED')

        admin_headers = self.headers()
        response = self.client.get('/api/v1/admin/session', headers=admin_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['admin']['email'], ADMIN_EMAIL)
        self.assertEqual(response.headers['cache-control'], 'no-store')

    def test_console_shell_and_assets_are_served(self):
        response = self.client.get('/admin')
        self.assertEqual(response.status_code, 200)
        self.assertIn('绒星', response.text)
        self.assertIn("script-src 'self'", response.headers['content-security-policy'])
        self.assertEqual(response.headers['x-content-type-options'], 'nosniff')
        asset = self.client.get('/admin/assets/app.js')
        self.assertEqual(asset.status_code, 200)
        self.assertIn('javascript', asset.headers['content-type'])
        self.assertEqual(asset.headers['cache-control'], 'no-cache')

    def test_overview_aggregates_window_and_alerts(self):
        headers = self.headers()
        response = self.client.get('/api/v1/admin/overview?days=30', headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data['window']['days'], 30)
        self.assertEqual(len(data['series']['days']), 30)
        self.assertEqual(len(data['series']['screenings']), 30)
        self.assertEqual(data['kpis']['users_total'], 5)
        self.assertEqual(data['kpis']['users_suspended'], 1)
        self.assertEqual(data['kpis']['pending_deletions'], 1)
        self.assertEqual(data['kpis']['pets_total'], 1)
        self.assertEqual(data['kpis']['screenings'], 2)
        self.assertEqual(data['kpis']['redline_hits'], 1)
        self.assertEqual(data['kpis']['chat_messages'], 1)
        self.assertTrue(any(item['state'] == 'urgent' and item['count'] == 1 for item in data['states']))
        self.assertEqual(len(data['redlines']), 1)
        self.assertEqual(data['redlines'][0]['pet_name'], '团团')
        self.assertEqual(data['ai_models'][0]['model'], 'qwen-plus')
        self.assertEqual(data['tasks'][0]['failed'], 1)
        self.assertTrue(data['alerts'])

    def test_user_list_search_and_detail(self):
        headers = self.headers()
        listing = self.client.get('/api/v1/admin/users?query=owner@example.com', headers=headers)
        self.assertEqual(listing.status_code, 200, listing.text)
        self.assertEqual(listing.json()['total'], 1)
        item = listing.json()['items'][0]
        self.assertEqual(item['nickname'], '团团的铲屎官')
        self.assertEqual(item['pet_count'], 1)
        self.assertEqual(item['screening_count'], 2)

        detail = self.client.get(f'/api/v1/admin/users/{self.owner_id}', headers=headers)
        self.assertEqual(detail.status_code, 200, detail.text)
        body = detail.json()
        self.assertEqual(body['user']['email'], OWNER_EMAIL)
        self.assertEqual(body['counts']['screenings'], 2)
        self.assertEqual(body['counts']['redlines'], 1)
        self.assertEqual(body['counts']['chat_messages'], 1)
        self.assertEqual(body['pets'][0]['name'], '团团')
        self.assertAlmostEqual(body['pets'][0]['weight_kg'], 4.2)
        self.assertIsNone(body['deletion_job'])
        self.assertEqual(self.client.get('/api/v1/admin/users/999999', headers=headers).status_code, 404)

    def test_status_change_writes_audit_and_blocks_self_and_grace_period(self):
        headers = self.headers()
        owner_tokens = self.login(OWNER_EMAIL, OWNER_PASSWORD).json()
        response = self.client.patch(
            f'/api/v1/admin/users/{self.owner_id}/status', json={'status': 'suspended'}, headers=headers
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['status'], 'suspended')
        with Session(self.engine) as db:
            self.assertEqual(db.get(User, self.owner_id).status, 'suspended')
            audit = db.scalars(select(AdminAuditLog)).all()
            self.assertEqual(len(audit), 1)
            self.assertEqual(audit[0].action, 'user.status')
            self.assertEqual(audit[0].detail, {'from': 'active', 'to': 'suspended'})

        # The suspended account can no longer sign in, and old refresh sessions are revoked.
        self.assertEqual(self.login(OWNER_EMAIL, OWNER_PASSWORD).status_code, 401)
        with Session(self.engine) as db:
            sessions = db.scalars(select(AuthSession).where(AuthSession.user_id == self.owner_id)).all()
            self.assertTrue(sessions)
            self.assertTrue(all(session.revoked_at is not None for session in sessions))

        restore = self.client.patch(
            f'/api/v1/admin/users/{self.owner_id}/status', json={'status': 'active'}, headers=headers
        )
        self.assertEqual(restore.status_code, 200)
        # Suspension retired the old session; a fresh login is required.
        old_access = self.client.get('/api/v1/me', headers={'Authorization': f'Bearer {owner_tokens["access_token"]}'})
        self.assertEqual(old_access.status_code, 401)
        self.assertEqual(self.login(OWNER_EMAIL, OWNER_PASSWORD).status_code, 200)

        self.assertEqual(
            self.client.patch(
                f'/api/v1/admin/users/{self.admin_id}/status', json={'status': 'suspended'}, headers=headers
            ).status_code,
            409,
        )
        grace = self.client.patch(
            f'/api/v1/admin/users/{self.deleting_id}/status', json={'status': 'active'}, headers=headers
        )
        self.assertEqual(grace.status_code, 409)
        self.assertEqual(
            self.client.patch(
                '/api/v1/admin/users/999999/status', json={'status': 'active'}, headers=headers
            ).status_code,
            404,
        )
        invalid = self.client.patch(
            f'/api/v1/admin/users/{self.owner_id}/status', json={'status': 'deleted'}, headers=headers
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.json()['code'], 'VALIDATION_ERROR')

    def test_pets_screenings_and_usage_endpoints(self):
        headers = self.headers()
        pets = self.client.get('/api/v1/admin/pets?query=团团', headers=headers)
        self.assertEqual(pets.status_code, 200, pets.text)
        self.assertEqual(pets.json()['total'], 1)
        pet = pets.json()['items'][0]
        self.assertEqual(pet['owner_email'], OWNER_EMAIL)
        self.assertAlmostEqual(pet['weight_kg'], 4.2)

        screenings = self.client.get('/api/v1/admin/screenings?state=urgent&redline=only', headers=headers)
        self.assertEqual(screenings.status_code, 200, screenings.text)
        self.assertEqual(screenings.json()['total'], 1)
        row = screenings.json()['items'][0]
        self.assertEqual(row['state'], 'urgent')
        self.assertTrue(row['redline_hit'])
        self.assertEqual(row['symptoms'][0]['label'], '呕吐')

        detail = self.client.get(f'/api/v1/admin/screenings/{self.redline_id}', headers=headers)
        self.assertEqual(detail.status_code, 200, detail.text)
        body = detail.json()
        self.assertEqual(body['pet']['name'], '团团')
        self.assertEqual(body['owner']['email'], OWNER_EMAIL)
        self.assertEqual(body['symptoms'][0]['duration'], '>24h')
        self.assertTrue(body['symptoms'][0]['severe'])
        self.assertEqual(self.client.get('/api/v1/admin/screenings/999999', headers=headers).status_code, 404)

        usage = self.client.get('/api/v1/admin/ai-usage?days=7', headers=headers)
        self.assertEqual(usage.status_code, 200, usage.text)
        usage_body = usage.json()
        self.assertEqual(usage_body['ai']['totals']['calls'], 1)
        self.assertEqual(usage_body['ai']['totals']['cost_est'], 0.0123)
        self.assertEqual(usage_body['per_user'][0]['email'], OWNER_EMAIL)
        self.assertEqual(usage_body['tasks'][0]['success_rate'], 0.0)
        self.assertEqual(usage_body['quota_denials'][0]['metric'], 'screening')

    def test_audit_list_is_paginated(self):
        headers = self.headers()
        for _ in range(3):
            self.client.patch(
                f'/api/v1/admin/users/{self.other_id}/status', json={'status': 'suspended'}, headers=headers
            )
            self.client.patch(f'/api/v1/admin/users/{self.other_id}/status', json={'status': 'active'}, headers=headers)
        response = self.client.get('/api/v1/admin/audit?page=1&page_size=5', headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['total'], 6)
        self.assertEqual(len(response.json()['items']), 5)
        self.assertEqual(response.json()['items'][0]['admin_email'], ADMIN_EMAIL)

    def test_unconfigured_admin_list_returns_503(self):
        headers = self.headers()
        with patch.dict(os.environ, {**self.env, 'ADMIN_EMAILS': ''}):
            with TestClient(main.create_dev_app()) as client:
                response = client.get('/api/v1/admin/session', headers=headers)
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json()['code'], 'ADMIN_NOT_CONFIGURED')


if __name__ == '__main__':
    unittest.main()
