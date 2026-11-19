"""Opt-in end-to-end smoke: HTTP API -> MinIO -> Redis/arq worker -> task result.

Run with a disposable versioned MinIO bucket and Redis:
  E2E_SMOKE=1 REDIS_TEST_URL=redis://127.0.0.1:6390
  MEDIA_S3_ENDPOINT=http://127.0.0.1:9000 MEDIA_S3_BUCKET=rongxing-smoke
  MEDIA_S3_ACCESS_KEY=... MEDIA_S3_SECRET_KEY=...
  .venv311/bin/python -m unittest discover -s tests -p 'test_e2e_smoke.py' -v
Uses fake generation providers; real DashScope acceptance needs DASHSCOPE_API_KEY.
"""
import asyncio
import io
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx
from arq import Worker, cron
from arq.connections import RedisSettings, create_pool
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import main, worker
from app.auth import utcnow
from app.avatars import ACTIONS, S3Assets
from app.identity import create_email_account, verify_email
from app.models import Base
from app.providers.fake import FakeImageProvider, FakeVideoProvider


@unittest.skipUnless(os.environ.get('E2E_SMOKE') == '1', 'requires MinIO + Redis smoke environment')
class E2ESmokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_photo_upload_to_avatar_result(self):
        redis_url = os.environ.get('REDIS_TEST_URL')
        if not redis_url:
            self.skipTest('requires REDIS_TEST_URL')
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        url = 'sqlite:///' + str(Path(directory.name) / 'e2e.db')
        engine = create_engine(url)
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        with Session(engine) as db, db.begin():
            token = create_email_account(db, 'e2e@example.com', 'Strong123', utcnow())
            verify_email(db, token, utcnow())
        with patch.dict(os.environ, {
            'DATABASE_URL': url, 'JWT_SECRET': 'test-signing-key-32-bytes-or-more',
            'PRIVACY_VERSION': 'p1', 'TERMS_VERSION': 't1',
            'PRIVACY_URL': 'https://example.com/privacy', 'TERMS_URL': 'https://example.com/terms',
        }):
            app = main.create_dev_app()
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                         base_url='http://testserver', timeout=15) as client:
                login = await client.post('/api/v1/auth/login', json={'email': 'e2e@example.com', 'password': 'Strong123'})
                login.raise_for_status()
                headers = {'Authorization': f"Bearer {login.json()['access_token']}"}
                (await client.post('/api/v1/consents', headers=headers, json={'privacy': 'p1', 'terms': 't1'})).raise_for_status()
                pet = await client.post('/api/v1/pets', headers=headers, json={'name': '团团'})
                pet.raise_for_status()
                pet_id = pet.json()['id']

                buffer = io.BytesIO()
                Image.new('RGB', (8, 8), (200, 150, 100)).save(buffer, format='PNG')
                payload = buffer.getvalue()
                ticket = await client.post('/api/v1/media/presign', headers=headers, json={
                    'pet_id': pet_id, 'content_type': 'image/png', 'size_bytes': len(payload)})
                ticket.raise_for_status()
                media_id, upload = ticket.json()['media_id'], ticket.json()['upload']
                posted = await asyncio.to_thread(
                    httpx.post, upload['url'], data=upload['fields'],
                    files={'file': ('photo.png', payload, 'image/png')}, timeout=15)
                self.assertIn(posted.status_code, (200, 204))
                complete = await client.post(f'/api/v1/media/{media_id}/complete', headers=headers)
                complete.raise_for_status()
                self.assertEqual(complete.json()['status'], 'verified')

                submitted = await client.post(f'/api/v1/pets/{pet_id}/avatar', headers=headers,
                                              json={'media_id': media_id})
                self.assertEqual(submitted.status_code, 202)
                task_id = submitted.json()['task_id']
                merged = await client.post(f'/api/v1/pets/{pet_id}/avatar', headers=headers,
                                           json={'media_id': media_id})
                self.assertEqual(merged.json()['task_id'], task_id)
                manifest = submitted.json()['placeholder_manifest']
                self.assertEqual(manifest['body_type'], 'standard')
                self.assertEqual(manifest['version'], 'v1')
                self.assertEqual(set(manifest['clips']), set(ACTIONS))
                clip = await client.get(manifest['clips']['idle'])
                self.assertEqual(clip.status_code, 200)
                self.assertEqual(clip.headers['content-type'], 'video/mp4')
                self.assertIn('immutable', clip.headers['cache-control'])
                self.assertGreater(len(clip.content), 0)
                action_map = await client.get('/api/v1/config/action-map', headers=headers)
                action_map.raise_for_status()
                self.assertEqual(action_map.json()['version'], 'am-2026-11-18')
                pending_view = await client.get(f'/api/v1/pets/{pet_id}/avatar', headers=headers)
                pending_view.raise_for_status()
                self.assertEqual(pending_view.json()['task_id'], task_id)
                self.assertIsNone(pending_view.json()['base_image'])
                self.assertEqual(pending_view.json()['placeholder_manifest'], manifest)

                worker_engine = create_engine(url)
                self.addCleanup(worker_engine.dispose)

                async def on_startup(ctx):
                    ctx['engine'] = worker_engine
                    ctx['assets'] = S3Assets.from_env()
                    ctx['image_provider'] = FakeImageProvider()
                    ctx['video_provider'] = FakeVideoProvider()

                settings = RedisSettings.from_dsn(redis_url)
                pool = await create_pool(settings)
                runner = Worker([worker.run_task], redis_settings=settings, redis_pool=pool,
                                max_tries=1, burst=False, poll_delay=0.1, on_startup=on_startup,
                                cron_jobs=[cron(worker.sweep, second=set(range(0, 60, 2)))])
                running = asyncio.create_task(runner.async_run())
                try:
                    body = None
                    deadline = asyncio.get_event_loop().time() + 60
                    while asyncio.get_event_loop().time() < deadline:
                        response = await client.get(f'/api/v1/tasks/{task_id}', headers=headers)
                        response.raise_for_status()
                        body = response.json()
                        if body['status'] in ('succeeded', 'failed'):
                            break
                        await asyncio.sleep(0.3)
                    self.assertIsNotNone(body)
                    self.assertEqual(body['status'], 'succeeded', body)
                    result = body['result']
                    self.assertTrue(result['usable'])
                    self.assertEqual(result['ready_count'], 7)
                    self.assertEqual(set(result['clips']), set(ACTIONS))
                    assets = S3Assets.from_env()
                    head = await asyncio.to_thread(
                        assets.client.head_object, Bucket=assets.bucket,
                        Key=result['base_image']['key'], VersionId=result['base_image']['version_id'])
                    self.assertGreater(head['ContentLength'], 0)
                    view = await client.get(f'/api/v1/pets/{pet_id}/avatar', headers=headers)
                    view.raise_for_status()
                    avatar = view.json()
                    self.assertTrue(avatar['usable'])
                    self.assertEqual(avatar['ready_count'], 7)
                    self.assertEqual(avatar['task_id'], task_id)
                    for asset_url in [avatar['base_image']['url'], avatar['clips']['idle']['url']]:
                        fetched = await asyncio.to_thread(httpx.get, asset_url, timeout=15)
                        self.assertEqual(fetched.status_code, 200)
                        self.assertGreater(len(fetched.content), 0)
                finally:
                    running.cancel()
                    try:
                        await running
                    except asyncio.CancelledError:
                        pass
                    await pool.aclose()

                # T09 初筛：规则硬判定、红线卡、存档回看与存证删除（引用保护）。
                config = await client.get('/api/v1/config/symptoms', headers=headers)
                config.raise_for_status()
                self.assertEqual(config.json()['version'], 'sx-2026-11-19')
                invalid = await client.post(f'/api/v1/pets/{pet_id}/screenings', headers=headers,
                                            json={'appetite': 'normal', 'symptoms': []})
                self.assertEqual(invalid.status_code, 400)
                self.assertEqual(invalid.json()['code'], 'VALIDATION_ERROR')
                self.assertIn('spirit', [f['field'] for f in invalid.json()['detail']['fields']])
                screening = await client.post(f'/api/v1/pets/{pet_id}/screenings', headers=headers, json={
                    'spirit': 'normal', 'appetite': 'normal',
                    'symptoms': [{'code': 'vomiting', 'duration': '>24h', 'frequency': '2-3'}],
                    'redline_options': [], 'media_ids': [media_id]})
                self.assertEqual(screening.status_code, 201)
                record = screening.json()
                self.assertEqual(record['state'], 'urgent')
                self.assertTrue(record['redline_hit'])
                self.assertIn('vomiting_persistent', record['redlines'])
                self.assertEqual(record['redline_card']['title'], '建议立即就医')
                self.assertEqual(record['disclaimer'], 'AI 结果仅供日常健康管理参考,不替代专业兽医诊断')
                detail = await client.get(f"/api/v1/screenings/{record['screening_id']}", headers=headers)
                detail.raise_for_status()
                self.assertEqual(detail.json()['state'], 'urgent')
                self.assertEqual(detail.json()['media'][0]['media_id'], media_id)
                history = await client.get(f'/api/v1/pets/{pet_id}/screenings', headers=headers)
                history.raise_for_status()
                self.assertEqual(history.json()['items'][0]['screening_id'], record['screening_id'])
                normal = await client.post(f'/api/v1/pets/{pet_id}/screenings', headers=headers, json={
                    'spirit': 'normal', 'appetite': 'normal', 'symptoms': [], 'redline_options': [], 'media_ids': []})
                self.assertEqual(normal.status_code, 201)
                self.assertEqual(normal.json()['state'], 'normal')
                self.assertIsNone(normal.json()['redline_card'])
                removed = await client.delete(
                    f"/api/v1/screenings/{record['screening_id']}/media/{media_id}", headers=headers)
                self.assertEqual(removed.status_code, 204)
                # 照片仍被分身任务引用：只删关联，对象版本保留。
                still = await client.get(f'/api/v1/media/{media_id}', headers=headers)
                self.assertEqual(still.status_code, 200)


if __name__ == '__main__':
    unittest.main()
