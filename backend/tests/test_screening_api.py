from datetime import timedelta
import os
from unittest import TestCase
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.orm import Session
from test_auth_api import AuthAPIFixture

from app.core.security import utcnow
from app.models import HealthEvent, HealthScreening, MediaUpload, ScreeningMedia, Task
from app.services.identity import create_email_account

DISCLAIMER = 'AI 结果仅供日常健康管理参考,不替代专业兽医诊断'
CARD_TITLE = '建议立即就医'
CARD_SUBTITLE = '该症状可能危及生命,请不要等待观察,尽快前往具备急诊能力的宠物医院。'
PREPARATION = [
    '带上本条记录与存证照片/视频',
    '出发前电话确认医院急诊能力',
    '疑似中毒请携带可疑物品包装,勿自行催吐',
    '勿擅自喂食人用药物',
]


class ScreeningFixture(AuthAPIFixture):
    def setUp(self):
        super().setUp()
        # 测试固定走异步入队（验证 worker 行为），不受开发环境 SCREENING_ADVICE_MODE=sync 影响
        os.environ['SCREENING_ADVICE_MODE'] = 'async'
        self.addCleanup(os.environ.pop, 'SCREENING_ADVICE_MODE', None)
        self.headers = {'Authorization': 'Bearer ' + self.login().json()['access_token']}
        self.client.post(
            '/api/v1/consents', headers=self.headers, json={'privacy': 'p1', 'terms': 't1'}
        ).raise_for_status()
        self.pet = (
            self.client.post('/api/v1/pets', headers=self.headers, json={'name': '团团'})
            .raise_for_status()
            .json()['id']
        )

    def verified_account(self, email, consent=True):
        with Session(self.engine) as db:
            create_email_account(db, email, self.password, self.now)
            db.commit()
        if consent:
            headers = {'Authorization': 'Bearer ' + self.login(email=email).json()['access_token']}
            self.client.post(
                '/api/v1/consents', headers=headers, json={'privacy': 'p1', 'terms': 't1'}
            ).raise_for_status()
        return email

    def submit(self, body=None, pet=None):
        payload = {'spirit': 'normal', 'appetite': 'normal'} if body is None else body
        return self.client.post(f'/api/v1/pets/{pet or self.pet}/screenings', headers=self.headers, json=payload)

    def make_media(self, kind='photo', verified=True, pet=None):
        import uuid

        media_id = uuid.uuid4().hex
        with Session(self.engine) as db:
            db.add(
                MediaUpload(
                    id=media_id,
                    pet_id=pet or self.pet,
                    kind=kind,
                    content_type='image/png' if kind == 'photo' else 'video/mp4',
                    size_bytes=100,
                    expires_at=utcnow() + timedelta(minutes=10),
                    version_id='version-1' if verified else None,
                )
            )
            db.commit()
        return media_id


class SymptomConfigTests(ScreeningFixture, TestCase):
    def test_requires_login_and_consent(self):
        self.assertEqual(self.client.get('/api/v1/config/symptoms').status_code, 401)
        self.verified_account('other@example.com', consent=False)
        token = self.login(email='other@example.com').json()['access_token']
        self.assertEqual(
            self.client.get('/api/v1/config/symptoms', headers={'Authorization': 'Bearer ' + token}).status_code, 403
        )

    def test_payload_is_versioned_and_complete(self):
        data = self.client.get('/api/v1/config/symptoms', headers=self.headers).raise_for_status().json()
        self.assertEqual(data['version'], 'sx-2026-11-19')
        self.assertEqual(len(data['symptoms']), 15)
        self.assertEqual(len(data['redlines']), 6)
        self.assertEqual(data['duration_bands'], ['<2h', '2-12h', '12-24h', '>24h'])
        self.assertEqual(data['notes_max'], 255)
        vomiting = next(s for s in data['symptoms'] if s['code'] == 'vomiting')
        self.assertTrue(vomiting['frequency'])

    def test_missing_rules_returns_503(self):
        self.client.app.state.triage_rules = None
        response = self.client.get('/api/v1/config/symptoms', headers=self.headers)
        self.assertEqual((response.status_code, response.json()['code']), (503, 'CONFIG_UNAVAILABLE'))
        self.assertEqual(self.submit().status_code, 503)


class ScreeningSubmitTests(ScreeningFixture, TestCase):
    def test_auth_and_ownership(self):
        self.assertEqual(self.client.post(f'/api/v1/pets/{self.pet}/screenings', json={}).status_code, 401)
        self.assertEqual(self.submit(pet=self.pet + 1).status_code, 404)

    def test_validation_errors_locate_fields(self):
        cases = [
            ({'appetite': 'normal'}, 'spirit'),
            ({'spirit': 'normal', 'appetite': 'normal', 'symptoms': [{'code': 'vomiting'}]}, 'symptoms[0].duration'),
            (
                {'spirit': 'normal', 'appetite': 'normal', 'symptoms': [{'code': 'nope', 'duration': '<2h'}]},
                'symptoms[0].code',
            ),
            (
                {
                    'spirit': 'normal',
                    'appetite': 'normal',
                    'symptoms': [{'code': 'vomiting', 'duration': '<2h', 'frequency': '1', 'notes': 'x' * 256}],
                },
                'symptoms[0].notes',
            ),
            (
                {'spirit': 'normal', 'appetite': 'normal', 'symptoms': [{'code': 'vomiting', 'duration': '<2h'}]},
                'symptoms[0].frequency',
            ),
        ]
        for body, field in cases:
            response = self.submit(body)
            self.assertEqual((response.status_code, response.json()['code']), (400, 'VALIDATION_ERROR'), body)
            self.assertIn(field, [e['field'] for e in response.json()['detail']['fields']], body)

    def test_normal_creates_no_event(self):
        data = self.submit().raise_for_status().json()
        self.assertEqual(data['state'], 'normal')
        self.assertFalse(data['redline_hit'])
        self.assertEqual(data['disclaimer'], DISCLAIMER)
        self.assertIsNone(data['redline_card'])
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(HealthEvent).where(HealthEvent.pet_id == self.pet)), None)
            screening = db.get(HealthScreening, data['screening_id'])
            self.assertEqual(screening.rules_version, 'sx-2026-11-19+rl-2026-11-19')

    def test_observe_and_vet_create_weighted_events(self):
        observe = (
            self.submit(
                {
                    'spirit': 'normal',
                    'appetite': 'normal',
                    'symptoms': [{'code': 'vomiting', 'duration': '2-12h', 'frequency': '1'}],
                }
            )
            .raise_for_status()
            .json()
        )
        self.assertEqual(observe['state'], 'observe')
        vet = self.submit({'spirit': 'markedly_down', 'appetite': 'normal'}).raise_for_status().json()
        self.assertEqual(vet['state'], 'vet')
        with Session(self.engine) as db:
            events = db.scalars(
                select(HealthEvent).where(HealthEvent.pet_id == self.pet).order_by(HealthEvent.id)
            ).all()
            # F06-3 复查覆盖（T08 提前实现）：vet 复查解决旧 observe 事件，仅最新结论活跃。
            self.assertEqual(
                [(e.severity, e.score_delta, e.active, e.source) for e in events],
                [('observe', 10, False, 'screening'), ('vet', 30, True, 'screening')],
            )
            self.assertIsNotNone(events[0].resolved_at)
            self.assertIsNone(events[1].resolved_at)
            self.assertEqual([e.source_id for e in events], [observe['screening_id'], vet['screening_id']])

    def test_explicit_redline_is_urgent_with_verbatim_copy(self):
        data = (
            self.submit({'spirit': 'normal', 'appetite': 'normal', 'redline_options': ['open_mouth_breathing']})
            .raise_for_status()
            .json()
        )
        self.assertEqual((data['state'], data['redline_hit'], data['redlines']), ('urgent', True, ['resp_distress']))
        self.assertEqual(
            data['redline_card'], {'title': CARD_TITLE, 'subtitle': CARD_SUBTITLE, 'preparation': PREPARATION}
        )
        with Session(self.engine) as db:
            event = db.scalar(select(HealthEvent).where(HealthEvent.pet_id == self.pet))
            self.assertEqual((event.severity, event.score_delta), ('urgent', 60))

    def test_derived_redline_vomiting_over_24h(self):
        data = (
            self.submit(
                {
                    'spirit': 'normal',
                    'appetite': 'normal',
                    'symptoms': [{'code': 'vomiting', 'duration': '>24h', 'frequency': '>6'}],
                }
            )
            .raise_for_status()
            .json()
        )
        self.assertEqual((data['state'], data['redlines']), ('urgent', ['vomiting_persistent']))

    def test_media_attachment_limits_and_verification(self):
        photo = self.make_media()
        video = self.make_media(kind='video')
        ok = (
            self.submit({'spirit': 'normal', 'appetite': 'normal', 'media_ids': [photo, video]})
            .raise_for_status()
            .json()
        )
        detail = (
            self.client.get(f'/api/v1/screenings/{ok["screening_id"]}', headers=self.headers).raise_for_status().json()
        )
        self.assertEqual({m['media_id']: m['type'] for m in detail['media']}, {photo: 'photo', video: 'video'})
        unverified = self.make_media(verified=False)
        response = self.submit({'spirit': 'normal', 'appetite': 'normal', 'media_ids': [unverified]})
        self.assertEqual((response.status_code, response.json()['code']), (409, 'MEDIA_NOT_VERIFIED'))
        foreign = self.make_media(pet=self.pet + 1)
        self.assertEqual(
            self.submit({'spirit': 'normal', 'appetite': 'normal', 'media_ids': [foreign]}).status_code, 404
        )
        four = [self.make_media() for _ in range(4)]
        response = self.submit({'spirit': 'normal', 'appetite': 'normal', 'media_ids': four})
        self.assertEqual((response.status_code, response.json()['code']), (400, 'VALIDATION_ERROR'))
        response = self.submit({'spirit': 'normal', 'appetite': 'normal', 'media_ids': [photo, photo]})
        self.assertEqual(response.status_code, 400)


class ScreeningReadTests(ScreeningFixture, TestCase):
    def test_detail_reproduces_grades_and_is_owner_only(self):
        body = {
            'spirit': 'normal',
            'appetite': 'decreased',
            'symptoms': [
                {'code': 'diarrhea', 'duration': '12-24h', 'frequency': '2-3', 'notes': '软便', 'severe': False},
                {'code': 'limping', 'duration': '<2h', 'severe': True},
            ],
        }
        created = self.submit(body).raise_for_status().json()
        self.assertEqual(created['state'], 'vet')  # limping severe → vet
        detail = (
            self.client.get(f'/api/v1/screenings/{created["screening_id"]}', headers=self.headers)
            .raise_for_status()
            .json()
        )
        self.assertEqual(detail['rules_version'], 'sx-2026-11-19+rl-2026-11-19')
        self.assertEqual(detail['symptom_grades'], {'diarrhea': 'observe', 'limping': 'vet'})
        labels = {s['code']: s['label'] for s in detail['symptoms']}
        self.assertEqual(labels['diarrhea'], '软便/腹泻')
        self.assertIsNone(detail['llm_advice'])
        self.assertEqual(detail['disclaimer'], DISCLAIMER)
        self.verified_account('nosy@example.com', consent=True)
        token = self.login(email='nosy@example.com').json()['access_token']
        self.assertEqual(
            self.client.get(
                f'/api/v1/screenings/{created["screening_id"]}', headers={'Authorization': 'Bearer ' + token}
            ).status_code,
            404,
        )

    def test_history_lists_newest_first(self):
        first = self.submit().raise_for_status().json()['screening_id']
        second = (
            self.submit({'spirit': 'slightly_down', 'appetite': 'normal'}).raise_for_status().json()['screening_id']
        )
        data = self.client.get(f'/api/v1/pets/{self.pet}/screenings', headers=self.headers).raise_for_status().json()
        self.assertEqual([item['screening_id'] for item in data['items']], [second, first])
        self.assertEqual(data['items'][0]['state'], 'normal')  # slightly_down 单独不触发 vet，无症状→normal


class ScreeningMediaDeleteTests(ScreeningFixture, TestCase):
    def setUp(self):
        super().setUp()
        from app.services.media import PhotoStorage

        env = {
            'MEDIA_S3_ENDPOINT': 'http://127.0.0.1:9000',
            'MEDIA_S3_BUCKET': 'private-photos',
            'MEDIA_S3_ACCESS_KEY': 'test-only',
            'MEDIA_S3_SECRET_KEY': 'test-only-secret',
        }
        with patch.dict('os.environ', env):
            self.client.app.state.photo_storage = PhotoStorage.from_env()

    def submit_with_media(self, media_ids):
        return (
            self.submit({'spirit': 'normal', 'appetite': 'normal', 'media_ids': media_ids})
            .raise_for_status()
            .json()['screening_id']
        )

    def test_delete_unreferenced_media_removes_object_and_row(self):
        media = self.make_media()
        screening = self.submit_with_media([media])
        storage = self.client.app.state.photo_storage
        self.assertIsNotNone(storage)
        with patch.object(storage.client, 'delete_object') as delete:
            response = self.client.delete(f'/api/v1/screenings/{screening}/media/{media}', headers=self.headers)
        self.assertEqual(response.status_code, 204)
        delete.assert_called_once()
        self.assertEqual(delete.call_args.kwargs['VersionId'], 'version-1')
        with Session(self.engine) as db:
            self.assertIsNone(db.get(MediaUpload, media))
            self.assertEqual(db.scalar(select(ScreeningMedia).where(ScreeningMedia.screening_id == screening)), None)

    def test_delete_keeps_media_referenced_elsewhere(self):
        media = self.make_media()
        first = self.submit_with_media([media])
        second = self.submit_with_media([media])
        with patch.object(self.client.app.state.photo_storage.client, 'delete_object') as delete:
            self.client.delete(f'/api/v1/screenings/{first}/media/{media}', headers=self.headers).raise_for_status()
        delete.assert_not_called()
        with Session(self.engine) as db:
            self.assertIsNotNone(db.get(MediaUpload, media))
            self.assertIsNotNone(db.scalar(select(ScreeningMedia).where(ScreeningMedia.screening_id == second)))

    def test_delete_keeps_media_used_by_avatar_task(self):
        media = self.make_media()
        screening = self.submit_with_media([media])
        with Session(self.engine) as db:
            db.add(
                Task(
                    id='a' * 32,
                    pet_id=self.pet,
                    type='avatar_batch',
                    status='succeeded',
                    request_key='k' * 64,
                    payload={'media_id': media},
                    attempts=1,
                )
            )
            db.commit()
        with patch.object(self.client.app.state.photo_storage.client, 'delete_object') as delete:
            self.client.delete(f'/api/v1/screenings/{screening}/media/{media}', headers=self.headers).raise_for_status()
        delete.assert_not_called()
        with Session(self.engine) as db:
            self.assertIsNotNone(db.get(MediaUpload, media))

    def test_delete_unknown_association_is_404(self):
        screening = self.submit_with_media([])
        self.assertEqual(
            self.client.delete(f'/api/v1/screenings/{screening}/media/' + 'b' * 32, headers=self.headers).status_code,
            404,
        )
