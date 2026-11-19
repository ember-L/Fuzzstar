"""录音解读纯逻辑与 Provider（FRD F09-3/4；worker/API 集成见 test_audio_api.py）。"""
import io
import unittest
import wave
from pathlib import Path

from app.audio import (AUDIO_FOOTER, AudioReplyError, build_audio_persona_messages,
                       normalize_emotion, parse_audio_reply)
from app.chat import EMOTIONS, load_chat_config
from app.media import MAX_AUDIO_BYTES, valid_audio
from app.providers.base import EmotionResult
from app.providers.fake import FakeAudioProvider

RULES_DIR = Path(__file__).resolve().parents[1] / 'rules'
FENCE = chr(96) * 3


def wav_bytes(seconds: float, rate: int = 8000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b'\x00\x00' * int(rate * seconds))
    return buffer.getvalue()


class AudioConfigTests(unittest.TestCase):
    def setUp(self):
        self.config = load_chat_config(RULES_DIR)

    def test_audio_config_keys(self):
        self.assertEqual(self.config['audio_confidence_threshold'], 0.4)
        self.assertEqual(self.config['audio_min_seconds'], 1)
        self.assertEqual(self.config['audio_max_seconds'], 60)
        self.assertEqual(self.config['unrecognized_label'], '未识别')
        self.assertEqual(self.config['audio_footer'], '情绪解读为娱乐性参考,置信度仅供判断展示。')
        self.assertTrue(self.config['audio_fallback_reply'])
        for word in ('确诊', '治疗', '诊断'):
            self.assertNotIn(word, self.config['audio_fallback_reply'])

    def test_footer_constant_matches_frd(self):
        self.assertEqual(AUDIO_FOOTER, '情绪解读为娱乐性参考,置信度仅供判断展示。')


class ParseAudioReplyTests(unittest.TestCase):
    def setUp(self):
        self.config = load_chat_config(RULES_DIR)

    def test_plain_and_fenced_json(self):
        self.assertEqual(parse_audio_reply('{"reply": "喵～我听到啦"}', self.config), '喵～我听到啦')
        fenced = '\n' + FENCE + 'json\n{"reply": "蹭蹭你"}\n' + FENCE + '\n'
        self.assertEqual(parse_audio_reply(fenced, self.config), '蹭蹭你')

    def test_forbidden_words_raise(self):
        for word in ('确诊', '治疗', '诊断'):
            with self.assertRaises(AudioReplyError):
                parse_audio_reply('{"reply": "需要' + word + '"}', self.config)

    def test_truncates_to_reply_max(self):
        long_reply = '喵' * 300
        parsed = parse_audio_reply('{"reply": "' + long_reply + '"}', self.config)
        self.assertEqual(len(parsed), self.config['reply_max'])

    def test_invalid_payloads_raise(self):
        for raw in ('不是 JSON', '{"reply": 42}', '{"text": "缺少 reply"}', ''):
            with self.assertRaises(AudioReplyError):
                parse_audio_reply(raw, self.config)


class PersonaMessagesTests(unittest.TestCase):
    def setUp(self):
        self.config = load_chat_config(RULES_DIR)
        self.pet = {'name': '团团', 'species': 'cat', 'breed': None, 'sex': 'unknown',
                    'age_months': 24, 'neutered': True, 'body_type': 'standard'}

    def test_system_contains_emotion_and_contract(self):
        messages = build_audio_persona_messages(self.pet, 'normal', 'happy', 0.82,
                                                [{'role': 'user', 'content': '你好'}], self.config)
        self.assertEqual(messages[0]['role'], 'system')
        system = messages[0]['content']
        self.assertIn('团团', system)
        self.assertIn('happy', system)
        self.assertIn('reply', system)
        self.assertIn(self.config['disclaimer'], system)
        self.assertEqual(messages[-1], {'role': 'user', 'content': '你好'})

    def test_sick_tone_for_urgent_screening(self):
        messages = build_audio_persona_messages(self.pet, 'urgent', 'painful', 0.9, [], self.config)
        self.assertIn('不适', messages[0]['content'])


class NormalizeEmotionTests(unittest.TestCase):
    def setUp(self):
        self.config = load_chat_config(RULES_DIR)

    def test_valid_emotion_with_confidence(self):
        result = normalize_emotion('happy', 0.82, self.config)
        self.assertEqual(result, {'emotion': 'happy', 'confidence': 0.82, 'uncertain': False})

    def test_low_confidence_marks_uncertain(self):
        self.assertTrue(normalize_emotion('sad', 0.39, self.config)['uncertain'])
        self.assertFalse(normalize_emotion('happy', 0.4, self.config)['uncertain'])

    def test_clamps_confidence_range(self):
        self.assertEqual(normalize_emotion('happy', 1.7, self.config)['confidence'], 1.0)
        self.assertEqual(normalize_emotion('happy', -0.2, self.config)['confidence'], 0.0)

    def test_unknown_emotion_becomes_unrecognized(self):
        result = normalize_emotion('angry', 0.9, self.config)
        self.assertEqual(result['emotion'], 'unrecognized')
        self.assertIsNone(result['confidence'])
        self.assertTrue(result['uncertain'])

    def test_all_six_emotions_accepted(self):
        for emotion in EMOTIONS:
            self.assertEqual(normalize_emotion(emotion, 0.5, self.config)['emotion'], emotion)


class ValidAudioTests(unittest.TestCase):
    def test_one_second_wav_passes(self):
        self.assertTrue(valid_audio(wav_bytes(1), 'audio/wav'))

    def test_sixty_seconds_passes_and_sixty_one_fails(self):
        self.assertTrue(valid_audio(wav_bytes(60), 'audio/wav'))
        self.assertFalse(valid_audio(wav_bytes(61), 'audio/wav'))

    def test_too_short_fails(self):
        self.assertFalse(valid_audio(wav_bytes(0.5), 'audio/wav'))

    def test_wrong_content_type_fails(self):
        self.assertFalse(valid_audio(wav_bytes(2), 'image/png'))

    def test_garbage_bytes_fail(self):
        self.assertFalse(valid_audio(b'not audio at all', 'audio/wav'))

    def test_size_limit_constant(self):
        self.assertEqual(MAX_AUDIO_BYTES, 10 * 1024 * 1024)


class FakeAudioProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_interpret_returns_result_and_records_call(self):
        provider = FakeAudioProvider(emotion='fearful', confidence=0.55)
        result = await provider.interpret('https://audio.example/x.wav', '解读情绪')
        self.assertIsInstance(result, EmotionResult)
        self.assertEqual((result.emotion, result.confidence), ('fearful', 0.55))
        self.assertEqual(provider.calls, [{'audio_url': 'https://audio.example/x.wav', 'prompt': '解读情绪'}])

    async def test_fail_raises(self):
        provider = FakeAudioProvider(fail=True)
        with self.assertRaises(RuntimeError):
            await provider.interpret('https://audio.example/x.wav', '解读情绪')


if __name__ == '__main__':
    unittest.main()
