"""T17 F11-1: per-user daily quotas (DB-atomic, env-hot-adjustable, server-day).

The usage_counters table is the transactional source of truth (ARCH deviation:
no Redis dependency); increments share the business write's transaction, so a
failed request never burns quota. Red-line screenings are exempt (F11-1).
"""
import os
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models import UsageCounter

QUOTA_DEFAULTS = {'screening': 10, 'avatar_gen': 3, 'chat_msg': 50}
QUOTA_ENV = {'screening': 'QUOTA_SCREENING', 'avatar_gen': 'QUOTA_AVATAR', 'chat_msg': 'QUOTA_CHAT'}


class QuotaExceeded(Exception):
    def __init__(self, metric: str, used: int, limit: int):
        super().__init__(f'quota exceeded: {metric}')
        self.metric, self.used, self.limit = metric, used, limit


def quota_limits(env: Optional[dict] = None) -> dict:
    env = os.environ if env is None else env
    limits = {}
    for metric, default in QUOTA_DEFAULTS.items():
        try:
            value = int(env.get(QUOTA_ENV[metric], ''))
        except (TypeError, ValueError):
            value = default
        limits[metric] = value if value > 0 else default
    return limits


def consume_quota(db: Session, user_id: int, metric: str, *, now: datetime, env: Optional[dict] = None) -> int:
    """Atomically increment today's counter; raise QuotaExceeded past the limit.

    The caller rolls back on QuotaExceeded so the increment is undone.
    """
    limit = quota_limits(env)[metric]
    values = dict(user_id=user_id, day=now.date(), metric=metric, count=1)
    if db.bind.dialect.name == 'sqlite':
        stmt = sqlite_insert(UsageCounter).values(**values).on_conflict_do_update(
            index_elements=['user_id', 'day', 'metric'], set_={'count': UsageCounter.count + 1})
    else:
        stmt = mysql_insert(UsageCounter).values(**values).on_duplicate_key_update(count=UsageCounter.count + 1)
    db.execute(stmt)
    db.flush()
    count = db.scalar(select(UsageCounter.count).where(UsageCounter.user_id == user_id,
                                                       UsageCounter.day == now.date(),
                                                       UsageCounter.metric == metric))
    if count > limit:
        raise QuotaExceeded(metric, count, limit)
    return count


def quota_snapshot(db: Session, user_id: int, *, now: datetime, env: Optional[dict] = None) -> dict:
    limits = quota_limits(env)
    rows = db.execute(select(UsageCounter.metric, UsageCounter.count).where(
        UsageCounter.user_id == user_id, UsageCounter.day == now.date())).all()
    used = {metric: count for metric, count in rows}
    return {'day': now.date().isoformat(),
            'metrics': {metric: {'used': used.get(metric, 0), 'limit': limit} for metric, limit in limits.items()}}


def quota_gate(db: Session, user_id: int, metric: str, *, now: Optional[datetime] = None) -> int:
    from app.auth import APIError, utcnow
    try:
        return consume_quota(db, user_id, metric, now=now or utcnow())
    except QuotaExceeded as exc:
        raise APIError(429, 'QUOTA_EXCEEDED', '今日次数已用完，明日再试',
                       {'metric': exc.metric, 'used': exc.used, 'limit': exc.limit}) from exc
