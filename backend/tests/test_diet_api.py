"""T12 饮食记录与喂养参考 API（FRD F07-1~4，附录 E）。"""
from datetime import datetime, timedelta
from unittest import TestCase

from sqlalchemy.orm import Session

from test_auth_api import AuthAPIFixture
from app.core.security import utcnow
from app.services.feeding import FEEDING_DISCLAIMER
from app.models import DietRecord, WeightRecord


class DietFixture(AuthAPIFixture):
    def setUp(self):
        super().setUp()
        self.headers = {'Authorization': 'Bearer ' + self.login().json()['access_token']}
        self.client.post('/api/v1/consents', headers=self.headers, json={'privacy': 'p1', 'terms': 't1'}).raise_for_status()
        self.pet = self.client.post('/api/v1/pets', headers=self.headers, json={'name': '团团'}).raise_for_status().json()['id']

    def post_diet(self, body, pet=None, headers=None):
        return self.client.post(f'/api/v1/pets/{pet or self.pet}/diet',
                                headers=self.headers if headers is None else headers, json=body)

    def get_diet(self, pet=None, **params):
        return self.client.get(f'/api/v1/pets/{pet or self.pet}/diet', headers=self.headers, params=params)

    def make_diet(self, food_type='dry', amount_g=50, fed_at=None, pet=None):
        with Session(self.engine) as db:
            record = DietRecord(pet_id=pet or self.pet, food_type=food_type, amount_g=amount_g,
                                kcal_est=round(amount_g * 3.8, 1) if food_type == 'dry' else (round(amount_g * 0.9, 1) if food_type == 'wet' else None),
                                fed_at=fed_at or utcnow())
            db.add(record)
            db.commit()
            return record.id

    def make_weight(self, kg, measured_at=None, pet=None):
        with Session(self.engine) as db:
            record = WeightRecord(pet_id=pet or self.pet, weight_kg=kg, measured_at=measured_at or utcnow())
            db.add(record)
            db.commit()
            return record.id

    def other_headers(self):
        from app.services.identity import create_email_account, verify_email
        with Session(self.engine) as db:
            token = create_email_account(db, 'other@example.com', self.password, self.now)
            verify_email(db, token, self.now)
            db.commit()
        headers = {'Authorization': 'Bearer ' + self.login(email='other@example.com').json()['access_token']}
        self.client.post('/api/v1/consents', headers=headers, json={'privacy': 'p1', 'terms': 't1'}).raise_for_status()
        return headers


class DietRecordTests(DietFixture, TestCase):
    def test_ac_07_2_dry_50g_is_190(self):
        data = self.post_diet({'food_type': 'dry', 'amount_g': 50}).raise_for_status().json()
        self.assertEqual(data['kcal_est'], 190.0)
        self.assertEqual(data['amount_g'], 50.0)
        self.assertEqual(data['food_type'], 'dry')
        self.assertIsInstance(data['id'], int)
        fed = datetime.fromisoformat(data['fed_at'])
        self.assertLess(abs((utcnow() - fed).total_seconds()), 120)

    def test_wet_snack_other_kcal(self):
        self.assertEqual(self.post_diet({'food_type': 'wet', 'amount_g': 100}).raise_for_status().json()['kcal_est'], 90.0)
        self.assertIsNone(self.post_diet({'food_type': 'snack', 'amount_g': 20}).raise_for_status().json()['kcal_est'])
        self.assertIsNone(self.post_diet({'food_type': 'other', 'amount_g': 20}).raise_for_status().json()['kcal_est'])

    def test_amount_validation_locates_field(self):
        for amount in (0, -5, 2001):
            response = self.post_diet({'food_type': 'dry', 'amount_g': amount})
            self.assertEqual(response.status_code, 400, amount)
            body = response.json()
            self.assertEqual(body['code'], 'VALIDATION_ERROR')
            self.assertIn('amount_g', [f['field'] for f in body['detail']['fields']])

    def test_type_and_text_validation(self):
        self.assertEqual(self.post_diet({'food_type': 'grass', 'amount_g': 10}).status_code, 400)
        response = self.post_diet({'food_type': 'dry', 'amount_g': 10, 'note': 'x' * 256})
        self.assertEqual(response.status_code, 400)
        self.assertIn('note', [f['field'] for f in response.json()['detail']['fields']])
        self.assertEqual(self.post_diet({'food_type': 'dry', 'amount_g': 10, 'food_name': 'x' * 65}).status_code, 400)

    def test_fed_at_window(self):
        future = (utcnow() + timedelta(minutes=2)).isoformat() + 'Z'
        response = self.post_diet({'food_type': 'dry', 'amount_g': 10, 'fed_at': future})
        self.assertEqual(response.status_code, 400)
        self.assertIn('fed_at', [f['field'] for f in response.json()['detail']['fields']])
        old = (utcnow() - timedelta(days=8)).isoformat() + 'Z'
        self.assertEqual(self.post_diet({'food_type': 'dry', 'amount_g': 10, 'fed_at': old}).status_code, 400)
        back = (utcnow() - timedelta(days=6)).isoformat() + 'Z'
        self.assertEqual(self.post_diet({'food_type': 'dry', 'amount_g': 10, 'fed_at': back}).status_code, 201)

    def test_amount_rounded_to_one_decimal(self):
        data = self.post_diet({'food_type': 'dry', 'amount_g': 33.33}).raise_for_status().json()
        self.assertEqual(data['amount_g'], 33.3)
        self.assertEqual(data['kcal_est'], 126.5)

    def test_requires_login_consent_and_ownership(self):
        self.assertEqual(self.client.post(f'/api/v1/pets/{self.pet}/diet', json={'food_type': 'dry', 'amount_g': 10}).status_code, 401)
        other = self.other_headers()
        self.assertEqual(self.post_diet({'food_type': 'dry', 'amount_g': 10}, headers=other).status_code, 404)
        self.assertEqual(self.client.get(f'/api/v1/pets/{self.pet}/diet', headers=other).status_code, 404)
        record = self.make_diet()
        self.assertEqual(self.client.delete(f'/api/v1/pets/{self.pet}/diet/{record}', headers=other).status_code, 404)

    def test_ac_07_3_local_day_boundary(self):
        offset = 480  # UTC+8
        local_today = (utcnow() + timedelta(minutes=offset)).date()
        start = datetime.combine(local_today, datetime.min.time()) - timedelta(minutes=offset)
        before = self.make_diet('dry', 50, fed_at=start - timedelta(minutes=1))
        at_start = self.make_diet('wet', 100, fed_at=start)
        late = self.make_diet('snack', 20, fed_at=start + timedelta(hours=23, minutes=59))
        data = self.get_diet(date=local_today.isoformat(), tz_offset_minutes=offset).raise_for_status().json()
        self.assertEqual(data['date'], local_today.isoformat())
        self.assertEqual(sorted(i['id'] for i in data['items']), sorted([at_start, late]))
        self.assertEqual(data['count'], 2)
        self.assertEqual(data['total_g'], 120.0)
        self.assertEqual(data['total_kcal'], 90.0)
        prev = self.get_diet(date=(local_today - timedelta(days=1)).isoformat(), tz_offset_minutes=offset).raise_for_status().json()
        self.assertEqual([i['id'] for i in prev['items']], [before])

    def test_totals_and_delete_recompute(self):
        self.post_diet({'food_type': 'dry', 'amount_g': 50}).raise_for_status()
        wet = self.post_diet({'food_type': 'wet', 'amount_g': 100}).raise_for_status().json()['id']
        self.post_diet({'food_type': 'snack', 'amount_g': 20}).raise_for_status()
        offset = -datetime.now().astimezone().utcoffset().total_seconds() / 60
        local_today = (utcnow() + timedelta(minutes=offset)).date()
        data = self.get_diet(date=local_today.isoformat(), tz_offset_minutes=int(offset)).raise_for_status().json()
        self.assertEqual((data['total_g'], data['total_kcal'], data['count']), (170.0, 280.0, 3))
        self.assertEqual(self.client.delete(f'/api/v1/pets/{self.pet}/diet/{wet}', headers=self.headers).status_code, 204)
        data = self.get_diet(date=local_today.isoformat(), tz_offset_minutes=int(offset)).raise_for_status().json()
        self.assertEqual((data['total_g'], data['total_kcal'], data['count']), (70.0, 190.0, 2))

    def test_recent_mode_without_date(self):
        now = utcnow()
        a = self.make_diet('dry', 10, fed_at=now - timedelta(hours=2))
        b = self.make_diet('wet', 20, fed_at=now - timedelta(hours=1))
        data = self.get_diet().raise_for_status().json()
        self.assertEqual([i['id'] for i in data['items']], [b, a])
        limited = self.get_diet(limit=1).raise_for_status().json()
        self.assertEqual(len(limited['items']), 1)

    def test_delete_missing_is_404(self):
        self.assertEqual(self.client.delete(f'/api/v1/pets/{self.pet}/diet/999999', headers=self.headers).status_code, 404)

    def test_bad_date_param(self):
        self.assertEqual(self.get_diet(date='2026/11/19').status_code, 400)


class FeedingReferenceTests(DietFixture, TestCase):
    def reference(self, pet=None):
        return self.client.get(f'/api/v1/pets/{pet or self.pet}/feeding-reference', headers=self.headers)

    def test_no_weight_gives_guidance_not_numbers(self):
        data = self.reference().raise_for_status().json()
        self.assertFalse(data['has_weight'])
        self.assertNotIn('der_kcal', data)
        self.assertTrue(data['guidance'])
        self.assertEqual(data['disclaimer'], FEEDING_DISCLAIMER)

    def test_ac_07_4_4kg_neutered_adult(self):
        self.make_weight(4.0)
        self.client.patch(f'/api/v1/pets/{self.pet}', headers=self.headers,
                          json={'birth_date': '2024-01-01', 'neutered': True}).raise_for_status()
        data = self.reference().raise_for_status().json()
        self.assertTrue(data['has_weight'])
        self.assertEqual(data['weight_kg'], 4.0)
        self.assertAlmostEqual(data['der_kcal'], 238.0, delta=1.0)
        self.assertAlmostEqual(data['dry_g'], 63.0, delta=1.0)
        self.assertEqual(data['disclaimer'], FEEDING_DISCLAIMER)

    def test_latest_weight_wins(self):
        now = utcnow()
        self.make_weight(3.0, measured_at=now - timedelta(days=2))
        self.make_weight(5.0, measured_at=now - timedelta(days=1))
        self.assertEqual(self.reference().raise_for_status().json()['weight_kg'], 5.0)

    def test_missing_config_is_503(self):
        self.client.app.state.feeding_config = None
        try:
            response = self.post_diet({'food_type': 'dry', 'amount_g': 10})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()['code'], 'CONFIG_UNAVAILABLE')
            self.assertEqual(self.reference().status_code, 503)
        finally:
            from app.services.feeding import load_feeding_config
            from pathlib import Path
            self.client.app.state.feeding_config = load_feeding_config(Path(__file__).resolve().parents[1] / 'rules')


class HealthOverviewTests(DietFixture, TestCase):
    def test_diet_today_same_source_as_diet_api(self):
        self.post_diet({'food_type': 'dry', 'amount_g': 50}).raise_for_status()
        self.post_diet({'food_type': 'wet', 'amount_g': 100}).raise_for_status()
        offset = 480
        local_today = (utcnow() + timedelta(minutes=offset)).date().isoformat()
        health = self.client.get(f'/api/v1/pets/{self.pet}/health', headers=self.headers,
                                 params={'tz_offset_minutes': offset}).raise_for_status().json()
        daily = self.get_diet(date=local_today, tz_offset_minutes=offset).raise_for_status().json()
        self.assertEqual(health['diet_today'], {'date': local_today, 'total_g': daily['total_g'],
                                                'total_kcal': daily['total_kcal'], 'count': daily['count']})
        self.assertEqual(health['diet_today']['count'], 2)

    def test_latest_weight_in_health(self):
        self.make_weight(4.2)
        health = self.client.get(f'/api/v1/pets/{self.pet}/health', headers=self.headers).raise_for_status().json()
        self.assertEqual(health['latest_weight']['weight_kg'], 4.2)
        self.assertTrue(health['latest_weight']['measured_at'])

    def test_empty_pet_has_zero_diet_not_null(self):
        health = self.client.get(f'/api/v1/pets/{self.pet}/health', headers=self.headers).raise_for_status().json()
        self.assertEqual(health['diet_today']['count'], 0)
        self.assertEqual(health['diet_today']['total_kcal'], 0.0)
        self.assertIsNone(health['latest_weight'])


if __name__ == '__main__':
    import unittest
    unittest.main()
