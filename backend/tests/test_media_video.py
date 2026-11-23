import io
import json
import subprocess
import tempfile
import base64
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from sqlalchemy.orm import Session

from test_auth_api import AuthAPIFixture
from app.services.media import MAX_VIDEO_BYTES, PhotoStorage, valid_video
from app.models import MediaUpload


def make_clip(seconds: float) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / 'clip.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', f'testsrc=duration={seconds}:size=160x120:rate=12',
                        '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-y', str(target)],
                       check=True, capture_output=True, timeout=120)
        return target.read_bytes()


class VideoValidationTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.short = make_clip(1)
        cls.long = make_clip(31)

    def test_accepts_short_mp4_and_quicktime_declared_mp4(self):
        self.assertTrue(valid_video(self.short, 'video/mp4'))
        self.assertTrue(valid_video(self.short, 'video/quicktime'))

    def test_rejects_over_30_seconds_garbage_and_wrong_type(self):
        self.assertFalse(valid_video(self.long, 'video/mp4'))
        self.assertFalse(valid_video(b'not a video', 'video/mp4'))
        self.assertFalse(valid_video(self.short, 'image/png'))


class VideoMediaAPITests(AuthAPIFixture, TestCase):
    @classmethod
    def setUpClass(cls):
        cls.clip = make_clip(1)

    def setUp(self):
        super().setUp()
        self.headers = {'Authorization': 'Bearer ' + self.login().json()['access_token']}
        self.client.post('/api/v1/consents', headers=self.headers, json={'privacy': 'p1', 'terms': 't1'}).raise_for_status()
        self.pet = self.client.post('/api/v1/pets', headers=self.headers, json={'name': '团团'}).raise_for_status().json()['id']
        env = {'MEDIA_S3_ENDPOINT': 'http://127.0.0.1:9000', 'MEDIA_S3_BUCKET': 'private-photos',
               'MEDIA_S3_ACCESS_KEY': 'test-only', 'MEDIA_S3_SECRET_KEY': 'test-only-secret'}
        with patch.dict('os.environ', env):
            self.storage = PhotoStorage.from_env()
        self.client.app.state.photo_storage = self.storage

    def presign(self, **changes):
        body = {'pet_id': self.pet, 'kind': 'video', 'content_type': 'video/mp4', 'size_bytes': len(self.clip)}
        return self.client.post('/api/v1/media/presign', headers=self.headers, json={**body, **changes})

    def test_video_presign_uses_video_key_and_limits(self):
        response = self.presign().raise_for_status()
        signed = response.json()
        policy = json.loads(base64.b64decode(signed['upload']['fields']['policy']))
        self.assertIn({'key': f'videos/{self.pet}/{signed["media_id"]}'}, policy['conditions'])
        self.assertIn({'Content-Type': 'video/mp4'}, policy['conditions'])
        self.assertIn(['content-length-range', len(self.clip), len(self.clip)], policy['conditions'])
        with Session(self.engine) as db:
            self.assertEqual(db.get(MediaUpload, signed['media_id']).kind, 'video')
        for bad in ({'size_bytes': MAX_VIDEO_BYTES + 1}, {'content_type': 'image/png'}, {'content_type': 'video/webm'}):
            invalid = self.presign(**bad)
            self.assertEqual((invalid.status_code, invalid.json()['code']), (422, 'MEDIA_INVALID'))
        # T16 起 audio 为合法 kind；此处 content_type 仍是 video/mp4，应被音频类型校验拦截。
        self.assertEqual(self.presign(kind='audio').status_code, 422)
        photo = self.presign(kind='photo', content_type='video/mp4', size_bytes=100)
        self.assertEqual(photo.status_code, 422)

    def test_video_complete_verifies_bytes_and_pins_version(self):
        signed = self.presign().raise_for_status().json()
        path = f"/api/v1/media/{signed['media_id']}/complete"
        with patch.object(self.storage.client, 'head_object', return_value={
            'ContentLength': len(self.clip), 'ContentType': 'video/mp4', 'VersionId': 'video-v1',
        }), patch.object(self.storage.client, 'get_object', return_value={'Body': io.BytesIO(self.clip)}):
            done = self.client.post(path, headers=self.headers).raise_for_status()
            self.assertEqual(done.json(), {'media_id': signed['media_id'], 'status': 'verified'})
        with Session(self.engine) as db:
            media = db.get(MediaUpload, signed['media_id'])
            self.assertEqual((media.version_id, media.kind), ('video-v1', 'video'))
        download = self.client.get(f"/api/v1/media/{signed['media_id']}", headers=self.headers).raise_for_status()
        self.assertIn('download_url', download.json())

    def test_video_complete_rejects_overlong_content(self):
        long_clip = make_clip(31)
        signed = self.presign(size_bytes=len(long_clip)).raise_for_status().json()
        with patch.object(self.storage.client, 'head_object', return_value={
            'ContentLength': len(long_clip), 'ContentType': 'video/mp4', 'VersionId': 'video-v1',
        }), patch.object(self.storage.client, 'get_object', return_value={'Body': io.BytesIO(long_clip)}):
            rejected = self.client.post(f"/api/v1/media/{signed['media_id']}/complete", headers=self.headers)
        self.assertEqual((rejected.status_code, rejected.json()['code']), (422, 'MEDIA_INVALID'))
