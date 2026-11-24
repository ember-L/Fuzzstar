"""T18: read-only ops report aggregates (AI cost, tasks, denials, quota)."""

import unittest
from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.security import utcnow
from app.models import AiUsageLog, Base, Pet, QuotaDenial, Task, UsageCounter, User
from scripts.ops_report import build_report, render_text


def make_engine():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return engine


class OpsReportTests(unittest.TestCase):
    def setUp(self):
        self.engine = make_engine()
        self.addCleanup(self.engine.dispose)
        self.now = utcnow()
        with Session(self.engine) as db, db.begin():
            db.add_all(
                [
                    User(id=1, nickname='甲'),
                    User(id=2, nickname='乙'),
                    Pet(id=1, user_id=1, name='团团', species='cat', status='active'),
                ]
            )
            db.add_all(
                [
                    AiUsageLog(
                        user_id=1,
                        provider='dashscope',
                        model='qwen-plus',
                        kind='llm',
                        tokens_in=100,
                        tokens_out=30,
                        cost_est=0.002,
                        created_at=self.now - timedelta(days=1),
                    ),
                    AiUsageLog(
                        user_id=1,
                        provider='dashscope',
                        model='qwen2-audio-instruct',
                        kind='audio',
                        media_seconds=12.5,
                        cost_est=0.01,
                        created_at=self.now - timedelta(days=2),
                    ),
                    AiUsageLog(
                        user_id=2,
                        provider='dashscope',
                        model='qwen-plus',
                        kind='llm',
                        tokens_in=50,
                        tokens_out=20,
                        cost_est=0.001,
                        created_at=self.now - timedelta(days=1),
                    ),
                    AiUsageLog(
                        user_id=None,
                        provider='dashscope',
                        model='qwen-plus',
                        kind='llm',
                        tokens_in=10,
                        tokens_out=5,
                        cost_est=0.004,
                        created_at=self.now - timedelta(days=1),
                    ),
                    AiUsageLog(
                        user_id=1,
                        provider='dashscope',
                        model='qwen-plus',
                        kind='llm',
                        tokens_in=999,
                        tokens_out=999,
                        cost_est=9.99,
                        created_at=self.now - timedelta(days=10),
                    ),
                ]
            )
            db.add_all(
                [
                    Task(
                        id='a' * 32,
                        pet_id=1,
                        type='avatar_batch',
                        status='succeeded',
                        request_key='k1',
                        payload={},
                        attempts=1,
                        created_at=self.now - timedelta(hours=2),
                        updated_at=self.now - timedelta(hours=1),
                    ),
                    Task(
                        id='b' * 32,
                        pet_id=1,
                        type='avatar_batch',
                        status='failed',
                        request_key='k2',
                        payload={},
                        attempts=3,
                        created_at=self.now - timedelta(hours=3),
                        updated_at=self.now - timedelta(hours=2),
                    ),
                    Task(
                        id='c' * 32,
                        pet_id=1,
                        type='screening_analysis',
                        status='succeeded',
                        request_key='k3',
                        payload={},
                        attempts=2,
                        created_at=self.now - timedelta(hours=1),
                        updated_at=self.now - timedelta(minutes=30),
                    ),
                    Task(
                        id='d' * 32,
                        pet_id=1,
                        type='gif_export',
                        status='pending',
                        request_key='k4',
                        payload={},
                        attempts=0,
                        created_at=self.now - timedelta(minutes=5),
                        updated_at=self.now - timedelta(minutes=5),
                    ),
                ]
            )
            db.add_all(
                [
                    QuotaDenial(user_id=1, metric='chat_msg', day=self.now.date(), created_at=self.now),
                    QuotaDenial(user_id=1, metric='chat_msg', day=self.now.date(), created_at=self.now),
                    QuotaDenial(
                        user_id=2,
                        metric='screening',
                        day=self.now.date() - timedelta(days=1),
                        created_at=self.now - timedelta(days=1),
                    ),
                    UsageCounter(user_id=1, day=self.now.date(), metric='chat_msg', count=5),
                ]
            )

    def test_ai_calls_and_window(self):
        report = build_report(self.engine, now=self.now, days=7)
        rows = {(row['kind'], row['model']): row for row in report['ai_calls']['rows']}
        self.assertEqual(rows[('llm', 'qwen-plus')]['calls'], 3)
        self.assertEqual(rows[('llm', 'qwen-plus')]['tokens_in'], 160)
        self.assertAlmostEqual(rows[('llm', 'qwen-plus')]['cost_est'], 0.007, places=6)
        self.assertEqual(rows[('audio', 'qwen2-audio-instruct')]['media_seconds'], 12.5)
        self.assertEqual(report['ai_calls']['totals']['calls'], 4)  # the 10-day-old row is excluded
        self.assertAlmostEqual(report['ai_calls']['totals']['cost_est'], 0.017, places=6)

    def test_daily_and_per_user_cost(self):
        report = build_report(self.engine, now=self.now, days=7)
        daily = {row['day']: row for row in report['daily_cost']}
        self.assertEqual(daily[(self.now - timedelta(days=1)).date().isoformat()]['calls'], 3)
        users = {row['user_id']: row for row in report['per_user_cost']}
        self.assertAlmostEqual(users[1]['cost_est'], 0.012, places=6)
        self.assertAlmostEqual(users[None]['cost_est'], 0.004, places=6)
        self.assertEqual(report['per_user_cost'][0]['user_id'], 1)  # descending by cost

    def test_task_stats(self):
        report = build_report(self.engine, now=self.now, days=7)
        tasks = {row['type']: row for row in report['tasks']}
        avatar = tasks['avatar_batch']
        self.assertEqual((avatar['total'], avatar['succeeded'], avatar['failed'], avatar['retried']), (2, 1, 1, 1))
        self.assertAlmostEqual(avatar['avg_duration_s'], 3600.0, places=1)
        self.assertAlmostEqual(avatar['p95_duration_s'], 3600.0, places=1)
        self.assertEqual(tasks['screening_analysis']['retried'], 1)
        self.assertEqual(tasks['gif_export']['in_flight'], 1)
        self.assertIsNone(tasks['gif_export']['avg_duration_s'])

    def test_denials_and_quota_usage(self):
        report = build_report(self.engine, now=self.now, days=7)
        denials = {(row['metric'], row['day']): row['count'] for row in report['quota_denials']}
        self.assertEqual(denials[('chat_msg', self.now.date().isoformat())], 2)
        self.assertEqual(denials[('screening', (self.now - timedelta(days=1)).date().isoformat())], 1)
        usage = {row['metric']: row['used'] for row in report['quota_usage_today']}
        self.assertEqual(usage['chat_msg'], 5)

    def test_render_text_sections(self):
        text = render_text(build_report(self.engine, now=self.now, days=7))
        for section in ('AI 调用', '单用户日成本', '任务', '配额拒绝', '今日配额用量'):
            self.assertIn(section, text)


if __name__ == '__main__':
    unittest.main()
