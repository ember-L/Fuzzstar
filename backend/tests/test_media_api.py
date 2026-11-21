import base64
import io
import json
from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from test_auth_api import AuthAPIFixture
from app import main
from app.services.identity import create_email_account, verify_email
from app.services.media import PhotoStorage, valid_photo
from app.models import MediaUpload

# 1×1 PNG; no user media in the test suite.
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgYGAAAAAEAAH2FzhVAAAAAElFTkSuQmCC')


class MediaAPITests(AuthAPIFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.headers = {'Authorization': 'Bearer ' + self.login().json()['access_token']}
        self.client.app.state.photo_storage = None
        self.versions = {'privacy': 'p1', 'terms': 't1'}
        self.client.post('/api/v1/consents', headers=self.headers, json=self.versions).raise_for_status()
        self.pet = self.client.post('/api/v1/pets', headers=self.headers, json={'name': '团团'}).raise_for_status().json()['id']
        self.body = {'pet_id': self.pet, 'content_type': 'image/png', 'size_bytes': len(PNG)}
        self.path = '/api/v1/media/presign'

    def presign(self, **changes):
        return self.client.post(self.path, headers=self.headers, json={**self.body, **changes})

    def configure_storage(self):
        env = {
            'MEDIA_S3_ENDPOINT': 'http://127.0.0.1:9000', 'MEDIA_S3_BUCKET': 'private-photos',
            'MEDIA_S3_ACCESS_KEY': 'test-only', 'MEDIA_S3_SECRET_KEY': 'test-only-secret',
        }
        with patch.dict('os.environ', env):
            storage = PhotoStorage.from_env()
        self.client.app.state.photo_storage = storage
        return storage

    def test_partial_or_insecure_storage_configuration_is_rejected(self):
        env = {'MEDIA_S3_ENDPOINT': 'http://storage.example', 'MEDIA_S3_BUCKET': 'private-photos',
               'MEDIA_S3_ACCESS_KEY': 'test-only', 'MEDIA_S3_SECRET_KEY': 'test-only-secret'}
        with patch.dict('os.environ', env, clear=True), self.assertRaisesRegex(RuntimeError, 'HTTPS'):
            PhotoStorage.from_env()
        with patch.dict('os.environ', {'MEDIA_S3_BUCKET': 'private-photos'}, clear=True), self.assertRaises(RuntimeError):
            PhotoStorage.from_env()

    def test_presign_enforces_login_consent_pet_owner_and_input(self):
        self.assertEqual(self.client.post(self.path, json=self.body).status_code, 401)
        self.assertEqual(self.presign().status_code, 503)
        self.assertEqual(self.presign(pet_id=self.pet + 1).status_code, 404)
        for bad in ({'content_type': 'text/html'}, {'size_bytes': 0}, {'size_bytes': 10485761}):
            invalid = self.presign(**bad)
            self.assertEqual((invalid.status_code, invalid.json()['code']), (422, 'MEDIA_INVALID'))
        for bad in ({'size_bytes': True}, {'object_key': 'custom'}):
            self.assertEqual(self.presign(**bad).status_code, 400)
        self.client.app.state.policy_versions = {**self.versions, 'privacy': 'p2'}
        self.assertEqual(self.presign().status_code, 403)
        self.assertEqual(TestClient(main.app).post(self.path, json=self.body).status_code, 404)

    def test_signed_post_is_specific_and_completion_pins_verified_version(self):
        storage = self.configure_storage()
        response = self.presign()
        self.assertEqual(response.status_code, 201)
        signed = response.json()
        self.assertEqual(response.headers['cache-control'], 'no-store')
        policy = json.loads(base64.b64decode(signed['upload']['fields']['policy']))
        self.assertIn({'key': f'photos/{self.pet}/{signed["media_id"]}'}, policy['conditions'])
        self.assertIn({'Content-Type': 'image/png'}, policy['conditions'])
        self.assertIn(['content-length-range', len(PNG), len(PNG)], policy['conditions'])
        self.assertLessEqual((datetime.fromisoformat(policy['expiration'].rstrip('Z')).replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).total_seconds(), 600)
        path = f'/api/v1/media/{signed["media_id"]}/complete'
        with patch.object(storage.client, 'head_object', return_value={
            'ContentLength': len(PNG), 'ContentType': 'image/png', 'VersionId': 'verified-v1',
        }) as head, patch.object(storage.client, 'get_object', return_value={'Body': io.BytesIO(PNG)}) as read:
            done = self.client.post(path, headers=self.headers).raise_for_status()
            self.assertEqual(done.json(), {'media_id': signed['media_id'], 'status': 'verified'})
            self.assertEqual(read.call_args.kwargs['VersionId'], 'verified-v1')
            head.reset_mock()
            head.side_effect = AssertionError('Completed upload must not inspect a newer version')
            self.assertEqual(self.client.post(path, headers=self.headers).json(), done.json())
        with Session(self.engine) as db:
            self.assertEqual(db.get(MediaUpload, signed['media_id']).version_id, 'verified-v1')

    def test_download_is_signed_only_for_the_verified_version(self):
        storage = self.configure_storage()
        upload_id = self.presign().raise_for_status().json()['media_id']
        path = f'/api/v1/media/{upload_id}'
        self.assertEqual(self.client.get(path, headers=self.headers).status_code, 409)
        with Session(self.engine) as db, db.begin():
            db.get(MediaUpload, upload_id).version_id = 'pinned-version'
        with patch.object(storage.client, 'generate_presigned_url', return_value='https://storage.example/download') as sign:
            response = self.client.get(path, headers=self.headers).raise_for_status()
        self.assertEqual(response.json(), {'download_url': 'https://storage.example/download', 'expires_in': 3600})
        self.assertEqual(sign.call_args.args, ('get_object',))
        self.assertEqual(sign.call_args.kwargs['Params']['VersionId'], 'pinned-version')
        self.assertEqual(response.headers['cache-control'], 'no-store')

    def test_photo_decoder_supports_three_formats_and_limits_pixels(self):
        for content_type, format_name in [('image/jpeg', 'JPEG'), ('image/png', 'PNG'), ('image/heic', 'HEIF')]:
            with self.subTest(content_type=content_type):
                image = io.BytesIO()
                Image.new('RGB', (16, 16)).save(image, format_name)
                self.assertTrue(valid_photo(image.getvalue(), content_type))
                self.assertFalse(valid_photo(image.getvalue()[:20], content_type))
                with patch('app.services.media.MAX_PHOTO_PIXELS', 255):
                    self.assertFalse(valid_photo(image.getvalue(), content_type))

    def test_another_account_cannot_complete_even_with_the_id(self):
        storage = self.configure_storage()
        signed = self.presign().raise_for_status().json()
        with Session(self.engine) as db, db.begin():
            token = create_email_account(db, 'other@example.com', self.password, self.now)
            verify_email(db, token, self.now)
        headers = {'Authorization': 'Bearer ' + self.login('other@example.com').json()['access_token']}
        self.client.post('/api/v1/consents', headers=headers, json=self.versions).raise_for_status()
        with patch.object(storage.client, 'head_object', side_effect=AssertionError('unauthorized storage access')):
            path = f'/api/v1/media/{signed["media_id"]}/complete'
            self.assertEqual(self.client.post(path, headers=headers).status_code, 404)
            self.assertEqual(self.client.get(path.removesuffix('/complete'), headers=headers).status_code, 404)
            self.client.delete(f'/api/v1/pets/{self.pet}', headers=self.headers).raise_for_status()
            self.assertEqual(self.client.post(path, headers=self.headers).status_code, 404)

    def test_rejects_expired_unversioned_and_mismatched_objects(self):
        storage = self.configure_storage()
        upload_id = self.presign().raise_for_status().json()['media_id']
        path = f'/api/v1/media/{upload_id}/complete'
        metadata = {'ContentLength': len(PNG), 'ContentType': 'image/png', 'VersionId': 'v1'}
        from botocore.exceptions import ClientError
        missing = ClientError({'Error': {'Code': 'NoSuchKey'}, 'ResponseMetadata': {'HTTPStatusCode': 404}}, 'HeadObject')
        with patch.object(storage.client, 'head_object', side_effect=missing):
            self.assertEqual(self.client.post(path, headers=self.headers).status_code, 409)
        for wrong, expected in [({'VersionId': 'null'}, 503), ({'ContentLength': len(PNG) + 1}, 422), ({'ContentType': 'image/jpeg'}, 422)]:
            with patch.object(storage.client, 'head_object', return_value={**metadata, **wrong}), patch.object(
                storage.client, 'get_object', side_effect=AssertionError('must reject before download'),
            ):
                self.assertEqual(self.client.post(path, headers=self.headers).status_code, expected)
        with patch.object(storage.client, 'head_object', return_value=metadata), patch.object(
            storage.client, 'get_object', return_value={'Body': io.BytesIO(b'X' * len(PNG))},
        ):
            self.assertEqual(self.client.post(path, headers=self.headers).status_code, 422)
        with Session(self.engine) as db, db.begin():
            db.get(MediaUpload, upload_id).expires_at = datetime(2020, 1, 1)
        with patch.object(storage.client, 'head_object', side_effect=AssertionError('expired upload must not touch storage')):
            self.assertEqual(self.client.post(path, headers=self.headers).status_code, 410)
