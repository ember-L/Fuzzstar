"""T18 read-only ops report: AI calls/cost, task health, quota denials/usage.

Usage: DATABASE_URL=... python -m scripts.ops_report [--days 7] [--json]
Aggregates only; never prints emails, tokens or other personal identifiers.
"""
import argparse
import json
import math
import os
from datetime import timedelta

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.auth import utcnow
from app.models import AiUsageLog, QuotaDenial, Task, UsageCounter


def _p95(values):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def _round(value, places=4):
    return None if value is None else round(float(value), places)


def build_report(engine, *, now, days=7):
    since = now - timedelta(days=days)
    with Session(engine) as db:
        ai_rows = db.execute(
            select(AiUsageLog.kind, AiUsageLog.model, func.count(AiUsageLog.id),
                   func.coalesce(func.sum(AiUsageLog.tokens_in), 0),
                   func.coalesce(func.sum(AiUsageLog.tokens_out), 0),
                   func.coalesce(func.sum(AiUsageLog.media_seconds), 0.0),
                   func.coalesce(func.sum(AiUsageLog.cost_est), 0))
            .where(AiUsageLog.created_at >= since)
            .group_by(AiUsageLog.kind, AiUsageLog.model)
            .order_by(AiUsageLog.kind, AiUsageLog.model)).all()
        ai = [{'kind': kind, 'model': model, 'calls': calls, 'tokens_in': int(tokens_in),
               'tokens_out': int(tokens_out), 'media_seconds': _round(seconds, 2), 'cost_est': _round(cost)}
              for kind, model, calls, tokens_in, tokens_out, seconds, cost in ai_rows]
        totals = {'calls': sum(row['calls'] for row in ai),
                  'tokens_in': sum(row['tokens_in'] for row in ai),
                  'tokens_out': sum(row['tokens_out'] for row in ai),
                  'media_seconds': _round(sum(row['media_seconds'] or 0 for row in ai), 2),
                  'cost_est': _round(sum(row['cost_est'] or 0 for row in ai))}
        daily_rows = db.execute(
            select(func.date(AiUsageLog.created_at), func.count(AiUsageLog.id),
                   func.coalesce(func.sum(AiUsageLog.cost_est), 0))
            .where(AiUsageLog.created_at >= since)
            .group_by(func.date(AiUsageLog.created_at))
            .order_by(func.date(AiUsageLog.created_at))).all()
        daily = [{'day': str(day), 'calls': calls, 'cost_est': _round(cost)} for day, calls, cost in daily_rows]
        user_rows = db.execute(
            select(AiUsageLog.user_id, func.count(AiUsageLog.id), func.coalesce(func.sum(AiUsageLog.cost_est), 0))
            .where(AiUsageLog.created_at >= since)
            .group_by(AiUsageLog.user_id)).all()
        per_user = sorted(({'user_id': user_id, 'calls': calls, 'cost_est': _round(cost)}
                           for user_id, calls, cost in user_rows),
                          key=lambda row: row['cost_est'] or 0, reverse=True)[:10]
        tasks = db.scalars(select(Task).where(Task.created_at >= since)).all()
        by_type = {}
        for task in tasks:
            row = by_type.setdefault(task.type, {'type': task.type, 'total': 0, 'succeeded': 0, 'failed': 0,
                                                 'in_flight': 0, 'retried': 0, 'durations': []})
            row['total'] += 1
            if task.status == 'succeeded':
                row['succeeded'] += 1
            elif task.status == 'failed':
                row['failed'] += 1
            else:
                row['in_flight'] += 1
            if task.attempts > 1:
                row['retried'] += 1
            if task.status in ('succeeded', 'failed'):
                row['durations'].append((task.updated_at - task.created_at).total_seconds())
        task_rows = []
        for row in sorted(by_type.values(), key=lambda item: item['type']):
            durations = row.pop('durations')
            row['avg_duration_s'] = _round(sum(durations) / len(durations), 2) if durations else None
            row['p95_duration_s'] = _round(_p95(durations), 2)
            task_rows.append(row)
        denial_rows = db.execute(
            select(QuotaDenial.metric, QuotaDenial.day, func.count(QuotaDenial.id))
            .where(QuotaDenial.created_at >= since)
            .group_by(QuotaDenial.metric, QuotaDenial.day)
            .order_by(QuotaDenial.day.desc(), QuotaDenial.metric)).all()
        denials = [{'metric': metric, 'day': str(day), 'count': count} for metric, day, count in denial_rows]
        usage_rows = db.execute(
            select(UsageCounter.metric, func.sum(UsageCounter.count))
            .where(UsageCounter.day == now.date())
            .group_by(UsageCounter.metric).order_by(UsageCounter.metric)).all()
        usage = [{'metric': metric, 'used': int(used)} for metric, used in usage_rows]
    return {'window_days': days, 'generated_at': now.isoformat(),
            'ai_calls': {'rows': ai, 'totals': totals}, 'daily_cost': daily, 'per_user_cost': per_user,
            'tasks': task_rows, 'quota_denials': denials, 'quota_usage_today': usage}


def render_text(report):
    lines = [f"绒星运营报表（近 {report['window_days']} 天，生成于 {report['generated_at']}）", '']
    totals = report['ai_calls']['totals']
    lines.append(f"AI 调用合计：{totals['calls']} 次，tokens {totals['tokens_in']}/{totals['tokens_out']}，"
                 f"媒体 {totals['media_seconds']}s，估算成本 {totals['cost_est']}")
    for row in report['ai_calls']['rows']:
        lines.append(f"  {row['kind']}/{row['model']}：{row['calls']} 次，tokens {row['tokens_in']}/{row['tokens_out']}，"
                     f"媒体 {row['media_seconds']}s，成本 {row['cost_est']}")
    lines.append('')
    lines.append('每日 AI 成本：')
    for row in report['daily_cost']:
        lines.append(f"  {row['day']}：{row['calls']} 次，成本 {row['cost_est']}")
    lines.append('')
    lines.append('单用户日成本 Top10（窗口内合计，user_id 为内部编号，NULL=已注销匿名）：')
    for row in report['per_user_cost']:
        lines.append(f"  user {row['user_id']}：{row['calls']} 次，成本 {row['cost_est']}")
    lines.append('')
    lines.append('任务健康（时长=终态 updated_at-created_at）：')
    for row in report['tasks']:
        lines.append(f"  {row['type']}：总 {row['total']} 成功 {row['succeeded']} 失败 {row['failed']} "
                     f"进行中 {row['in_flight']} 重试 {row['retried']} "
                     f"平均 {row['avg_duration_s']}s p95 {row['p95_duration_s']}s")
    lines.append('')
    lines.append('配额拒绝：')
    for row in report['quota_denials']:
        lines.append(f"  {row['day']} {row['metric']}：{row['count']} 次")
    if not report['quota_denials']:
        lines.append('  （无）')
    lines.append('')
    lines.append('今日配额用量（全体用户合计）：')
    for row in report['quota_usage_today']:
        lines.append(f"  {row['metric']}：{row['used']}")
    if not report['quota_usage_today']:
        lines.append('  （无）')
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='绒星运营报表（只读）')
    parser.add_argument('--days', type=int, default=7)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    url = os.environ.get('DATABASE_URL')
    if not url:
        raise SystemExit('DATABASE_URL is required')
    engine = create_engine(url, hide_parameters=True)
    try:
        report = build_report(engine, now=utcnow(), days=args.days)
    finally:
        engine.dispose()
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else render_text(report))


if __name__ == '__main__':
    main()
