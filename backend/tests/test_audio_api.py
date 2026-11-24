"""T16 音频消息 API：presign audio、202 入队、进行中合并、签名播放地址（FRD F09-3/4）。"""

import unittest
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session
from test_chat import ChatFixture

from app.core.security import utcnow
from app.models import ChatMessage, MediaUpload, Task


class FakeStorage:
    def presign(self, photo):
        return {'url': 'https://fake.local/upload', 'fields': {'key': photo.object_key}}

    def asset_url(self, key, version_id):
        return f'https://fake.local/{key}?v={version_id}'


class AudioChatFixture(ChatFixture):
    def setUp(self):
        super().setUp()
        self.app.state.photo_storage = FakeStorage()

    def make_audio(self, verified=True, kind='audio', pet_id=None, content_type='audio/wav'):
        media_id = uuid4().hex
        with Session(self.engine) as db, db.begin():
            db.add(
                MediaUpload(
                    id=media_id,
                    pet_id=pet_id or self.pet_id,
                    kind=kind,
                    content_type=content_type,
                    size_bytes=16044,
                    expires_at=utcnow() + timedelta(minutes=10),
                    version_id='version-1' if verified else None,
                )
            )
        return media_id

    def send_audio(self, media_id, **extra):
        return self.client.post(
            f'/api/v1/chat/sessions/{self.session_id}/messages',
            headers=self.headers,
            json={'kind': 'audio', 'media_id': media_id, **extra},
        )


class AudioAPITests(AudioChatFixture, unittest.TestCase):
    def test_presign_audio_accepts_wav(self):
        response = self.client.post(
            '/api/v1/media/presign',
            headers=self.headers,
            json={'pet_id': self.pet_id, 'kind': 'audio', 'content_type': 'audio/wav', 'size_bytes': 16044},
        )
        self.assertEqual(response.status_code, 201)
        media_id = response.json()['media_id']
        with Session(self.engine) as db:
            media = db.get(MediaUpload, media_id)
            self.assertEqual(media.kind, 'audio')
            self.assertTrue(media.object_key.startswith(f'audio/{self.pet_id}/'))

    def test_presign_audio_rejects_bad_type_and_size(self):
        for payload in (
            {'content_type': 'audio/ogg', 'size_bytes': 100},
            {'content_type': 'audio/wav', 'size_bytes': 11 * 1024 * 1024},
            {'content_type': 'audio/wav', 'size_bytes': 0},
        ):
            response = self.client.post(
                '/api/v1/media/presign', headers=self.headers, json={'pet_id': self.pet_id, 'kind': 'audio', **payload}
            )
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()['code'], 'MEDIA_INVALID')

    def test_audio_message_enqueues_task(self):
        media_id = self.make_audio()
        response = self.send_audio(media_id)
        self.assertEqual(response.status_code, 202)
        body = response.json()
        self.assertRegex(body['task_id'], r'^[0-9a-f]{32}$')
        self.assertEqual(body['user_message']['kind'], 'audio')
        self.assertEqual(
            body['user_message']['audio_url'], f'https://fake.local/audio/{self.pet_id}/{media_id}?v=version-1'
        )
        self.assertIsNone(body['pet_message'])
        self.assertIsNone(body['guidance'])
        with Session(self.engine) as db:
            task = db.get(Task, body['task_id'])
            self.assertEqual((task.type, task.status), ('audio_interpret', 'pending'))
            self.assertEqual(task.payload['media_id'], media_id)
            self.assertEqual(task.payload['session_id'], self.session_id)
            message = db.get(ChatMessage, body['user_message']['id'])
            self.assertEqual(message.task_id, task.id)
            self.assertEqual(message.audio_url, f'audio/{self.pet_id}/{media_id}')
            self.assertEqual(task.payload['message_id'], message.id)

    def test_audio_message_merges_inflight_retry(self):
        media_id = self.make_audio()
        first = self.send_audio(media_id)
        second = self.send_audio(media_id)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()['task_id'], first.json()['task_id'])
        self.assertEqual(second.json()['user_message']['id'], first.json()['user_message']['id'])
        with Session(self.engine) as db:
            tasks = db.scalars(select(Task).where(Task.type == 'audio_interpret')).all()
            self.assertEqual(len(tasks), 1)
            messages = db.scalars(select(ChatMessage).where(ChatMessage.kind == 'audio')).all()
            self.assertEqual(len(messages), 1)

    def test_audio_message_new_task_after_previous_finished(self):
        media_id = self.make_audio()
        first = self.send_audio(media_id)
        with Session(self.engine) as db, db.begin():
            task = db.get(Task, first.json()['task_id'])
            task.status = 'succeeded'
        second = self.send_audio(media_id)
        self.assertEqual(second.status_code, 202)
        self.assertNotEqual(second.json()['task_id'], first.json()['task_id'])

    def test_audio_media_validation(self):
        unverified = self.make_audio(verified=False)
        self.assertEqual(self.send_audio(unverified).status_code, 409)
        photo = self.make_audio(kind='photo', content_type='image/png')
        wrong_kind = self.send_audio(photo)
        self.assertEqual(wrong_kind.status_code, 422)
        self.assertEqual(wrong_kind.json()['code'], 'MEDIA_INVALID')
        other_pet = self.client.post('/api/v1/pets', headers=self.headers, json={'name': '另一个'}).json()['id']
        foreign = self.make_audio(pet_id=other_pet)
        self.assertEqual(self.send_audio(foreign).status_code, 404)
        missing = self.client.post(
            f'/api/v1/chat/sessions/{self.session_id}/messages', headers=self.headers, json={'kind': 'audio'}
        )
        self.assertEqual(missing.status_code, 400)
        with_content = self.send_audio(self.make_audio(), content='多余')
        self.assertEqual(with_content.status_code, 400)

    def test_text_without_content_rejected(self):
        response = self.client.post(
            f'/api/v1/chat/sessions/{self.session_id}/messages', headers=self.headers, json={'kind': 'text'}
        )
        self.assertEqual(response.status_code, 400)

    def test_audio_session_isolation(self):
        other = self.verified_account('other@example.com')
        media_id = self.make_audio()
        response = self.client.post(
            f'/api/v1/chat/sessions/{self.session_id}/messages',
            headers=other,
            json={'kind': 'audio', 'media_id': media_id},
        )
        self.assertEqual(response.status_code, 404)

    def test_get_messages_signs_audio_url(self):
        media_id = self.make_audio()
        self.send_audio(media_id)
        listing = self.client.get(f'/api/v1/chat/sessions/{self.session_id}/messages', headers=self.headers)
        listing.raise_for_status()
        item = listing.json()['items'][0]
        self.assertEqual(item['kind'], 'audio')
        self.assertEqual(item['audio_url'], f'https://fake.local/audio/{self.pet_id}/{media_id}?v=version-1')
        self.app.state.photo_storage = None
        again = self.client.get(f'/api/v1/chat/sessions/{self.session_id}/messages', headers=self.headers)
        again.raise_for_status()
        self.assertIsNone(again.json()['items'][0]['audio_url'])

    def test_text_chat_still_works_after_audio(self):
        self.send_audio(self.make_audio())
        response = self.send('你好呀')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['pet_message']['content'], '喵～我在呢')


if __name__ == '__main__':
    unittest.main()
