"""T10 worker screening_analysis：LLM 建议成功/禁词重试/失败降级模板 + ai_usage_logs。"""
import asyncio
import unittest
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.services.advice import load_advice_templates
from app.models import AiUsageLog, Base, HealthScreening, Pet, ScreeningSymptom, Task, User
from app.providers.fake import FakeLLMProvider
from app.services.tasks import enqueue_task
from app.services.triage import load_rules
from app import worker

RULES_DIR = Path(__file__).resolve().parents[1] / 'rules'
GOOD_REPLY = '{"text": "建议观察精神与食欲变化,记录呕吐频次。", "tips": ["保证饮水", "24小时后复查"]}'


def make_engine():
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return engine


def seed_screening(engine, state='observe'):
    with Session(engine) as db, db.begin():
        db.add(User(id=1, nickname='测试用户'))
        db.add(Pet(id=1, user_id=1, name='团团', species='cat', status='active'))
        screening = HealthScreening(pet_id=1, user_id=1, state=state, redline_hit=False,
                                    spirit='slightly_down', appetite='decreased',
                                    rules_version='sx-2026-11-19+rl-2026-11-19',
                                    triage_json={'redlines': [], 'symptom_grades': {'vomiting': state}})
        db.add(screening)
        db.flush()
        screening_id = screening.id
        db.add(ScreeningSymptom(screening_id=screening_id, symptom_code='vomiting',
                                duration='2-12h', frequency='2-3', notes='饭后吐', severe=False))
        task = enqueue_task(db, 1, 'screening_analysis', str(screening_id), {'screening_id': screening_id})
        return task.id, screening_id


class ScreeningWorkerTests(unittest.TestCase):
    def setUp(self):
        self.engine = make_engine()
        self.addCleanup(self.engine.dispose)
        self.templates = load_advice_templates(RULES_DIR)
        self.rules = load_rules(RULES_DIR)
        self.task_id, self.screening_id = seed_screening(self.engine)
        self.llm = FakeLLMProvider(GOOD_REPLY)
        self.ctx = {'engine': self.engine, 'llm_provider': self.llm,
                    'advice_templates': self.templates, 'triage_rules': self.rules}

    def screening(self):
        with Session(self.engine) as db:
            return db.get(HealthScreening, self.screening_id)

    def task(self):
        with Session(self.engine) as db:
            return db.get(Task, self.task_id)

    def usage_rows(self):
        with Session(self.engine) as db:
            return db.scalars(select(AiUsageLog).order_by(AiUsageLog.id)).all()

    def test_success_persists_llm_advice_and_usage(self):
        asyncio.run(worker.run_task(self.ctx, self.task_id))
        task = self.task()
        self.assertEqual(task.status, 'succeeded')
        self.assertEqual(task.result, {'screening_id': self.screening_id, 'source': 'llm'})
        screening = self.screening()
        self.assertIn('观察', screening.llm_advice)
        self.assertEqual(screening.advice_json['source'], 'llm')
        self.assertEqual(screening.advice_json['tips'], ['保证饮水', '24小时后复查'])
        rows = self.usage_rows()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row.kind, row.provider, row.task_id, row.user_id), ('llm', 'fake', self.task_id, 1))
        self.assertEqual((row.tokens_in, row.tokens_out), (100, 30))
        prompt = self.llm.calls[0]['messages'][1]['content']
        self.assertIn('呕吐', prompt)  # 规则标签进入提示词
        self.assertIn('饭后吐', prompt)

    def test_forbidden_output_retries_then_template_fallback(self):
        self.llm = FakeLLMProvider('{"text": "可确诊为肠胃炎", "tips": []}')
        self.ctx['llm_provider'] = self.llm
        for expected in (('pending', 1), ('pending', 2), ('failed', 3)):
            asyncio.run(worker.run_task(self.ctx, self.task_id))
            task = self.task()
            self.assertEqual((task.status, task.attempts), expected)
        screening = self.screening()
        self.assertIsNone(screening.llm_advice)
        self.assertEqual(screening.advice_json['source'], 'template')
        self.assertEqual(screening.advice_json['text'], self.templates['states']['observe']['text'])
        rows = self.usage_rows()
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(r.tokens_in is None and r.tokens_out is None for r in rows))

    def test_transient_failure_then_success_logs_both(self):
        self.llm = FakeLLMProvider(GOOD_REPLY, fail_times=1)
        self.ctx['llm_provider'] = self.llm
        asyncio.run(worker.run_task(self.ctx, self.task_id))
        self.assertEqual(self.task().status, 'pending')
        asyncio.run(worker.run_task(self.ctx, self.task_id))
        self.assertEqual(self.task().status, 'succeeded')
        rows = self.usage_rows()
        self.assertEqual(len(rows), 2)
        self.assertIsNone(rows[0].tokens_in)
        self.assertEqual(rows[1].tokens_in, 100)

    def test_fallback_does_not_overwrite_existing_llm_advice(self):
        asyncio.run(worker.run_task(self.ctx, self.task_id))
        from app.services.advice import apply_template_fallback
        apply_template_fallback(self.engine, self.task_id, self.templates)
        self.assertEqual(self.screening().advice_json['source'], 'llm')


if __name__ == '__main__':
    unittest.main()
