"""T16 worker audio_interpret：情绪解读＋人设叠加＋失败降级（FRD F09-3/4，AC-09-3/4）。"""

import asyncio
import io
import unittest
import wave
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session
from test_worker import FakeAssets, make_engine

from app import worker
from app.core.security import utcnow
from app.models import AiUsageLog, ChatMessage, ChatSession, MediaUpload, Pet, Task, User
from app.providers.fake import FakeAudioProvider, FakeLLMProvider
from app.services.chat import load_chat_config
from app.services.tasks import enqueue_task

RULES_DIR = Path(__file__).resolve().parents[1] / 'rules'
CONFIG = load_chat_config(RULES_DIR)


def wav_bytes(seconds=1.0):
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b'\x00\x00' * int(8000 * seconds))
    return buffer.getvalue()


class InterpretAudioTests(unittest.TestCase):
    def setUp(self):
        self.engine = make_engine()
        self.addCleanup(self.engine.dispose)
        self.media_id = uuid4().hex
        with Session(self.engine) as db, db.begin():
            db.add(User(id=1, nickname='测试用户'))
            db.add(Pet(id=1, user_id=1, name='团团', species='cat', status='active'))
            db.add(
                MediaUpload(
                    id=self.media_id,
                    pet_id=1,
                    kind='audio',
                    content_type='audio/wav',
                    size_bytes=len(wav_bytes()),
                    expires_at=utcnow() + timedelta(minutes=10),
                    version_id='version-1',
                )
            )
            session = ChatSession(pet_id=1, user_id=1)
            db.add(session)
            db.flush()
            self.session_id = session.id
            message = ChatMessage(
                session_id=session.id, role='user', kind='audio', audio_url=f'audio/1/{self.media_id}'
            )
            db.add(message)
            db.flush()
            self.message_id = message.id
            task = enqueue_task(
                db,
                1,
                'audio_interpret',
                str(message.id),
                {'media_id': self.media_id, 'message_id': message.id, 'session_id': session.id},
            )
            self.task_id = task.id
            message.task_id = task.id
        self.assets = FakeAssets(photo=wav_bytes())
        self.audio = FakeAudioProvider()
        self.llm = FakeLLMProvider(reply='{"reply": "喵～我听起来很开心"}')

    def ctx(self, **overrides):
        base = {
            'engine': self.engine,
            'assets': self.assets,
            'audio_provider': self.audio,
            'llm_provider': self.llm,
            'chat_config': CONFIG,
        }
        base.update(overrides)
        return base

    def run_task(self, **overrides):
        asyncio.run(worker.run_task(self.ctx(**overrides), self.task_id))
        with Session(self.engine) as db:
            return db.get(Task, self.task_id)

    def pet_message(self):
        with Session(self.engine) as db:
            return db.scalars(select(ChatMessage).where(ChatMessage.role == 'pet')).one()

    def test_success_writes_emotion_and_persona_reply(self):
        task = self.run_task()
        self.assertEqual(task.status, 'succeeded')
        self.assertEqual(task.result['emotion'], 'happy')
        self.assertEqual(task.result['confidence'], 0.82)
        self.assertFalse(task.result['uncertain'])
        self.assertEqual(task.result['reply'], '喵～我听起来很开心')
        message = self.pet_message()
        self.assertEqual((message.kind, message.emotion_label), ('text', 'happy'))
        self.assertEqual(float(message.emotion_confidence), 0.82)
        self.assertEqual(message.task_id, self.task_id)
        self.assertEqual(task.result['pet_message_id'], message.id)
        self.assertEqual(self.audio.calls[0]['audio_url'], f'https://fake.local/audio/1/{self.media_id}?v=version-1')
        with Session(self.engine) as db:
            logs = db.scalars(select(AiUsageLog).order_by(AiUsageLog.id)).all()
            self.assertEqual(
                [(log.kind, log.tokens_in, log.tokens_out) for log in logs], [('audio', 60, 20), ('llm', 100, 30)]
            )
            self.assertTrue(all(log.task_id == self.task_id for log in logs))

    def test_low_confidence_marks_uncertain_in_persona(self):
        self.audio = FakeAudioProvider('fearful', 0.25)
        task = self.run_task()
        self.assertTrue(task.result['uncertain'])
        self.assertIn('不太确定', self.llm.calls[0]['messages'][0]['content'])
        message = self.pet_message()
        self.assertEqual(message.emotion_label, 'fearful')
        self.assertEqual(float(message.emotion_confidence), 0.25)

    def test_audio_failure_degrades_to_unrecognized(self):
        self.audio = FakeAudioProvider(fail=True)
        task = self.run_task()
        self.assertEqual(task.status, 'succeeded')
        self.assertEqual(task.result['emotion'], 'unrecognized')
        self.assertIsNone(task.result['confidence'])
        self.assertEqual(task.result['reply'], CONFIG['audio_fallback_reply'])
        message = self.pet_message()
        self.assertIsNone(message.emotion_label)
        self.assertEqual(message.content, CONFIG['audio_fallback_reply'])
        self.assertEqual(self.llm.calls, [])
        with Session(self.engine) as db:
            logs = db.scalars(select(AiUsageLog)).all()
            self.assertEqual(len(logs), 1)
            self.assertEqual((logs[0].kind, logs[0].tokens_in), ('audio', None))

    def test_llm_failure_keeps_emotion_with_soothing_reply(self):
        self.llm = FakeLLMProvider(fail_times=1)
        task = self.run_task()
        self.assertEqual(task.status, 'succeeded')
        self.assertEqual(task.result['emotion'], 'happy')
        self.assertEqual(task.result['reply'], CONFIG['audio_fallback_reply'])
        self.assertEqual(self.pet_message().emotion_label, 'happy')
        with Session(self.engine) as db:
            logs = db.scalars(select(AiUsageLog).where(AiUsageLog.kind == 'llm')).all()
            self.assertEqual(logs[0].tokens_in, None)

    def test_invalid_audio_bytes_skip_provider(self):
        self.assets = FakeAssets(photo=b'not audio')
        task = self.run_task()
        self.assertEqual(task.result['emotion'], 'unrecognized')
        self.assertEqual(self.audio.calls, [])

    def test_missing_audio_provider_degrades(self):
        task = self.run_task(audio_provider=None)
        self.assertEqual(task.status, 'succeeded')
        self.assertEqual(task.result['emotion'], 'unrecognized')
        self.assertEqual(task.result['reply'], CONFIG['audio_fallback_reply'])

    def test_unverified_media_retries_via_db_attempts(self):
        with Session(self.engine) as db, db.begin():
            db.get(MediaUpload, self.media_id).version_id = None
        task = self.run_task()
        self.assertEqual(task.status, 'pending')
        self.assertEqual(task.attempts, 1)
        self.assertIsNone(task.result)

    def test_persona_history_is_windowed(self):
        with Session(self.engine) as db, db.begin():
            for index in range(25):
                db.add(ChatMessage(session_id=self.session_id, role='user', kind='text', content=f'历史消息{index}'))
        self.run_task()
        messages = self.llm.calls[0]['messages']
        self.assertEqual(messages[0]['role'], 'system')
        self.assertLessEqual(len(messages), 21)


if __name__ == '__main__':
    unittest.main()
