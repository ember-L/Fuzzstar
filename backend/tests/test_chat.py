"""T15 文字聊天与安全边界（FRD F09-1/2/5/7）。

人设上下文=档案+最新初筛状态+免责；红线关键词零 LLM 附就医引导卡；
LLM 失败/禁词/解析失败降级模板安抚，对话不中断；用量全审计。
"""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import select
from sqlalchemy.orm import Session
from test_auth_api import AuthAPIFixture

from app.models import AiUsageLog
from app.providers.fake import FakeLLMProvider
from app.services.chat import (
    CHAT_DISCLAIMER,
    REDLINE_SUBTITLE,
    ChatReplyError,
    build_persona_messages,
    detect_redline,
    fallback_reply,
    load_chat_config,
    parse_chat_reply,
    redline_response,
)
from app.services.identity import create_email_account

RULES_DIR = Path(__file__).resolve().parents[1] / 'rules'
CONFIG = load_chat_config(RULES_DIR)
PET = {
    'name': '团团',
    'species': 'cat',
    'breed': '狸花',
    'sex': 'female',
    'age_months': 30,
    'neutered': True,
    'body_type': 'standard',
}


class ChatLogicTests(unittest.TestCase):
    def test_load_config_defaults(self):
        self.assertEqual(CONFIG['version'], 'ct-2026-11-19')
        self.assertEqual((CONFIG['context_window'], CONFIG['input_max'], CONFIG['reply_max']), (20, 500, 100))
        self.assertEqual(CONFIG['disclaimer'], CHAT_DISCLAIMER)

    def test_load_config_missing_returns_none(self):
        with TemporaryDirectory() as tmp:
            self.assertIsNone(load_chat_config(Path(tmp)))

    def test_load_config_rejects_empty_keywords(self):
        with TemporaryDirectory() as tmp:
            (Path(tmp) / 'chat.yaml').write_text(
                'version: ct-x\ncontext_window: 20\ninput_max: 500\nreply_max: 100\n'
                'disclaimer: 参考\nredline_keywords: []\nfallback_reply: 喵\nredline_reply: 就医\n',
                encoding='utf-8',
            )
            with self.assertRaises(RuntimeError):
                load_chat_config(Path(tmp))

    def test_detect_redline_variants(self):
        self.assertTrue(detect_redline('猫咪张嘴呼吸了', CONFIG))
        self.assertTrue(detect_redline('它张口呼吸', CONFIG))
        self.assertTrue(detect_redline('好像吃了百合', CONFIG))
        self.assertFalse(detect_redline('今天吃了 50g 猫粮', CONFIG))

    def test_persona_prompt_profile_and_contract(self):
        messages = build_persona_messages(PET, None, [], CONFIG)
        system = messages[0]
        self.assertEqual(system['role'], 'system')
        for fragment in ('团团', '狸花', '绝育', CHAT_DISCLAIMER, '100', 'emotion', 'reply'):
            self.assertIn(fragment, system['content'])

    def test_persona_prompt_sick_tone_follows_latest_screening(self):
        for state in ('observe', 'vet', 'urgent'):
            system = build_persona_messages(PET, state, [], CONFIG)[0]['content']
            self.assertIn('不适', system)
        normal = build_persona_messages(PET, 'normal', [], CONFIG)[0]['content']
        self.assertNotIn('最近身体不适', normal)

    def test_parse_reply_valid_and_emotion_default(self):
        parsed = parse_chat_reply('{"reply": "喵～我在呢", "emotion": "happy"}', CONFIG)
        self.assertEqual(parsed, {'reply': '喵～我在呢', 'emotion': 'happy'})
        relaxed = parse_chat_reply('{"reply": "嗯", "emotion": "unknown"}', CONFIG)
        self.assertEqual(relaxed['emotion'], 'relaxed')

    def test_parse_reply_forbidden_words_raise(self):
        for word in ('确诊', '治疗', '诊断'):
            with self.assertRaises(ChatReplyError):
                parse_chat_reply(json.dumps({'reply': f'可能是{word}了', 'emotion': 'sad'}), CONFIG)

    def test_parse_reply_truncates_to_limit(self):
        parsed = parse_chat_reply(json.dumps({'reply': '喵' * 150, 'emotion': 'happy'}), CONFIG)
        self.assertEqual(len(parsed['reply']), 100)

    def test_parse_reply_invalid_json_raises(self):
        with self.assertRaises(ChatReplyError):
            parse_chat_reply('不是 JSON', CONFIG)

    def test_templates_carry_disclaimer_boundary(self):
        fallback = fallback_reply(CONFIG)
        self.assertEqual((fallback['emotion'], fallback['source']), ('relaxed', 'template'))
        self.assertTrue(fallback['reply'])
        redline = redline_response(CONFIG)
        self.assertEqual(redline['emotion'], 'painful')
        self.assertEqual(redline['guidance']['title'], '建议立即就医')
        self.assertEqual(redline['guidance']['text'], REDLINE_SUBTITLE)
        self.assertEqual(redline['guidance']['route'], 'screening')


class ChatFixture(AuthAPIFixture):
    def setUp(self):
        super().setUp()
        self.headers = {'Authorization': f'Bearer {self.login().json()["access_token"]}'}
        self.client.post('/api/v1/consents', headers=self.headers, json={'privacy': 'p1', 'terms': 't1'})
        pet = self.client.post('/api/v1/pets', headers=self.headers, json={'name': '团团'})
        self.pet_id = pet.json()['id']
        self.app.state.chat_llm_provider = FakeLLMProvider(reply='{"reply": "喵～我在呢", "emotion": "happy"}')
        self.session_id = self.client.post(f'/api/v1/pets/{self.pet_id}/chat/sessions', headers=self.headers).json()[
            'session_id'
        ]

    @property
    def app(self):
        return self.client.app

    @property
    def provider(self):
        return self.app.state.chat_llm_provider

    def verified_account(self, email, consent=True):
        with Session(self.engine) as db, db.begin():
            create_email_account(db, email, self.password, self.now)
        headers = {'Authorization': f'Bearer {self.login(email).json()["access_token"]}'}
        if consent:
            self.client.post(
                '/api/v1/consents', headers=headers, json={'privacy': 'p1', 'terms': 't1'}
            ).raise_for_status()
        return headers

    def send(self, content, **extra):
        return self.client.post(
            f'/api/v1/chat/sessions/{self.session_id}/messages',
            headers=self.headers,
            json={'kind': 'text', 'content': content, **extra},
        )

    def make_screening(self, state):
        answers = {'spirit': 'normal', 'appetite': 'normal', 'symptoms': [], 'redline_options': [], 'media_ids': []}
        if state == 'urgent':
            answers['symptoms'] = [{'code': 'vomiting', 'duration': '>24h', 'frequency': '2-3'}]
        response = self.client.post(f'/api/v1/pets/{self.pet_id}/screenings', headers=self.headers, json=answers)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['state'], state)


class ChatAPITests(ChatFixture, unittest.TestCase):
    def test_session_auto_create_and_idempotent(self):
        again = self.client.post(f'/api/v1/pets/{self.pet_id}/chat/sessions', headers=self.headers)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()['session_id'], self.session_id)
        listing = self.client.get(f'/api/v1/pets/{self.pet_id}/chat/sessions', headers=self.headers)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.json()['items']), 1)

    def test_send_text_returns_sync_persona_reply(self):
        response = self.send('你好呀')
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual((body['user_message']['role'], body['user_message']['content']), ('user', '你好呀'))
        self.assertEqual((body['pet_message']['role'], body['pet_message']['content']), ('pet', '喵～我在呢'))
        self.assertEqual(body['pet_message']['emotion_label'], 'happy')
        self.assertEqual(body['pet_message']['source'], 'llm')
        self.assertIsNone(body['guidance'])
        self.assertEqual(response.headers['Cache-Control'], 'no-store')

    def test_input_limits_and_extra_fields(self):
        too_long = self.send('喵' * 501)
        self.assertEqual(too_long.status_code, 400)
        self.assertIn('content', [f['field'] for f in too_long.json()['detail']['fields']])
        self.assertEqual(self.send('   ').status_code, 400)
        self.assertEqual(self.send(' hi', unexpected=1).status_code, 400)

    def test_context_window_keeps_latest_20(self):
        for index in range(25):
            self.send(f'历史消息{index}').raise_for_status()
        self.provider.calls.clear()
        self.send('第26条').raise_for_status()
        messages = self.provider.calls[-1]['messages']
        history = [m for m in messages if m['role'] != 'system']
        self.assertEqual(len(history), 20)
        self.assertEqual(history[-1]['content'], '第26条')
        self.assertNotIn('历史消息15', json.dumps(messages, ensure_ascii=False))
        self.assertIn('历史消息16', json.dumps(messages, ensure_ascii=False))

    def test_persona_prompt_uses_latest_screening_state(self):
        self.make_screening('urgent')
        self.provider.calls.clear()
        self.send('它今天怎么了').raise_for_status()
        system = self.provider.calls[-1]['messages'][0]['content']
        self.assertIn('不适', system)

    def test_redline_keyword_bypasses_llm_with_guidance(self):
        before = len(self.provider.calls)
        response = self.send('猫咪张嘴呼吸了，怎么办')
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(len(self.provider.calls), before)
        self.assertEqual(body['pet_message']['content'], CONFIG['redline_reply'])
        self.assertEqual(body['pet_message']['emotion_label'], 'painful')
        self.assertEqual(body['pet_message']['source'], 'template')
        self.assertEqual(body['guidance']['title'], '建议立即就医')
        self.assertEqual(body['guidance']['text'], REDLINE_SUBTITLE)
        with Session(self.engine) as db:
            self.assertEqual(db.scalars(select(AiUsageLog)).all(), [])

    def test_llm_failure_falls_back_and_conversation_continues(self):
        self.provider.fail_times = 1
        failed = self.send('在吗')
        self.assertEqual(failed.status_code, 201)
        self.assertEqual(failed.json()['pet_message']['content'], CONFIG['fallback_reply'])
        self.assertEqual(failed.json()['pet_message']['source'], 'template')
        recovered = self.send('还在吗')
        self.assertEqual(recovered.status_code, 201)
        self.assertEqual(recovered.json()['pet_message']['source'], 'llm')

    def test_forbidden_llm_output_falls_back(self):
        self.provider.reply = '{"reply": "这是确诊了", "emotion": "sad"}'
        response = self.send('它生病了吗')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['pet_message']['content'], CONFIG['fallback_reply'])

    def test_long_llm_reply_truncated(self):
        self.provider.reply = json.dumps({'reply': '喵' * 150, 'emotion': 'happy'}, ensure_ascii=False)
        response = self.send('说点什么')
        self.assertEqual(len(response.json()['pet_message']['content']), 100)

    def test_usage_logs_audit_success_and_failure(self):
        self.send('第一条').raise_for_status()
        self.provider.fail_times = 1
        self.send('第二条').raise_for_status()
        with Session(self.engine) as db:
            logs = db.scalars(select(AiUsageLog).order_by(AiUsageLog.id)).all()
            self.assertEqual(len(logs), 2)
            self.assertEqual(
                (logs[0].kind, logs[0].task_id, logs[0].tokens_in, logs[0].tokens_out), ('llm', None, 100, 30)
            )
            self.assertIsNone(logs[1].tokens_in)

    def test_history_pagination_descending_with_cursor(self):
        for index in range(5):
            self.send(f'消息{index}').raise_for_status()
        page = self.client.get(
            f'/api/v1/chat/sessions/{self.session_id}/messages', headers=self.headers, params={'limit': 4}
        )
        page.raise_for_status()
        items = page.json()['items']
        self.assertEqual(len(items), 4)
        self.assertGreater(items[0]['id'], items[-1]['id'])
        self.assertEqual(items[0]['role'], 'pet')
        older = self.client.get(
            f'/api/v1/chat/sessions/{self.session_id}/messages',
            headers=self.headers,
            params={'limit': 4, 'before': page.json()['next_before']},
        )
        older.raise_for_status()
        self.assertEqual(len(older.json()['items']), 4)
        self.assertLess(older.json()['items'][0]['id'], items[-1]['id'])
        last = self.client.get(
            f'/api/v1/chat/sessions/{self.session_id}/messages',
            headers=self.headers,
            params={'limit': 4, 'before': older.json()['next_before']},
        )
        last.raise_for_status()
        self.assertEqual(len(last.json()['items']), 2)
        self.assertIsNone(last.json()['next_before'])

    def test_audio_kind_not_accepted_until_t16(self):
        response = self.client.post(
            f'/api/v1/chat/sessions/{self.session_id}/messages',
            headers=self.headers,
            json={'kind': 'audio', 'content': 'x'},
        )
        self.assertEqual(response.status_code, 400)

    def test_missing_config_returns_503(self):
        self.app.state.chat_config = None
        response = self.client.post(f'/api/v1/pets/{self.pet_id}/chat/sessions', headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['code'], 'CONFIG_UNAVAILABLE')

    def test_no_provider_still_chats_with_template(self):
        self.app.state.chat_llm_provider = None
        response = self.send('在吗')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['pet_message']['content'], CONFIG['fallback_reply'])

    def test_ownership_and_consent_gates(self):
        self.assertEqual(self.client.get(f'/api/v1/chat/sessions/{self.session_id}/messages').status_code, 401)
        other_headers = self.verified_account('other@example.com', consent=False)
        self.assertEqual(
            self.client.post(f'/api/v1/pets/{self.pet_id}/chat/sessions', headers=other_headers).status_code, 403
        )
        stranger_headers = self.verified_account('stranger@example.com', consent=True)
        self.assertEqual(
            self.client.get(f'/api/v1/chat/sessions/{self.session_id}/messages', headers=stranger_headers).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f'/api/v1/chat/sessions/{self.session_id}/messages',
                headers=stranger_headers,
                json={'kind': 'text', 'content': 'hi'},
            ).status_code,
            404,
        )

    def test_threads_isolated_per_pet(self):
        second = self.client.post('/api/v1/pets', headers=self.headers, json={'name': '圆圆'})
        second_pet = second.json()['id']
        second_session = self.client.post(f'/api/v1/pets/{second_pet}/chat/sessions', headers=self.headers).json()[
            'session_id'
        ]
        self.assertNotEqual(second_session, self.session_id)
        self.send('团团专属秘密').raise_for_status()
        self.provider.calls.clear()
        self.client.post(
            f'/api/v1/chat/sessions/{second_session}/messages',
            headers=self.headers,
            json={'kind': 'text', 'content': '你好'},
        ).raise_for_status()
        self.assertNotIn('团团专属秘密', json.dumps(self.provider.calls[-1]['messages'], ensure_ascii=False))

    def test_idempotent_replay_does_not_duplicate(self):
        headers = {**self.headers, 'Idempotency-Key': 'chat-key-1'}
        url = f'/api/v1/chat/sessions/{self.session_id}/messages'
        first = self.client.post(url, headers=headers, json={'kind': 'text', 'content': '在吗'})
        self.assertEqual(first.status_code, 201)
        calls = len(self.provider.calls)
        again = self.client.post(url, headers=headers, json={'kind': 'text', 'content': '在吗'})
        self.assertEqual(again.status_code, 201)
        self.assertEqual(again.headers['Idempotent-Replay'], 'true')
        self.assertEqual(again.json(), first.json())
        self.assertEqual(len(self.provider.calls), calls)
        listing = self.client.get(url, headers=self.headers)
        self.assertEqual(len(listing.json()['items']), 2)

    def test_idempotency_conflict_on_different_body(self):
        headers = {**self.headers, 'Idempotency-Key': 'chat-key-2'}
        url = f'/api/v1/chat/sessions/{self.session_id}/messages'
        self.client.post(url, headers=headers, json={'kind': 'text', 'content': '甲'}).raise_for_status()
        conflict = self.client.post(url, headers=headers, json={'kind': 'text', 'content': '乙'})
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()['code'], 'IDEMPOTENCY_CONFLICT')

    def test_invalid_idempotency_key_rejected(self):
        headers = {**self.headers, 'Idempotency-Key': 'k' * 65}
        response = self.client.post(
            f'/api/v1/chat/sessions/{self.session_id}/messages', headers=headers, json={'kind': 'text', 'content': 'hi'}
        )
        self.assertEqual(response.status_code, 400)


if __name__ == '__main__':
    unittest.main()
