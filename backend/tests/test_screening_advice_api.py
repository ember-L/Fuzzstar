"""T10：初筛建议入队、urgent 模板即存、GET 建议状态解析（pending/ready/degraded）。"""

import re
from datetime import timedelta
from pathlib import Path
from unittest import TestCase

from sqlalchemy import select
from sqlalchemy.orm import Session
from test_screening_api import ScreeningFixture

from app.core.security import utcnow
from app.models import AiUsageLog, HealthScreening, Task
from app.services.advice import load_advice_templates

RULES_DIR = Path(__file__).resolve().parents[1] / 'rules'
OBSERVE_BODY = {
    'spirit': 'normal',
    'appetite': 'normal',
    'symptoms': [{'code': 'vomiting', 'duration': '2-12h', 'frequency': '2-3'}],
}
URGENT_BODY = {'spirit': 'normal', 'appetite': 'normal', 'redline_options': ['open_mouth_breathing']}
HEX32 = re.compile(r'^[0-9a-f]{32}$')


class AdviceApiFixture(ScreeningFixture):
    def setUp(self):
        super().setUp()
        self.templates = load_advice_templates(RULES_DIR)

    def task_for(self, screening_id):
        with Session(self.engine) as db:
            tasks = db.scalars(select(Task).where(Task.type == 'screening_analysis')).all()
            return next((t for t in tasks if (t.payload or {}).get('screening_id') == screening_id), None)

    def detail(self, screening_id):
        return self.client.get(f'/api/v1/screenings/{screening_id}', headers=self.headers).raise_for_status().json()

    def patch_task(self, task_id, **values):
        with Session(self.engine) as db:
            task = db.get(Task, task_id)
            for key, value in values.items():
                setattr(task, key, value)
            db.commit()


class SubmissionAdviceTests(AdviceApiFixture, TestCase):
    def test_non_urgent_enqueues_screening_analysis(self):
        body = self.submit(OBSERVE_BODY).raise_for_status().json()
        self.assertEqual(body['state'], 'observe')
        self.assertRegex(body['task_id'], HEX32)
        task = self.task_for(body['screening_id'])
        self.assertIsNotNone(task)
        self.assertEqual(
            (task.id, task.status, task.payload), (body['task_id'], 'pending', {'screening_id': body['screening_id']})
        )
        with Session(self.engine) as db:
            self.assertEqual(db.get(HealthScreening, body['screening_id']).task_id, task.id)
        detail = self.detail(body['screening_id'])
        self.assertEqual(detail['task_id'], task.id)
        self.assertEqual(detail['advice'], {'status': 'pending', 'source': None, 'text': None, 'tips': None})

    def test_normal_submission_also_enqueues(self):
        body = self.submit().raise_for_status().json()
        self.assertEqual(body['state'], 'normal')
        self.assertIsNotNone(self.task_for(body['screening_id']))

    def test_urgent_persists_template_without_task_or_usage(self):
        body = self.submit(URGENT_BODY).raise_for_status().json()
        self.assertEqual(body['state'], 'urgent')
        self.assertIsNone(body['task_id'])
        self.assertIsNone(self.task_for(body['screening_id']))
        with Session(self.engine) as db:
            screening = db.get(HealthScreening, body['screening_id'])
            self.assertEqual(screening.advice_json['source'], 'template')
            self.assertIsNone(screening.llm_advice)
            self.assertEqual(db.scalars(select(AiUsageLog)).all(), [])
        advice = self.detail(body['screening_id'])['advice']
        expected = self.templates['states']['urgent']
        self.assertEqual(advice['status'], 'ready')
        self.assertEqual(advice['source'], 'template')
        self.assertEqual(advice['text'], expected['text'])
        self.assertEqual(advice['tips'], expected['tips'])

    def test_missing_templates_returns_503(self):
        self.client.app.state.advice_templates = None
        for payload in (OBSERVE_BODY, URGENT_BODY):
            response = self.submit(payload)
            self.assertEqual((response.status_code, response.json()['code']), (503, 'CONFIG_UNAVAILABLE'))


class DetailAdviceTests(AdviceApiFixture, TestCase):
    def submit_observe(self):
        return self.submit(OBSERVE_BODY).raise_for_status().json()

    def test_llm_success_shows_ready(self):
        body = self.submit_observe()
        with Session(self.engine) as db:
            screening = db.get(HealthScreening, body['screening_id'])
            screening.llm_advice = '留意呕吐频次并记录。'
            screening.advice_json = {'source': 'llm', 'text': '留意呕吐频次并记录。', 'tips': ['记录时间', '拍照存证']}
            db.commit()
        advice = self.detail(body['screening_id'])['advice']
        self.assertEqual(
            advice,
            {'status': 'ready', 'source': 'llm', 'text': '留意呕吐频次并记录。', 'tips': ['记录时间', '拍照存证']},
        )

    def test_failed_task_degrades_to_template(self):
        body = self.submit_observe()
        self.patch_task(body['task_id'], status='failed', attempts=3)
        advice = self.detail(body['screening_id'])['advice']
        expected = self.templates['states']['observe']
        self.assertEqual(advice['status'], 'degraded')
        self.assertEqual(advice['source'], 'template')
        self.assertEqual(advice['text'], expected['text'])
        self.assertEqual(advice['tips'], expected['tips'])

    def test_persisted_template_after_exhaustion_is_degraded(self):
        body = self.submit_observe()
        self.patch_task(body['task_id'], status='failed', attempts=3)
        with Session(self.engine) as db:
            screening = db.get(HealthScreening, body['screening_id'])
            screening.advice_json = {
                'source': 'template',
                'text': '模板',
                'tips': ['t'],
                'template_version': 'at-2026-11-19',
            }
            db.commit()
        advice = self.detail(body['screening_id'])['advice']
        self.assertEqual((advice['status'], advice['source'], advice['text']), ('degraded', 'template', '模板'))

    def test_pending_over_60s_degrades_without_worker(self):
        body = self.submit_observe()
        self.patch_task(body['task_id'], created_at=utcnow() - timedelta(seconds=61))
        advice = self.detail(body['screening_id'])['advice']
        self.assertEqual(advice['status'], 'degraded')
        self.assertEqual(advice['text'], self.templates['states']['observe']['text'])

    def test_pending_within_60s_stays_pending(self):
        body = self.submit_observe()
        self.patch_task(body['task_id'], created_at=utcnow() - timedelta(seconds=30))
        self.assertEqual(self.detail(body['screening_id'])['advice']['status'], 'pending')
