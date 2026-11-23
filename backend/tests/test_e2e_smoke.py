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
import wave
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx
from arq import Worker, cron
from arq.connections import RedisSettings, create_pool
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import main, worker
from app.services.advice import load_advice_templates
from app.core.security import utcnow
from app.services.avatars import ACTIONS, S3Assets
from app.services.chat import load_chat_config
from app.services.identity import create_email_account, verify_email
from app.services.media import PhotoStorage
from app.models import AiUsageLog, Base, DeletionJob, MediaUpload, Pet, Task, User
from app.services.privacy import purge_due
from app.providers.fake import FakeAudioProvider, FakeImageProvider, FakeLLMProvider, FakeVideoProvider
from app.services.triage import load_rules

RULES_DIR = Path(__file__).resolve().parents[1] / 'rules'


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
                    ctx['llm_provider'] = FakeLLMProvider()
                    ctx['advice_templates'] = load_advice_templates(RULES_DIR)
                    ctx['triage_rules'] = load_rules(RULES_DIR)

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
                # T10：红线零 LLM——不建任务、模板即存、无用量记录。
                self.assertIsNone(record['task_id'])
                templates = load_advice_templates(RULES_DIR)
                detail = await client.get(f"/api/v1/screenings/{record['screening_id']}", headers=headers)
                detail.raise_for_status()
                self.assertEqual(detail.json()['state'], 'urgent')
                self.assertEqual(detail.json()['media'][0]['media_id'], media_id)
                urgent_advice = detail.json()['advice']
                self.assertEqual((urgent_advice['status'], urgent_advice['source']), ('ready', 'template'))
                self.assertEqual(urgent_advice['text'], templates['states']['urgent']['text'])
                with Session(worker_engine) as db:
                    self.assertEqual(db.scalars(select(AiUsageLog)).all(), [])
                # T08：urgent 首页健康聚合——红色状态卡+常驻就医入口。
                urgent_health = await client.get(f'/api/v1/pets/{pet_id}/health', headers=headers)
                urgent_health.raise_for_status()
                self.assertEqual((urgent_health.json()['state'], urgent_health.json()['score']), ('urgent', 40))
                self.assertEqual(urgent_health.json()['urgent_card']['title'], '建议立即就医')
                history = await client.get(f'/api/v1/pets/{pet_id}/screenings', headers=headers)
                history.raise_for_status()
                self.assertEqual(history.json()['items'][0]['screening_id'], record['screening_id'])
                normal = await client.post(f'/api/v1/pets/{pet_id}/screenings', headers=headers, json={
                    'spirit': 'normal', 'appetite': 'normal', 'symptoms': [], 'redline_options': [], 'media_ids': []})
                self.assertEqual(normal.status_code, 201)
                self.assertEqual(normal.json()['state'], 'normal')
                self.assertIsNone(normal.json()['redline_card'])
                self.assertIsNotNone(normal.json()['task_id'])
                # T08/F06-3：复查正常覆盖旧 urgent 事件，一次刷新回 normal/100。
                normal_health = await client.get(f'/api/v1/pets/{pet_id}/health', headers=headers)
                normal_health.raise_for_status()
                self.assertEqual((normal_health.json()['state'], normal_health.json()['score']), ('normal', 100))
                self.assertEqual(normal_health.json()['deductions'], [])
                self.assertIsNone(normal_health.json()['urgent_card'])
                removed = await client.delete(
                    f"/api/v1/screenings/{record['screening_id']}/media/{media_id}", headers=headers)
                self.assertEqual(removed.status_code, 204)
                # 照片仍被分身任务引用：只删关联，对象版本保留。
                still = await client.get(f'/api/v1/media/{media_id}', headers=headers)
                self.assertEqual(still.status_code, 200)

                # T10：非红线建议异步生成——pending → worker(fake LLM) → ready + 用量审计。
                observe = await client.post(f'/api/v1/pets/{pet_id}/screenings', headers=headers, json={
                    'spirit': 'normal', 'appetite': 'normal',
                    'symptoms': [{'code': 'vomiting', 'duration': '2-12h', 'frequency': '2-3'}],
                    'redline_options': [], 'media_ids': []})
                observe.raise_for_status()
                observe_record = observe.json()
                self.assertEqual(observe_record['state'], 'observe')
                observe_task = observe_record['task_id']
                self.assertIsNotNone(observe_task)
                observe_health = await client.get(f'/api/v1/pets/{pet_id}/health', headers=headers)
                observe_health.raise_for_status()
                self.assertEqual((observe_health.json()['state'], observe_health.json()['score']), ('observe', 90))
                self.assertEqual(observe_health.json()['deductions'][0]['symptoms'], ['呕吐'])
                before = await client.get(f"/api/v1/screenings/{observe_record['screening_id']}", headers=headers)
                before.raise_for_status()
                self.assertEqual(before.json()['advice']['status'], 'pending')
                pool2 = await create_pool(settings)
                await worker.sweep({'engine': worker_engine, 'redis': pool2})
                runner2 = Worker([worker.run_task], redis_settings=settings, redis_pool=pool2,
                                 max_tries=1, burst=True, poll_delay=0.05, on_startup=on_startup)
                await runner2.async_run()
                await pool2.aclose()
                after_task = await client.get(f'/api/v1/tasks/{observe_task}', headers=headers)
                after_task.raise_for_status()
                self.assertEqual(after_task.json()['status'], 'succeeded')
                after = await client.get(f"/api/v1/screenings/{observe_record['screening_id']}", headers=headers)
                after.raise_for_status()
                advice = after.json()['advice']
                self.assertEqual((advice['status'], advice['source']), ('ready', 'llm'))
                self.assertEqual(advice['text'], '建议观察精神与食欲变化。')
                self.assertEqual(advice['tips'], ['记录变化'])
                with Session(worker_engine) as db:
                    logs = db.scalars(select(AiUsageLog).where(AiUsageLog.task_id == observe_task)).all()
                    self.assertEqual(len(logs), 1)
                    self.assertEqual((logs[0].kind, logs[0].provider, logs[0].tokens_in, logs[0].tokens_out),
                                     ('llm', 'fake', 100, 30))
                final_health = await client.get(f'/api/v1/pets/{pet_id}/health', headers=headers)
                final_health.raise_for_status()
                self.assertEqual((final_health.json()['state'], final_health.json()['score']), ('observe', 90))
                self.assertEqual(final_health.json()['latest_screening']['screening_id'], observe_record['screening_id'])

                # T12：饮食快录→日聚合→删除重算→首页同源→喂养参考（无体重给引导）。
                diet = await client.post(f'/api/v1/pets/{pet_id}/diet', headers=headers,
                                         json={'food_type': 'dry', 'amount_g': 50})
                self.assertEqual(diet.status_code, 201)
                self.assertEqual(diet.json()['kcal_est'], 190.0)
                snack = await client.post(f'/api/v1/pets/{pet_id}/diet', headers=headers,
                                          json={'food_type': 'snack', 'amount_g': 20})
                snack.raise_for_status()
                self.assertIsNone(snack.json()['kcal_est'])
                daily = await client.get(f'/api/v1/pets/{pet_id}/diet', headers=headers,
                                         params={'date': utcnow().date().isoformat(), 'tz_offset_minutes': 0})
                daily.raise_for_status()
                self.assertEqual((daily.json()['total_g'], daily.json()['total_kcal'], daily.json()['count']),
                                 (70.0, 190.0, 2))
                diet_health = await client.get(f'/api/v1/pets/{pet_id}/health', headers=headers)
                diet_health.raise_for_status()
                self.assertEqual(diet_health.json()['diet_today']['count'], 2)
                self.assertEqual(diet_health.json()['diet_today']['total_kcal'], 190.0)
                deleted = await client.delete(f"/api/v1/pets/{pet_id}/diet/{snack.json()['id']}", headers=headers)
                self.assertEqual(deleted.status_code, 204)
                reference = await client.get(f'/api/v1/pets/{pet_id}/feeding-reference', headers=headers)
                reference.raise_for_status()
                self.assertFalse(reference.json()['has_weight'])
                self.assertEqual(reference.json()['disclaimer'],
                                 '以上为公开营养学公式换算的参考值,非医嘱;请结合体况与兽医建议调整。')

                # T13：体重录入→骤变提示→档案/首页/喂养参考即时更新（AC-08-1/2）。
                old_weight = await client.post(f'/api/v1/pets/{pet_id}/weights', headers=headers,
                                               json={'weight_kg': 4.0, 'measured_at': (utcnow() - timedelta(days=6)).isoformat()})
                old_weight.raise_for_status()
                new_weight = await client.post(f'/api/v1/pets/{pet_id}/weights', headers=headers, json={'weight_kg': 3.5})
                new_weight.raise_for_status()
                weights = await client.get(f'/api/v1/pets/{pet_id}/weights', headers=headers)
                weights.raise_for_status()
                alert = weights.json()['trend']['alert']
                self.assertEqual((alert['direction'], alert['pct'], alert['suggestion']), ('loss', -12.5, 'screening'))
                profile = await client.get(f'/api/v1/pets/{pet_id}', headers=headers)
                profile.raise_for_status()
                self.assertEqual(profile.json()['latest_weight']['weight_kg'], 3.5)
                weight_health = await client.get(f'/api/v1/pets/{pet_id}/health', headers=headers)
                weight_health.raise_for_status()
                self.assertEqual(weight_health.json()['latest_weight']['weight_kg'], 3.5)
                fed_reference = await client.get(f'/api/v1/pets/{pet_id}/feeding-reference', headers=headers)
                fed_reference.raise_for_status()
                self.assertTrue(fed_reference.json()['has_weight'])
                self.assertEqual(fed_reference.json()['weight_kg'], 3.5)
                self.assertGreater(fed_reference.json()['der_kcal'], 0)
                out_of_range = await client.post(f'/api/v1/pets/{pet_id}/weights', headers=headers, json={'weight_kg': 30.01})
                self.assertEqual(out_of_range.status_code, 400)

                # T14：幂等键回放——同键同 body 返回同一记录，不重复计数；同键异 body 409。
                key_headers = {**headers, 'Idempotency-Key': 'e2e-diet-key-0001'}
                first = await client.post(f'/api/v1/pets/{pet_id}/diet', headers=key_headers,
                                          json={'food_type': 'dry', 'amount_g': 30})
                self.assertEqual(first.status_code, 201)
                replay = await client.post(f'/api/v1/pets/{pet_id}/diet', headers=key_headers,
                                           json={'food_type': 'dry', 'amount_g': 30})
                self.assertEqual(replay.status_code, 201)
                self.assertEqual(replay.json()['id'], first.json()['id'])
                self.assertEqual(replay.headers.get('idempotent-replay'), 'true')
                conflict = await client.post(f'/api/v1/pets/{pet_id}/diet', headers=key_headers,
                                             json={'food_type': 'dry', 'amount_g': 31})
                self.assertEqual(conflict.status_code, 409)
                self.assertEqual(conflict.json()['code'], 'IDEMPOTENCY_CONFLICT')
                after_replay = await client.get(f'/api/v1/pets/{pet_id}/diet', headers=headers,
                                                params={'date': utcnow().date().isoformat(), 'tz_offset_minutes': 0})
                after_replay.raise_for_status()
                self.assertEqual((after_replay.json()['count'], after_replay.json()['total_kcal']), (2, 304.0))

                # T15：文字聊天——线程复用、人设 LLM 回复、红线零 LLM、幂等回放。
                chat_llm = FakeLLMProvider(reply='{"reply": "喵～我在呢", "emotion": "happy"}')
                app.state.chat_llm_provider = chat_llm
                session = await client.post(f'/api/v1/pets/{pet_id}/chat/sessions', headers=headers)
                self.assertEqual(session.status_code, 201)
                sid = session.json()['session_id']
                again = await client.post(f'/api/v1/pets/{pet_id}/chat/sessions', headers=headers)
                self.assertEqual(again.status_code, 200)
                self.assertEqual(again.json()['session_id'], sid)
                chat_key_headers = {**headers, 'Idempotency-Key': 'e2e-chat-key-0001'}
                sent = await client.post(f'/api/v1/chat/sessions/{sid}/messages', headers=chat_key_headers,
                                         json={'kind': 'text', 'content': '团团你在干嘛呀'})
                self.assertEqual(sent.status_code, 201)
                self.assertEqual(sent.json()['pet_message']['source'], 'llm')
                self.assertEqual(sent.json()['pet_message']['emotion_label'], 'happy')
                self.assertIsNone(sent.json()['guidance'])
                self.assertEqual(len(chat_llm.calls), 1)
                replayed = await client.post(f'/api/v1/chat/sessions/{sid}/messages', headers=chat_key_headers,
                                             json={'kind': 'text', 'content': '团团你在干嘛呀'})
                self.assertEqual(replayed.status_code, 201)
                self.assertEqual(replayed.json()['user_message']['id'], sent.json()['user_message']['id'])
                self.assertEqual(replayed.headers.get('idempotent-replay'), 'true')
                self.assertEqual(len(chat_llm.calls), 1)
                redline = await client.post(f'/api/v1/chat/sessions/{sid}/messages', headers=headers,
                                            json={'kind': 'text', 'content': '猫咪张口呼吸怎么办'})
                self.assertEqual(redline.status_code, 201)
                self.assertEqual(redline.json()['guidance']['title'], '建议立即就医')
                self.assertEqual(redline.json()['guidance']['route'], 'screening')
                self.assertEqual(redline.json()['pet_message']['emotion_label'], 'painful')
                self.assertEqual(len(chat_llm.calls), 1)  # 红线零 LLM
                messages = await client.get(f'/api/v1/chat/sessions/{sid}/messages', headers=headers,
                                            params={'limit': 4})
                messages.raise_for_status()
                items = messages.json()['items']
                self.assertEqual(len(items), 4)
                self.assertEqual(items[0]['role'], 'pet')
                self.assertIsNotNone(messages.json()['next_before'])
                with Session(worker_engine) as db:
                    chat_logs = db.scalars(select(AiUsageLog).where(
                        AiUsageLog.task_id.is_(None), AiUsageLog.kind == 'llm')).all()
                    self.assertEqual(len(chat_logs), 1)
                    self.assertEqual((chat_logs[0].tokens_in, chat_logs[0].tokens_out), (100, 30))

                # T16：录音解读——presign 上传→202 异步→同音频合并→worker 解读→情绪气泡+签名播放。
                audio_buffer = io.BytesIO()
                with wave.open(audio_buffer, 'wb') as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(8000)
                    wav.writeframes(b'\x00\x00' * 8000)
                audio_payload = audio_buffer.getvalue()
                audio_ticket = await client.post('/api/v1/media/presign', headers=headers, json={
                    'pet_id': pet_id, 'kind': 'audio', 'content_type': 'audio/wav',
                    'size_bytes': len(audio_payload)})
                self.assertEqual(audio_ticket.status_code, 201)
                audio_media_id = audio_ticket.json()['media_id']
                audio_upload = audio_ticket.json()['upload']
                async with httpx.AsyncClient() as storage:
                    audio_up = await storage.post(audio_upload['url'], data=audio_upload['fields'],
                                                  files={'file': ('meow.wav', audio_payload, 'audio/wav')}, timeout=15)
                self.assertIn(audio_up.status_code, (200, 204))
                audio_complete = await client.post(f'/api/v1/media/{audio_media_id}/complete', headers=headers)
                audio_complete.raise_for_status()
                self.assertEqual(audio_complete.json()['status'], 'verified')
                audio_sent = await client.post(f'/api/v1/chat/sessions/{sid}/messages', headers=headers,
                                               json={'kind': 'audio', 'media_id': audio_media_id})
                self.assertEqual(audio_sent.status_code, 202)
                audio_task = audio_sent.json()['task_id']
                self.assertIsNone(audio_sent.json()['pet_message'])
                self.assertTrue(audio_sent.json()['user_message']['audio_url'].startswith('http://127.0.0.1:9000/'))
                audio_merged = await client.post(f'/api/v1/chat/sessions/{sid}/messages', headers=headers,
                                                 json={'kind': 'audio', 'media_id': audio_media_id})
                self.assertEqual(audio_merged.status_code, 200)
                self.assertEqual(audio_merged.json()['task_id'], audio_task)

                audio_llm = FakeLLMProvider(reply='{"reply": "喵～我听到啦", "emotion": "happy"}')

                async def on_startup_audio(ctx):
                    ctx['engine'] = worker_engine
                    ctx['assets'] = S3Assets.from_env()
                    ctx['audio_provider'] = FakeAudioProvider()
                    ctx['llm_provider'] = audio_llm
                    ctx['chat_config'] = load_chat_config(RULES_DIR)

                pool3 = await create_pool(settings)
                await worker.sweep({'engine': worker_engine, 'redis': pool3})
                runner3 = Worker([worker.run_task], redis_settings=settings, redis_pool=pool3,
                                 max_tries=1, burst=True, poll_delay=0.05, on_startup=on_startup_audio)
                await runner3.async_run()
                await pool3.aclose()
                audio_after = await client.get(f'/api/v1/tasks/{audio_task}', headers=headers)
                audio_after.raise_for_status()
                self.assertEqual(audio_after.json()['status'], 'succeeded')
                audio_result = audio_after.json()['result']
                self.assertEqual((audio_result['emotion'], audio_result['confidence'], audio_result['uncertain']),
                                 ('happy', 0.82, False))
                audio_messages = await client.get(f'/api/v1/chat/sessions/{sid}/messages', headers=headers,
                                                  params={'limit': 2})
                audio_messages.raise_for_status()
                pet_bubble = audio_messages.json()['items'][0]
                self.assertEqual(pet_bubble['role'], 'pet')
                self.assertEqual(pet_bubble['content'], '喵～我听到啦')
                self.assertEqual((pet_bubble['emotion_label'], pet_bubble['emotion_confidence']), ('happy', 0.82))
                self.assertEqual(pet_bubble['task_id'], audio_task)
                async with httpx.AsyncClient() as storage:
                    played = await storage.get(audio_sent.json()['user_message']['audio_url'], timeout=15)
                self.assertEqual(played.status_code, 200)
                self.assertEqual(played.content, audio_payload)
                with Session(worker_engine) as db:
                    audio_logs = db.scalars(select(AiUsageLog).where(AiUsageLog.task_id == audio_task)).all()
                    self.assertEqual(sorted(log.kind for log in audio_logs), ['audio', 'llm'])
                    audio_log = next(log for log in audio_logs if log.kind == 'audio')
                    self.assertEqual((audio_log.tokens_in, audio_log.tokens_out), (60, 20))

                # T16/AC-09-4：解读失败→未识别+通用安抚，文字聊天仍可用。
                fail_ticket = await client.post('/api/v1/media/presign', headers=headers, json={
                    'pet_id': pet_id, 'kind': 'audio', 'content_type': 'audio/wav',
                    'size_bytes': len(audio_payload)})
                self.assertEqual(fail_ticket.status_code, 201)
                fail_media_id = fail_ticket.json()['media_id']
                fail_upload = fail_ticket.json()['upload']
                async with httpx.AsyncClient() as storage:
                    fail_up = await storage.post(fail_upload['url'], data=fail_upload['fields'],
                                                 files={'file': ('meow.wav', audio_payload, 'audio/wav')}, timeout=15)
                self.assertIn(fail_up.status_code, (200, 204))
                fail_complete = await client.post(f'/api/v1/media/{fail_media_id}/complete', headers=headers)
                fail_complete.raise_for_status()
                fail_sent = await client.post(f'/api/v1/chat/sessions/{sid}/messages', headers=headers,
                                              json={'kind': 'audio', 'media_id': fail_media_id})
                self.assertEqual(fail_sent.status_code, 202)
                fail_task = fail_sent.json()['task_id']

                async def on_startup_audio_fail(ctx):
                    ctx['engine'] = worker_engine
                    ctx['assets'] = S3Assets.from_env()
                    ctx['audio_provider'] = FakeAudioProvider(fail=True)
                    ctx['llm_provider'] = audio_llm
                    ctx['chat_config'] = load_chat_config(RULES_DIR)

                pool4 = await create_pool(settings)
                await worker.sweep({'engine': worker_engine, 'redis': pool4})
                runner4 = Worker([worker.run_task], redis_settings=settings, redis_pool=pool4,
                                 max_tries=1, burst=True, poll_delay=0.05, on_startup=on_startup_audio_fail)
                await runner4.async_run()
                await pool4.aclose()
                fail_after = await client.get(f'/api/v1/tasks/{fail_task}', headers=headers)
                fail_after.raise_for_status()
                self.assertEqual(fail_after.json()['status'], 'succeeded')
                self.assertEqual(fail_after.json()['result']['emotion'], 'unrecognized')
                fail_messages = await client.get(f'/api/v1/chat/sessions/{sid}/messages', headers=headers,
                                                 params={'limit': 1})
                fail_messages.raise_for_status()
                fail_bubble = fail_messages.json()['items'][0]
                self.assertIsNone(fail_bubble['emotion_label'])
                self.assertEqual(fail_bubble['content'],
                                 '喵…刚才那段声音我没太听清。你摸摸我,用文字告诉我发生了什么,我一直都在。')
                text_after_fail = await client.post(f'/api/v1/chat/sessions/{sid}/messages', headers=headers,
                                                    json={'kind': 'text', 'content': '还能聊天吗'})
                self.assertEqual(text_after_fail.status_code, 201)
                self.assertEqual(text_after_fail.json()['pet_message']['source'], 'llm')

                # T17：配额热调→429「明日再试」+红线豁免；plans/entitlement 只读；training 单独授权。
                with patch.dict(os.environ, {'QUOTA_SCREENING': '1', 'QUOTA_AVATAR': '1', 'QUOTA_CHAT': '1'}):
                    blocked_screen = await client.post(f'/api/v1/pets/{pet_id}/screenings', headers=headers,
                                                       json={'spirit': 'normal', 'appetite': 'normal'})
                    self.assertEqual(blocked_screen.status_code, 429)
                    self.assertEqual(blocked_screen.json()['code'], 'QUOTA_EXCEEDED')
                    self.assertIn('明日再试', blocked_screen.json()['message'])
                    redline_ok = await client.post(f'/api/v1/pets/{pet_id}/screenings', headers=headers,
                                                   json={'spirit': 'normal', 'appetite': 'normal',
                                                         'redline_options': ['open_mouth_breathing']})
                    self.assertEqual(redline_ok.status_code, 201)
                    self.assertEqual(redline_ok.json()['state'], 'urgent')
                    blocked_avatar = await client.post(f'/api/v1/pets/{pet_id}/avatar', headers=headers,
                                                       json={'media_id': media_id})
                    self.assertEqual(blocked_avatar.status_code, 429)
                    blocked_chat = await client.post(f'/api/v1/chat/sessions/{sid}/messages', headers=headers,
                                                     json={'kind': 'text', 'content': '配额用完了吗'})
                    self.assertEqual(blocked_chat.status_code, 429)
                    quota_view = await client.get('/api/v1/quota', headers=headers)
                    quota_view.raise_for_status()
                    self.assertEqual(quota_view.json()['metrics']['screening']['limit'], 1)
                plans = await client.get('/api/v1/plans', headers=headers)
                plans.raise_for_status()
                self.assertEqual({p['code'] for p in plans.json()['items']}, {'free', 'pro'})
                entitlement = await client.get('/api/v1/me/entitlement', headers=headers)
                entitlement.raise_for_status()
                self.assertEqual((entitlement.json()['plan'], entitlement.json()['message']), ('free', '测试期免费'))
                training_on = await client.post('/api/v1/consents/training', headers=headers, json={'granted': True})
                self.assertEqual(training_on.status_code, 200)
                self.assertTrue(training_on.json()['training_granted'])
                training_off = await client.post('/api/v1/consents/training', headers=headers, json={'granted': False})
                self.assertFalse(training_off.json()['training_granted'])

                # T17：GIF 导出——202+同动作合并→worker ffmpeg 水印转码→签名下载 GIF89a 480p。
                gif_sent = await client.post(f'/api/v1/pets/{pet_id}/share/gif', headers=headers,
                                             json={'action': 'idle'})
                self.assertEqual(gif_sent.status_code, 202)
                gif_task = gif_sent.json()['task_id']
                gif_merge = await client.post(f'/api/v1/pets/{pet_id}/share/gif', headers=headers,
                                              json={'action': 'idle'})
                self.assertEqual(gif_merge.status_code, 200)
                self.assertEqual(gif_merge.json()['task_id'], gif_task)

                # e2e 的 avatar 片是 fake 字节；GIF 转码需要真实视频——用占位库 idle 片替换该对象版本。
                real_clip = (Path(__file__).resolve().parents[1] / 'assets' / 'placeholders' / 'standard' / 'idle.mp4').read_bytes()
                gif_storage = PhotoStorage.from_env()
                with Session(worker_engine) as db, db.begin():
                    avatar_row = db.get(Task, task_id)
                    clip_key = avatar_row.result['clips']['idle']['key']
                put = gif_storage.client.put_object(Bucket=gif_storage.bucket, Key=clip_key,
                                                    Body=real_clip, ContentType='video/mp4')
                with Session(worker_engine) as db, db.begin():
                    gif_row = db.get(Task, gif_task)
                    gif_row.payload = {**gif_row.payload, 'clip_version_id': put['VersionId']}

                async def on_startup_gif(ctx):
                    ctx['engine'] = worker_engine
                    ctx['assets'] = S3Assets.from_env()

                pool5 = await create_pool(settings)
                await worker.sweep({'engine': worker_engine, 'redis': pool5})
                runner5 = Worker([worker.run_task], redis_settings=settings, redis_pool=pool5,
                                 max_tries=1, burst=True, poll_delay=0.05, on_startup=on_startup_gif)
                await runner5.async_run()
                await pool5.aclose()
                gif_after = await client.get(f'/api/v1/tasks/{gif_task}', headers=headers)
                gif_after.raise_for_status()
                self.assertEqual(gif_after.json()['status'], 'succeeded')
                gif_url = gif_after.json()['download_url']
                self.assertTrue(gif_url)
                async with httpx.AsyncClient() as storage:
                    gif_bytes = (await storage.get(gif_url, timeout=15)).content
                self.assertEqual(gif_bytes[:6], b'GIF89a')
                self.assertEqual(Image.open(io.BytesIO(gif_bytes)).size[1], 480)

                # T17：注销→冻结登录→幂等 200→到期 purge 物理清除（含 OSS），审计仅匿名统计。
                user_id = (await client.get('/api/v1/me', headers=headers)).json()['id']
                deleted = await client.delete('/api/v1/me', headers=headers)
                self.assertEqual(deleted.status_code, 202)
                purge_after = deleted.json()['purge_after']
                deleted_again = await client.delete('/api/v1/me', headers=headers)
                self.assertEqual(deleted_again.status_code, 200)
                self.assertEqual(deleted_again.json()['purge_after'], purge_after)
                frozen_login = await client.post('/api/v1/auth/login',
                                                 json={'email': 'e2e@example.com', 'password': 'Strong123'})
                self.assertEqual(frozen_login.status_code, 401)
                frozen_me = await client.get('/api/v1/me', headers=headers)
                self.assertEqual(frozen_me.status_code, 401)
                with Session(worker_engine) as db, db.begin():
                    job = db.scalar(select(DeletionJob).where(DeletionJob.user_id == user_id))
                    job.purge_after = utcnow() - timedelta(minutes=1)
                storage = PhotoStorage.from_env()
                purged = await asyncio.to_thread(purge_due, worker_engine, storage=storage, now=utcnow())
                self.assertEqual(purged, [user_id])
                with Session(worker_engine) as db:
                    self.assertIsNone(db.get(User, user_id))
                    self.assertIsNone(db.get(Pet, pet_id))
                    self.assertEqual(db.scalars(select(MediaUpload)).all(), [])
                    anonymous = db.scalars(select(AiUsageLog).where(AiUsageLog.user_id.is_(None))).all()
                    self.assertGreater(len(anonymous), 0)
                from botocore.exceptions import ClientError
                with self.assertRaises(ClientError):
                    storage.client.head_object(Bucket=storage.bucket, Key=f'photos/{pet_id}/{media_id}')


if __name__ == '__main__':
    unittest.main()
