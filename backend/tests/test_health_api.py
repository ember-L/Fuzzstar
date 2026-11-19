"""T08 GET /pets/{id}/health：状态档+健康分+扣分明细+概览；复查覆盖旧事件。"""
from datetime import timedelta
from unittest import TestCase
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.orm import Session

from test_screening_api import ScreeningFixture, CARD_TITLE, CARD_SUBTITLE, PREPARATION
from app.auth import utcnow
from app.models import HealthEvent, Pet

OBSERVE_BODY = {'spirit': 'normal', 'appetite': 'normal',
                'symptoms': [{'code': 'vomiting', 'duration': '2-12h', 'frequency': '2-3'}]}
URGENT_BODY = {'spirit': 'normal', 'appetite': 'normal', 'redline_options': ['open_mouth_breathing']}


class HealthApiFixture(ScreeningFixture):
    def health(self, pet=None):
        return self.client.get(f'/api/v1/pets/{pet or self.pet}/health', headers=self.headers)


class HealthApiTests(HealthApiFixture, TestCase):
    def test_requires_login_and_consent(self):
        self.assertEqual(self.client.get(f'/api/v1/pets/{self.pet}/health').status_code, 401)
        self.verified_account('other@example.com', consent=False)
        token = self.login(email='other@example.com').json()['access_token']
        self.assertEqual(self.client.get(f'/api/v1/pets/{self.pet}/health',
                                         headers={'Authorization': 'Bearer ' + token}).status_code, 403)

    def test_other_users_pet_is_404(self):
        self.verified_account('other@example.com')
        token = self.login(email='other@example.com').json()['access_token']
        self.assertEqual(self.client.get(f'/api/v1/pets/{self.pet}/health',
                                         headers={'Authorization': 'Bearer ' + token}).status_code, 404)

    def test_deleted_pet_is_404(self):
        with Session(self.engine) as db:
            db.get(Pet, self.pet).status = 'deleted'
            db.commit()
        self.assertEqual(self.health().status_code, 404)

    def test_new_pet_is_not_assessed(self):
        response = self.health().raise_for_status()
        data = response.json()
        self.assertEqual(data['state'], 'normal')
        self.assertIsNone(data['score'])
        self.assertEqual(data['deductions'], [])
        self.assertIsNone(data['latest_screening'])
        self.assertEqual(data['diet_today']['count'], 0)
        self.assertEqual(data['diet_today']['total_kcal'], 0.0)
        self.assertIsNone(data['latest_weight'])
        self.assertIsNone(data['urgent_card'])
        self.assertEqual(response.headers['Cache-Control'], 'no-store')

    def test_normal_screening_scores_100(self):
        self.submit().raise_for_status()
        data = self.health().raise_for_status().json()
        self.assertEqual(data['score'], 100)
        self.assertEqual(data['state'], 'normal')
        self.assertEqual(data['latest_screening']['state'], 'normal')

    def test_observe_score_and_traceable_deduction(self):
        screening_id = self.submit(OBSERVE_BODY).raise_for_status().json()['screening_id']
        data = self.health().raise_for_status().json()
        self.assertEqual(data['score'], 90)
        self.assertEqual(data['state'], 'observe')
        self.assertEqual(data['latest_screening']['screening_id'], screening_id)
        item = data['deductions'][0]
        self.assertEqual(item['severity'], 'observe')
        self.assertEqual(item['score_delta'], 10)
        self.assertEqual(item['effective_delta'], 10)
        self.assertFalse(item['decayed'])
        self.assertEqual(item['symptoms'], ['呕吐'])
        self.assertEqual(item['source'], 'screening')
        self.assertEqual(item['source_id'], screening_id)
        self.assertEqual(item['rules_version'], 'sx-2026-11-19+rl-2026-11-19')
        self.assertTrue(item['created_at'])

    def test_urgent_state_carries_vet_card(self):
        self.submit(URGENT_BODY).raise_for_status()
        data = self.health().raise_for_status().json()
        self.assertEqual(data['state'], 'urgent')
        self.assertEqual(data['score'], 40)
        self.assertEqual(data['urgent_card']['title'], CARD_TITLE)
        self.assertEqual(data['urgent_card']['subtitle'], CARD_SUBTITLE)
        self.assertEqual(data['urgent_card']['preparation'], PREPARATION)

    def test_recheck_normal_resolves_old_events(self):
        self.submit(OBSERVE_BODY).raise_for_status()
        self.submit().raise_for_status()
        data = self.health().raise_for_status().json()
        self.assertEqual(data['state'], 'normal')
        self.assertEqual(data['score'], 100)
        self.assertEqual(data['deductions'], [])
        with Session(self.engine) as db:
            events = db.scalars(select(HealthEvent).where(HealthEvent.pet_id == self.pet)).all()
            self.assertEqual(len(events), 1)
            self.assertFalse(events[0].active)
            self.assertIsNotNone(events[0].resolved_at)

    def test_recheck_escalation_replaces_event(self):
        self.submit(OBSERVE_BODY).raise_for_status()
        self.submit(URGENT_BODY).raise_for_status()
        data = self.health().raise_for_status().json()
        self.assertEqual(data['state'], 'urgent')
        self.assertEqual(data['score'], 40)
        self.assertEqual(len(data['deductions']), 1)
        self.assertEqual(data['deductions'][0]['severity'], 'urgent')
        with Session(self.engine) as db:
            resolved = db.scalars(select(HealthEvent).where(HealthEvent.pet_id == self.pet,
                                                           HealthEvent.active == False)).all()
            self.assertEqual(len(resolved), 1)
            self.assertEqual(resolved[0].severity, 'observe')

    def test_observe_decay_is_computed_at_read_time(self):
        self.submit(OBSERVE_BODY).raise_for_status()
        with Session(self.engine) as db:
            event = db.scalar(select(HealthEvent).where(HealthEvent.pet_id == self.pet))
            event.created_at = utcnow() - timedelta(hours=73)
            db.commit()
        data = self.health().raise_for_status().json()
        self.assertEqual(data['score'], 100)
        self.assertEqual(data['state'], 'normal')
        self.assertEqual(len(data['deductions']), 1)
        self.assertTrue(data['deductions'][0]['decayed'])
        self.assertEqual(data['deductions'][0]['effective_delta'], 0)

    def test_multi_pet_isolation(self):
        pet2 = self.client.post('/api/v1/pets', headers=self.headers, json={'name': '圆圆'}).raise_for_status().json()['id']
        self.submit(OBSERVE_BODY, pet=pet2).raise_for_status()
        self.assertIsNone(self.health().json()['score'])
        self.assertEqual(self.health(pet=pet2).json()['score'], 90)

    def test_latest_screening_is_most_recent(self):
        self.submit().raise_for_status()
        self.submit(OBSERVE_BODY).raise_for_status()
        data = self.health().raise_for_status().json()
        self.assertEqual(data['latest_screening']['state'], 'observe')

    def test_missing_rules_returns_503(self):
        with patch.object(self.client.app.state, 'triage_rules', None):
            response = self.health()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['code'], 'CONFIG_UNAVAILABLE')


if __name__ == '__main__':
    unittest.main()
