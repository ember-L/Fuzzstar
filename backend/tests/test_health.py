"""T08 健康分纯规则引擎（附录 D）：读时衰减、最高档状态、明细可追溯。"""

import unittest
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.services.health import compute_health

NOW = datetime(2026, 11, 19, 12, 0, 0)


def event(severity, *, hours_ago=0, delta=None, resolved=False, active=True, event_id=1):
    defaults = {'observe': 10, 'vet': 30, 'urgent': 60}
    return {
        'id': event_id,
        'source': 'screening',
        'source_id': event_id,
        'severity': severity,
        'score_delta': defaults[severity] if delta is None else delta,
        'active': active,
        'resolved_at': NOW - timedelta(hours=1) if resolved else None,
        'created_at': NOW - timedelta(hours=hours_ago),
        'rules_version': 'sx-2026-11-19+rl-2026-11-19',
        'symptoms': ['呕吐'],
    }


def compute(events, *, has_screening=True, now=NOW):
    return compute_health(events, has_screening=has_screening, now=now, decay_hours=72)


class HealthScoreTests(unittest.TestCase):
    def test_new_pet_without_screening_is_not_assessed(self):
        result = compute([], has_screening=False)
        self.assertIsNone(result['score'])
        self.assertEqual(result['state'], 'normal')
        self.assertEqual(result['deductions'], [])

    def test_screened_pet_without_events_scores_100(self):
        result = compute([])
        self.assertEqual(result['score'], 100)
        self.assertEqual(result['state'], 'normal')

    def test_single_observe_scores_90(self):
        result = compute([event('observe')])
        self.assertEqual(result['score'], 90)
        self.assertEqual(result['state'], 'observe')
        self.assertEqual(result['deductions'][0]['effective_delta'], 10)
        self.assertFalse(result['deductions'][0]['decayed'])

    def test_vet_and_urgent_deltas(self):
        self.assertEqual(compute([event('vet')])['score'], 70)
        urgent = compute([event('urgent')])
        self.assertEqual(urgent['score'], 40)
        self.assertEqual(urgent['state'], 'urgent')

    def test_multiple_events_accumulate_and_state_is_highest(self):
        result = compute([event('observe', event_id=1), event('vet', event_id=2)])
        self.assertEqual(result['score'], 60)
        self.assertEqual(result['state'], 'vet')

    def test_score_floors_at_zero(self):
        result = compute([event('urgent', event_id=1), event('urgent', event_id=2), event('vet', event_id=3)])
        self.assertEqual(result['score'], 0)

    def test_observe_decays_after_72h_but_stays_listed(self):
        result = compute([event('observe', hours_ago=73)])
        self.assertEqual(result['score'], 100)
        self.assertEqual(result['state'], 'normal')
        self.assertEqual(len(result['deductions']), 1)
        item = result['deductions'][0]
        self.assertTrue(item['decayed'])
        self.assertEqual(item['effective_delta'], 0)
        self.assertEqual(item['score_delta'], 10)

    def test_decay_boundary_is_inclusive_at_72h(self):
        self.assertTrue(compute([event('observe', hours_ago=72)])['deductions'][0]['decayed'])
        self.assertFalse(compute([event('observe', hours_ago=71)])['deductions'][0]['decayed'])

    def test_vet_and_urgent_never_decay(self):
        for severity in ('vet', 'urgent'):
            with self.subTest(severity=severity):
                result = compute([event(severity, hours_ago=200)])
                self.assertFalse(result['deductions'][0]['decayed'])
                self.assertEqual(result['state'], severity)

    def test_resolved_events_are_excluded(self):
        result = compute([event('observe', resolved=True), event('vet', resolved=True, event_id=2)])
        self.assertEqual(result['score'], 100)
        self.assertEqual(result['state'], 'normal')
        self.assertEqual(result['deductions'], [])

    def test_inactive_events_are_excluded(self):
        result = compute([event('urgent', active=False)])
        self.assertEqual(result['score'], 100)
        self.assertEqual(result['deductions'], [])

    def test_mixed_decayed_and_active(self):
        result = compute([event('observe', hours_ago=100, event_id=1), event('vet', event_id=2)])
        self.assertEqual(result['score'], 70)
        self.assertEqual(result['state'], 'vet')
        self.assertEqual(len(result['deductions']), 2)

    def test_deduction_sum_equals_100_minus_score(self):
        result = compute(
            [event('observe', hours_ago=100, event_id=1), event('vet', event_id=2), event('observe', event_id=3)]
        )
        self.assertEqual(sum(d['effective_delta'] for d in result['deductions']), 100 - result['score'])

    def test_deduction_items_carry_traceability_fields(self):
        item = compute([event('observe')])['deductions'][0]
        for key in (
            'id',
            'source',
            'source_id',
            'severity',
            'symptoms',
            'score_delta',
            'effective_delta',
            'decayed',
            'created_at',
            'rules_version',
        ):
            self.assertIn(key, item)


class HealthTest(unittest.TestCase):
    def test_health_endpoint_reports_service_is_alive(self):
        response = TestClient(app).get('/api/v1/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})

    def test_pet_write_is_not_exposed_before_authentication_exists(self):
        response = TestClient(app).post('/api/v1/pets', json={'name': '团团'})
        self.assertEqual(response.status_code, 404)


if __name__ == '__main__':
    unittest.main()
