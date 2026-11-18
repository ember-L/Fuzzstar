"""Opt-in end-to-end check against a disposable, versioned S3 bucket."""
import io
import os
import unittest
from uuid import uuid4

import httpx
from PIL import Image

from app.media import PhotoStorage
from app.models import MediaUpload


@unittest.skipUnless(os.environ.get('MEDIA_S3_SMOKE') == '1', 'requires a disposable versioned S3 bucket')
class PhotoStorageSmokeTest(unittest.TestCase):
    def test_post_policy_and_download_remain_bound_to_verified_version(self):
        storage = PhotoStorage.from_env()
        self.assertIsNotNone(storage)
        self.assertEqual(storage.client.get_bucket_versioning(Bucket=storage.bucket).get('Status'), 'Enabled')
        encoded = io.BytesIO()
        Image.new('RGB', (2, 2)).save(encoded, 'PNG')
        data = encoded.getvalue()
        photo = MediaUpload(id=uuid4().hex, pet_id=1, content_type='image/png', size_bytes=len(data))
        upload = storage.presign(photo)

        def submit(payload):
            return httpx.post(upload['url'], data=upload['fields'],
                              files={'file': ('fixture.png', payload, 'image/png')}, timeout=10)

        self.assertIn(submit(data + b'x' * 1024).status_code, (400, 403))
        submit(data).raise_for_status()
        photo.version_id = storage.verify(photo)
        submit(b'x' * len(data)).raise_for_status()
        downloaded = httpx.get(storage.download_url(photo), timeout=10).raise_for_status()
        self.assertEqual(downloaded.content, data)
