import tempfile
import unittest
from pathlib import Path

from app.triage import RulesBundle, load_rules, symptoms_config, triage, validate_answers

RULES_DIR = Path(__file__).resolve().parents[1] / 'rules'


def answers(spirit='normal', appetite='normal', symptoms=(), redline_options=()):
    return {'spirit': spirit, 'appetite': appetite,
            'symptoms': [dict(s) for s in symptoms], 'redline_options': list(redline_options)}


def symptom(code, duration='2-12h', **kw):
    return {'code': code, 'duration': duration, **kw}


class RuleLoaderTests(unittest.TestCase):
    def test_loads_versioned_bundle(self):
        bundle = load_rules(RULES_DIR)
        self.assertIsInstance(bundle, RulesBundle)
        self.assertEqual(bundle.rules_version, 'sx-2026-11-19+rl-2026-11-19')
        self.assertEqual(len(bundle.symptoms['symptoms']), 15)
        self.assertEqual(len(bundle.redlines['redlines']), 6)
        self.assertEqual(bundle.scoring['deltas'], {'observe': 10, 'vet': 30, 'urgent': 60})

    def test_missing_directory_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(load_rules(Path(tmp)))

    def test_invalid_rules_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'symptoms.yaml').write_text('version: sx-x\nsymptoms: []\n', encoding='utf-8')
            (root / 'redlines.yaml').write_text('version: rl-x\nredlines: []\n', encoding='utf-8')
            (root / 'scoring.yaml').write_text('version: sc-x\ndeltas: {observe: 10, vet: 30, urgent: 60}\n', encoding='utf-8')
            with self.assertRaises(RuntimeError):
                load_rules(root)


class GradingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load_rules(RULES_DIR)

    def grade(self, payload):
        return triage(self.bundle, payload)

    def test_no_symptoms_normal(self):
        result = self.grade(answers())
        self.assertEqual(result['state'], 'normal')
        self.assertFalse(result['redline_hit'])
        self.assertEqual(result['symptom_grades'], {})

    def test_spirit_markedly_down_alone_triggers_vet(self):
        self.assertEqual(self.grade(answers(spirit='markedly_down'))['state'], 'vet')

    def test_appetite_refused_alone_triggers_vet(self):
        self.assertEqual(self.grade(answers(appetite='refused'))['state'], 'vet')

    def test_appendix_a_grading_table(self):
        cases = [
            ('vomiting', {'duration': '2-12h', 'frequency': '2-3'}, 'observe'),
            ('vomiting', {'duration': '<2h', 'frequency': '4-6'}, 'vet'),
            ('vomiting', {'duration': '12-24h', 'frequency': '1'}, 'vet'),
            ('diarrhea', {'duration': '12-24h', 'frequency': '2-3'}, 'observe'),
            ('diarrhea', {'duration': '>24h', 'frequency': '1'}, 'vet'),
            ('diarrhea', {'duration': '<2h', 'frequency': '>6'}, 'vet'),
            ('constipation', {'duration': '12-24h'}, 'observe'),
            ('constipation', {'duration': '>24h'}, 'vet'),
            ('constipation', {'duration': '<2h', 'severe': True}, 'vet'),
            ('appetite_down', {'duration': '12-24h'}, 'observe'),
            ('appetite_down', {'duration': '>24h'}, 'vet'),
            ('lethargy', {'duration': '12-24h'}, 'observe'),
            ('lethargy', {'duration': '>24h'}, 'vet'),
            ('cough_sneeze', {'duration': '12-24h', 'frequency': '2-3'}, 'observe'),
            ('cough_sneeze', {'duration': '>24h', 'frequency': '1'}, 'vet'),
            ('cough_sneeze', {'duration': '<2h', 'frequency': '>6'}, 'vet'),
            ('eye_nose_discharge', {'duration': '12-24h'}, 'observe'),
            ('eye_nose_discharge', {'duration': '<2h', 'severe': True}, 'vet'),
            ('eye_nose_discharge', {'duration': '>24h'}, 'vet'),
            ('skin_itch_hairloss', {'duration': '2-12h'}, 'observe'),
            ('skin_itch_hairloss', {'duration': '2-12h', 'severe': True}, 'vet'),
            ('urination_abnormal', {'duration': '2-12h', 'frequency': '2-3'}, 'observe'),
            ('urination_abnormal', {'duration': '<2h', 'frequency': '1', 'severe': True}, 'vet'),
            ('limping', {'duration': '12-24h'}, 'observe'),
            ('limping', {'duration': '>24h'}, 'vet'),
            ('limping', {'duration': '<2h', 'severe': True}, 'vet'),
            ('weight_loss', {'duration': '>24h'}, 'observe'),
            ('weight_loss', {'duration': '>24h', 'severe': True}, 'vet'),
            ('feverish', {'duration': '2-12h'}, 'observe'),
            ('feverish', {'duration': '12-24h'}, 'vet'),
            ('ear_abnormal', {'duration': '12-24h'}, 'observe'),
            ('ear_abnormal', {'duration': '>24h'}, 'vet'),
            ('ear_abnormal', {'duration': '2-12h', 'severe': True}, 'vet'),
            ('oral_odor', {'duration': '2-12h'}, 'observe'),
            ('oral_odor', {'duration': '<2h', 'severe': True}, 'vet'),
            ('drooling', {'duration': '<2h', 'frequency': '1'}, 'observe'),
            ('drooling', {'duration': '<2h', 'frequency': '2-3'}, 'vet'),
            ('drooling', {'duration': '<2h', 'frequency': '1', 'severe': True}, 'vet'),
        ]
        for code, follow, expected in cases:
            with self.subTest(symptom=code, follow=follow):
                result = self.grade(answers(symptoms=[symptom(code, **follow)]))
                self.assertEqual(result['symptom_grades'][code], expected)
                self.assertEqual(result['state'], expected)

    def test_diarrhea_with_spirit_down_escalates(self):
        result = self.grade(answers(spirit='slightly_down',
                                    symptoms=[symptom('diarrhea', duration='<2h', frequency='1')]))
        self.assertEqual(result['state'], 'vet')

    def test_feverish_with_appetite_down_escalates(self):
        result = self.grade(answers(appetite='decreased', symptoms=[symptom('feverish', duration='<2h')]))
        self.assertEqual(result['state'], 'vet')

    def test_multiple_symptoms_take_highest(self):
        result = self.grade(answers(symptoms=[
            symptom('vomiting', duration='<2h', frequency='1'),
            symptom('limping', duration='>24h'),
        ]))
        self.assertEqual(result['state'], 'vet')
        self.assertEqual(result['symptom_grades'], {'vomiting': 'observe', 'limping': 'vet'})

    def test_same_version_reproducible(self):
        payload = answers(symptoms=[symptom('vomiting', duration='2-12h', frequency='2-3', notes='偶尔吐')])
        first, second = self.grade(payload), self.grade(payload)
        self.assertEqual(first, second)
        self.assertEqual(first['rules_version'], 'sx-2026-11-19+rl-2026-11-19')


class RedlineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load_rules(RULES_DIR)

    def test_each_explicit_redline_hits_urgent(self):
        options = ['open_mouth_breathing', 'convulsions', 'frequent_litter_no_urine', 'lily', 'persistent_bleeding']
        for option in options:
            with self.subTest(option=option):
                result = triage(self.bundle, answers(redline_options=[option]))
                self.assertEqual(result['state'], 'urgent')
                self.assertTrue(result['redline_hit'])
                self.assertEqual(len(result['redlines']), 1)

    def test_derived_vomiting_over_24h(self):
        result = triage(self.bundle, answers(symptoms=[symptom('vomiting', duration='>24h', frequency='1')]))
        self.assertEqual(result['state'], 'urgent')
        self.assertIn('vomiting_persistent', result['redlines'])

    def test_vomiting_12_24h_is_vet_not_redline(self):
        result = triage(self.bundle, answers(symptoms=[symptom('vomiting', duration='12-24h', frequency='1')]))
        self.assertEqual(result['state'], 'vet')
        self.assertFalse(result['redline_hit'])

    def test_redline_beats_grading(self):
        result = triage(self.bundle, answers(symptoms=[symptom('oral_odor')], redline_options=['convulsions']))
        self.assertEqual(result['state'], 'urgent')


class ValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load_rules(RULES_DIR)

    def fields(self, payload):
        return [e['field'] for e in validate_answers(self.bundle, payload)]

    def test_valid_answers_no_errors(self):
        self.assertEqual(self.fields(answers(symptoms=[symptom('vomiting', frequency='1')])), [])

    def test_missing_basics_located(self):
        payload = answers()
        del payload['spirit']
        del payload['appetite']
        self.assertEqual(self.fields(payload), ['spirit', 'appetite'])

    def test_missing_follow_ups_located(self):
        payload = answers(symptoms=[{'code': 'vomiting'}])
        self.assertEqual(self.fields(payload), ['symptoms[0].duration', 'symptoms[0].frequency'])

    def test_frequency_not_required_for_duration_only_symptom(self):
        self.assertEqual(self.fields(answers(symptoms=[symptom('limping')])), [])

    def test_notes_limit_and_unknown_codes(self):
        payload = answers(symptoms=[symptom('limping', notes='x' * 256), symptom('nope')],
                          redline_options=['bogus'])
        fields = self.fields(payload)
        self.assertIn('symptoms[0].notes', fields)
        self.assertIn('symptoms[1].code', fields)
        self.assertIn('redline_options[0]', fields)

    def test_duplicate_symptom_rejected(self):
        payload = answers(symptoms=[symptom('limping'), symptom('limping')])
        self.assertIn('symptoms[1].code', self.fields(payload))


class ConfigPayloadTests(unittest.TestCase):
    def test_config_shape(self):
        bundle = load_rules(RULES_DIR)
        config = symptoms_config(bundle)
        self.assertEqual(config['version'], 'sx-2026-11-19')
        self.assertEqual(config['duration_bands'], ['<2h', '2-12h', '12-24h', '>24h'])
        self.assertEqual(config['frequency_bands'], ['1', '2-3', '4-6', '>6'])
        self.assertEqual(len(config['symptoms']), 15)
        vomiting = next(s for s in config['symptoms'] if s['code'] == 'vomiting')
        self.assertTrue(vomiting['frequency'])
        self.assertEqual(len(config['redlines']), 6)
        derived = next(r for r in config['redlines'] if r['code'] == 'vomiting_persistent')
        self.assertEqual(derived['derived'], {'symptom': 'vomiting', 'duration': ['>24h']})


if __name__ == '__main__':
    unittest.main()
