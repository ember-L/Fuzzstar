"""T08 健康分聚合（FRD F04 / 附录 D）：纯规则、读时衰减、可追溯明细。

LLM 不参与打分。事件扣分以落库快照为准（score_delta 随规则版本存档），
observe 事件 72h 无复查在读时衰减为 0 并保留明细；vet/urgent 不自动衰减。
"""

from datetime import datetime, timedelta

SEVERITY_ORDER = {'normal': 0, 'observe': 1, 'vet': 2, 'urgent': 3}


def compute_health(events: list[dict], *, has_screening: bool, now: datetime, decay_hours: int) -> dict:
    """events 为未排序的健康事件快照；返回 {state, score, deductions}。

    有效事件 = active 且未 resolved 且未衰减；状态取有效事件最高档。
    明细列出全部未解决事件（含已衰减项，effective_delta=0）。
    无初筛且无事件 → score=None（UI「未评估 --」），禁止默认 100。
    """
    deductions = []
    effective_total = 0
    state = 'normal'
    decay_window = timedelta(hours=decay_hours)
    for event in events:
        if not event['active'] or event['resolved_at'] is not None:
            continue
        decayed = event['severity'] == 'observe' and now - event['created_at'] >= decay_window
        effective_delta = 0 if decayed else event['score_delta']
        effective_total += effective_delta
        if not decayed and SEVERITY_ORDER[event['severity']] > SEVERITY_ORDER[state]:
            state = event['severity']
        deductions.append(
            {
                'id': event['id'],
                'source': event['source'],
                'source_id': event['source_id'],
                'severity': event['severity'],
                'symptoms': event.get('symptoms', []),
                'score_delta': event['score_delta'],
                'effective_delta': effective_delta,
                'decayed': decayed,
                'created_at': event['created_at'],
                'rules_version': event.get('rules_version'),
            }
        )
    score = None if not has_screening and not events else max(0, 100 - effective_total)
    return {'state': state, 'score': score, 'deductions': deductions}
