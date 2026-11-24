"""T10 建议模块：模板加载、提示词构建、LLM 输出解析与禁词守卫。"""

import unittest
from pathlib import Path

from app.services.advice import AdviceError, build_advice_messages, load_advice_templates, parse_advice, template_advice

RULES_DIR = Path(__file__).resolve().parents[1] / 'rules'


class TemplateTests(unittest.TestCase):
    def test_load_templates(self):
        templates = load_advice_templates(RULES_DIR)
        self.assertIsNotNone(templates)
        self.assertEqual(templates['version'], 'at-2026-11-19')
        for state in ('normal', 'observe', 'vet', 'urgent'):
            self.assertIn(state, templates['states'])
            self.assertTrue(templates['states'][state]['text'])
            self.assertTrue(templates['states'][state]['tips'])

    def test_missing_directory_returns_none(self):
        self.assertIsNone(load_advice_templates(Path('/nonexistent-rules-dir')))

    def test_invalid_templates_raise(self):
        import tempfile

        import yaml

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'advice_templates.yaml'
            path.write_text(
                yaml.safe_dump({'version': 'x', 'states': {'normal': {'text': 't', 'tips': ['a']}}}), encoding='utf-8'
            )
            with self.assertRaises(RuntimeError):
                load_advice_templates(Path(tmp))

    def test_template_advice_shape_and_no_forbidden_words(self):
        templates = load_advice_templates(RULES_DIR)
        for state in ('normal', 'observe', 'vet', 'urgent'):
            advice = template_advice(templates, state)
            self.assertEqual(advice['source'], 'template')
            self.assertEqual(advice['template_version'], 'at-2026-11-19')
            self.assertTrue(advice['text'])
            self.assertTrue(advice['tips'])
            blob = advice['text'] + ''.join(advice['tips'])
            self.assertNotIn('确诊', blob)
            self.assertNotIn('治疗', blob)

    def test_unknown_state_raises(self):
        templates = load_advice_templates(RULES_DIR)
        with self.assertRaises(KeyError):
            template_advice(templates, 'bogus')


class PromptTests(unittest.TestCase):
    def test_messages_contain_answers_and_constraints(self):
        screening = {
            'state': 'observe',
            'spirit': 'slightly_down',
            'appetite': 'decreased',
            'rules_version': 'sx-2026-11-19+rl-2026-11-19',
        }
        symptoms = [
            {
                'code': 'vomiting',
                'label': '呕吐',
                'duration': '2-12h',
                'frequency': '2-3',
                'notes': '饭后吐',
                'severe': False,
                'grade': 'observe',
            }
        ]
        messages = build_advice_messages(screening, symptoms)
        self.assertEqual(messages[0]['role'], 'system')
        self.assertIn('确诊', messages[0]['content'])
        self.assertIn('治疗', messages[0]['content'])
        user = messages[1]['content']
        for fragment in ('observe', 'slightly_down', 'decreased', '呕吐', '2-12h', '2-3', '饭后吐'):
            self.assertIn(fragment, user)


class ParseTests(unittest.TestCase):
    def test_parse_valid_json(self):
        advice = parse_advice('{"text": "建议观察精神与食欲变化。", "tips": ["记录呕吐频次", "保证饮水"]}')
        self.assertEqual(advice['text'], '建议观察精神与食欲变化。')
        self.assertEqual(advice['tips'], ['记录呕吐频次', '保证饮水'])

    def test_parse_json_in_code_fence(self):
        advice = parse_advice('```json\n{"text": "t", "tips": ["a"]}\n```')
        self.assertEqual(advice['text'], 't')

    def test_invalid_json_raises(self):
        with self.assertRaises(AdviceError):
            parse_advice('这不是 JSON')

    def test_missing_fields_raise(self):
        with self.assertRaises(AdviceError):
            parse_advice('{"tips": ["a"]}')
        with self.assertRaises(AdviceError):
            parse_advice('{"text": "  ", "tips": []}')

    def test_forbidden_words_raise(self):
        with self.assertRaises(AdviceError):
            parse_advice('{"text": "可确诊为肠胃炎", "tips": []}')
        with self.assertRaises(AdviceError):
            parse_advice('{"text": "建议观察", "tips": ["自行治疗"]}')


if __name__ == '__main__':
    unittest.main()
