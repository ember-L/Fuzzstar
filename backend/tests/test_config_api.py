"""动作映射配置接口（FRD 附录 C，ARCHITECTURE 版本化配置）。"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from test_auth_api import AuthAPIFixture

from app.services.rules import load_action_map

ACTIONS = {'idle', 'happy', 'sad', 'sick', 'crouch', 'look_left', 'look_right'}


class ActionMapAPITests(AuthAPIFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.headers = {'Authorization': f'Bearer {self.login().json()["access_token"]}'}

    def consent(self):
        self.client.post(
            '/api/v1/consents', headers=self.headers, json={'privacy': 'p1', 'terms': 't1'}
        ).raise_for_status()

    def test_requires_login(self):
        response = self.client.get('/api/v1/config/action-map')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['code'], 'AUTH_REQUIRED')

    def test_requires_consent(self):
        response = self.client.get('/api/v1/config/action-map', headers=self.headers)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['code'], 'CONSENT_REQUIRED')

    def test_returns_versioned_map_covering_appendix_c(self):
        self.consent()
        response = self.client.get('/api/v1/config/action-map', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        body = response.json()
        self.assertEqual(body['version'], 'am-2026-11-18')
        self.assertEqual(set(body['actions']), ACTIONS)
        self.assertEqual(body['priority'], ['health', 'chat_emotion', 'interaction', 'idle'])
        rules = body['rules']
        self.assertTrue(rules)
        for rule in rules:
            self.assertIn(rule['source'], body['priority'])
            self.assertIsInstance(rule['condition'], dict)
            actions = rule['action'] if isinstance(rule['action'], list) else [rule['action']]
            self.assertTrue(set(actions) <= ACTIONS)

        def match(source, condition):
            return [r['action'] for r in rules if r['source'] == source and r['condition'] == condition]

        self.assertEqual(match('health', {'state': ['observe', 'vet']}), ['sick'])
        self.assertEqual(match('health', {'state': 'urgent'}), ['sick'])
        self.assertEqual(match('chat_emotion', {'emotion': 'happy'}), ['happy'])
        self.assertEqual(match('chat_emotion', {'emotion': 'annoyed'}), ['crouch'])
        self.assertEqual(match('chat_emotion', {'emotion': 'seeking_attention'}), [['look_left', 'look_right']])
        self.assertEqual(match('interaction', {'gesture': 'tap'}), [['look_left', 'look_right']])
        self.assertEqual(match('interaction', {'gesture': 'long_press'}), ['happy'])

    def test_missing_map_returns_503(self):
        self.consent()
        self.client.app.state.action_map = None
        response = self.client.get('/api/v1/config/action-map', headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['code'], 'CONFIG_UNAVAILABLE')


class ActionMapLoaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def write(self, text):
        (self.dir / 'action_map.yaml').write_text(text, encoding='utf-8')

    def test_missing_file_returns_none(self):
        self.assertIsNone(load_action_map(self.dir))

    def test_valid_file_loads(self):
        source = Path(__file__).resolve().parents[1] / 'rules' / 'action_map.yaml'
        self.write(source.read_text(encoding='utf-8'))
        loaded = load_action_map(self.dir)
        self.assertEqual(loaded['version'], 'am-2026-11-18')

    def test_invalid_action_rejected(self):
        self.write(
            'version: v1\nactions: [idle, jump]\npriority: [health]\n'
            'rules:\n  - {source: health, condition: {state: normal}, action: idle}\n'
        )
        with self.assertRaises(RuntimeError):
            load_action_map(self.dir)

    def test_unknown_rule_source_rejected(self):
        self.write(
            'version: v1\nactions: [idle, happy, sad, sick, crouch, look_left, look_right]\n'
            'priority: [health]\nrules:\n  - {source: mood, condition: {x: 1}, action: idle}\n'
        )
        with self.assertRaises(RuntimeError):
            load_action_map(self.dir)


if __name__ == '__main__':
    unittest.main()
