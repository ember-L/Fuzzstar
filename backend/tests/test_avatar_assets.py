"""占位资产下发与体型档案（FRD F03-4 / F02-1 体型扩展，AC-03-1）。"""
import hashlib
import unittest
from datetime import timedelta
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.security import utcnow
from app.services.identity import create_email_account, verify_email
from app.models import MediaUpload
from test_auth_api import AuthAPIFixture

ACTIONS = ('idle', 'happy', 'sad', 'sick', 'crouch', 'look_left', 'look_right')


class AvatarAssetsTests(AuthAPIFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.headers = {'Authorization': f"Bearer {self.login().json()['access_token']}"}
        self.client.post('/api/v1/consents', headers=self.headers, json={'privacy': 'p1', 'terms': 't1'}).raise_for_status()
        self.pet_id = self.client.post('/api/v1/pets', headers=self.headers, json={'name': '团团'}).json()['id']

    def make_media(self, pet_id):
        media_id = uuid4().hex
        with Session(self.engine) as db, db.begin():
            db.add(MediaUpload(id=media_id, pet_id=pet_id, content_type='image/png', size_bytes=1024,
                               expires_at=utcnow() + timedelta(minutes=10), version_id='version-1'))
        return media_id

    def submit(self, pet_id, media_id):
        return self.client.post(f'/api/v1/pets/{pet_id}/avatar', json={'media_id': media_id}, headers=self.headers)

    def test_pet_profile_defaults_body_type_standard(self):
        response = self.client.get(f'/api/v1/pets/{self.pet_id}', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['body_type'], 'standard')

    def test_create_pet_with_body_type(self):
        response = self.client.post('/api/v1/pets', headers=self.headers, json={'name': '胖胖', 'body_type': 'chubby'})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['body_type'], 'chubby')

    def test_invalid_body_type_rejected(self):
        response = self.client.post('/api/v1/pets', headers=self.headers, json={'name': '胖胖', 'body_type': 'fat'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'VALIDATION_ERROR')

    def test_patch_body_type(self):
        response = self.client.patch(f'/api/v1/pets/{self.pet_id}', headers=self.headers, json={'body_type': 'slim'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['body_type'], 'slim')

    def test_placeholder_manifest_requires_login(self):
        response = self.client.get('/api/v1/avatar/placeholder-manifest')
        self.assertEqual(response.status_code, 401)

    def test_placeholder_manifest_requires_consent(self):
        with Session(self.engine) as db, db.begin():
            token = create_email_account(db, 'noconsent2@example.com', self.password, self.now)
            verify_email(db, token, self.now)
        headers = {'Authorization': f"Bearer {self.login('noconsent2@example.com').json()['access_token']}"}
        response = self.client.get('/api/v1/avatar/placeholder-manifest', headers=headers)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['code'], 'CONSENT_REQUIRED')

    def test_placeholder_manifest_shape(self):
        response = self.client.get('/api/v1/avatar/placeholder-manifest', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        body = response.json()
        self.assertEqual(body['version'], 'v1')
        self.assertEqual(set(body['groups']), {'slim', 'standard', 'chubby'})
        for group in body['groups'].values():
            self.assertEqual(set(group), set(ACTIONS))
            for url in group.values():
                self.assertTrue(url.startswith('http://testserver/api/v1/avatar/placeholders/v1/'))

    def test_placeholder_manifest_unavailable(self):
        self.client.app.state.placeholder_library = None
        response = self.client.get('/api/v1/avatar/placeholder-manifest', headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['code'], 'PLACEHOLDER_UNAVAILABLE')

    def test_clip_download_is_public_and_version_pinned(self):
        manifest = self.client.get('/api/v1/avatar/placeholder-manifest', headers=self.headers).json()
        url = manifest['groups']['standard']['idle']
        path = url.split('testserver')[1]
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['content-type'], 'video/mp4')
        self.assertIn('immutable', response.headers['cache-control'])
        expected = self.client.app.state.placeholder_library.manifest['clips']['standard']['idle']['sha256']
        self.assertEqual(hashlib.sha256(response.content).hexdigest(), expected)

    def test_clip_whitelist_404(self):
        for path in ('/api/v1/avatar/placeholders/v1/standard/jump.mp4',
                     '/api/v1/avatar/placeholders/v9/standard/idle.mp4',
                     '/api/v1/avatar/placeholders/v1/fat/idle.mp4',
                     '/api/v1/avatar/placeholders/v1/standard/idle.txt'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 404, path)

    def test_submit_includes_placeholder_manifest(self):
        response = self.submit(self.pet_id, self.make_media(self.pet_id))
        self.assertEqual(response.status_code, 202)
        placeholder = response.json()['placeholder_manifest']
        self.assertEqual(placeholder['version'], 'v1')
        self.assertEqual(placeholder['body_type'], 'standard')
        self.assertEqual(set(placeholder['clips']), set(ACTIONS))
        self.assertIn('/v1/standard/idle.mp4', placeholder['clips']['idle'])

    def test_submit_uses_pet_body_type(self):
        pet_id = self.client.post('/api/v1/pets', headers=self.headers, json={'name': '胖胖', 'body_type': 'chubby'}).json()['id']
        response = self.submit(pet_id, self.make_media(pet_id))
        self.assertEqual(response.status_code, 202)
        placeholder = response.json()['placeholder_manifest']
        self.assertEqual(placeholder['body_type'], 'chubby')
        self.assertIn('/v1/chubby/happy.mp4', placeholder['clips']['happy'])

    def test_submit_without_library_503(self):
        self.client.app.state.placeholder_library = None
        response = self.submit(self.pet_id, self.make_media(self.pet_id))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['code'], 'PLACEHOLDER_UNAVAILABLE')


if __name__ == '__main__':
    unittest.main()
