"""T14 浅离线幂等补发（FRD F07-5 / AC-07-5）：diet POST 可选 Idempotency-Key。"""

from datetime import timedelta
from unittest import TestCase

from sqlalchemy import select
from sqlalchemy.orm import Session
from test_diet_api import DietFixture

from app.core.security import utcnow
from app.models import RequestIdempotency
from app.services.idempotency import IDEMPOTENCY_TTL, hash_request
from app.worker import _sweep_db


class IdempotencyTests(DietFixture, TestCase):
    def post_key(self, key, body=None, pet=None, headers=None):
        merged = dict(self.headers if headers is None else headers)
        merged['Idempotency-Key'] = key
        return self.post_diet(body or {'food_type': 'dry', 'amount_g': 50}, pet=pet, headers=merged)

    def test_post_with_key_creates_record(self):
        data = self.post_key('key-1').raise_for_status().json()
        self.assertEqual(data['kcal_est'], 190.0)
        self.assertEqual(self.get_diet().json()['count'], 1)

    def test_replay_same_key_same_body_returns_same_record(self):
        first = self.post_key('key-1').raise_for_status().json()
        replay = self.post_key('key-1')
        self.assertEqual(replay.status_code, 201)
        self.assertEqual(replay.json()['id'], first['id'])
        self.assertEqual(replay.headers.get('Idempotent-Replay'), 'true')
        self.assertEqual(self.get_diet().json()['count'], 1)

    def test_replay_preserves_original_fed_at(self):
        first = self.post_key('key-1').raise_for_status().json()
        replay = self.post_key('key-1').raise_for_status().json()
        self.assertEqual(replay['fed_at'], first['fed_at'])
        self.assertEqual(replay['created_at'], first['created_at'])

    def test_same_key_different_body_conflicts(self):
        self.post_key('key-1').raise_for_status()
        conflict = self.post_key('key-1', body={'food_type': 'wet', 'amount_g': 80})
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()['code'], 'IDEMPOTENCY_CONFLICT')
        self.assertEqual(self.get_diet().json()['count'], 1)

    def test_same_key_different_pet_conflicts(self):
        other_pet = (
            self.client.post('/api/v1/pets', headers=self.headers, json={'name': '圆圆'})
            .raise_for_status()
            .json()['id']
        )
        self.post_key('key-1').raise_for_status()
        conflict = self.post_key('key-1', pet=other_pet)
        self.assertEqual(conflict.status_code, 409)

    def test_different_keys_create_two_records(self):
        self.post_key('key-1').raise_for_status()
        self.post_key('key-2').raise_for_status()
        self.assertEqual(self.get_diet().json()['count'], 2)

    def test_without_key_duplicates_allowed(self):
        self.post_diet({'food_type': 'dry', 'amount_g': 50}).raise_for_status()
        self.post_diet({'food_type': 'dry', 'amount_g': 50}).raise_for_status()
        self.assertEqual(self.get_diet().json()['count'], 2)

    def test_key_too_long_rejected(self):
        response = self.post_key('x' * 65)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'VALIDATION_ERROR')

    def test_validation_error_not_cached(self):
        bad = self.post_key('key-1', body={'food_type': 'dry', 'amount_g': 0})
        self.assertEqual(bad.status_code, 400)
        fixed = self.post_key('key-1', body={'food_type': 'dry', 'amount_g': 50})
        self.assertEqual(fixed.status_code, 201)
        self.assertEqual(self.get_diet().json()['count'], 1)

    def test_other_user_same_key_independent(self):
        self.post_key('key-1').raise_for_status()
        headers = self.other_headers()
        pet = self.client.post('/api/v1/pets', headers=headers, json={'name': '别家猫'}).raise_for_status().json()['id']
        merged = dict(headers)
        merged['Idempotency-Key'] = 'key-1'
        response = self.client.post(
            f'/api/v1/pets/{pet}/diet', headers=merged, json={'food_type': 'dry', 'amount_g': 50}
        )
        self.assertEqual(response.status_code, 201)

    def test_unauthorized_rejected(self):
        response = self.client.post(
            f'/api/v1/pets/{self.pet}/diet',
            headers={'Idempotency-Key': 'key-1'},
            json={'food_type': 'dry', 'amount_g': 50},
        )
        self.assertEqual(response.status_code, 401)

    def test_hash_is_path_and_body_sensitive(self):
        a = hash_request('/api/v1/pets/1/diet', {'food_type': 'dry', 'amount_g': 50})
        b = hash_request('/api/v1/pets/2/diet', {'food_type': 'dry', 'amount_g': 50})
        c = hash_request('/api/v1/pets/1/diet', {'amount_g': 50, 'food_type': 'dry'})
        self.assertNotEqual(a, b)
        self.assertEqual(a, c)
        self.assertEqual(len(a), 64)

    def test_sweep_prunes_expired_idempotency_rows(self):
        self.post_key('key-old').raise_for_status()
        self.post_key('key-new').raise_for_status()
        with Session(self.engine) as db:
            row = db.scalar(select(RequestIdempotency).where(RequestIdempotency.key == 'key-old'))
            row.created_at = utcnow() - IDEMPOTENCY_TTL - timedelta(hours=1)
            db.commit()
        _sweep_db(self.engine)
        with Session(self.engine) as db:
            keys = set(db.scalars(select(RequestIdempotency.key)).all())
        self.assertEqual(keys, {'key-new'})
