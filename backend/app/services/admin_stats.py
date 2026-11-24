"""Read models and aggregates for the operations console.

The console is intentionally read-mostly: aggregates are computed in SQL with
portable constructs so the same code runs on MySQL in production and SQLite in
tests. Times are stored as naive UTC; daily buckets are shifted to UTC+8 so the
"day" an operator sees matches the Beijing calendar.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Iterable, Optional

from sqlalchemy import func, or_, select, text, update
from sqlalchemy.orm import Session

from app.models import (
    AdminAuditLog,
    AiUsageLog,
    AuthSession,
    ChatMessage,
    ChatSession,
    Consent,
    DeletionJob,
    DietRecord,
    HealthScreening,
    Pet,
    QuotaDenial,
    ScreeningMedia,
    ScreeningSymptom,
    Task,
    UsageCounter,
    User,
    UserCredential,
    WeightRecord,
)
from app.services.triage import RulesBundle

LOCAL = timedelta(hours=8)
STATES = ('normal', 'observe', 'vet', 'urgent')
MAX_WINDOW_DAYS = 180


def local_day(column, db: Session):
    """SQL expression for the UTC+8 calendar day of a timestamp column."""
    if db.get_bind().dialect.name == 'mysql':
        return func.date(func.date_add(column, text('INTERVAL 8 HOUR')))
    return func.date(column, '+8 hours')


def _window(now: datetime, days: int) -> dict:
    days = max(1, min(int(days or 30), MAX_WINDOW_DAYS))
    today = (now + LOCAL).date()
    first = today - timedelta(days=days - 1)
    start = datetime.combine(first, time.min) - LOCAL
    labels = [(first + timedelta(days=index)).isoformat() for index in range(days)]
    return {'days': days, 'today': today, 'start': start, 'labels': labels}


def _round(value, places: int = 4):
    return None if value is None else round(float(value), places)


def _escape_like(value: str) -> str:
    return value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def _pattern(value: Optional[str]) -> Optional[str]:
    value = (value or '').strip()
    return f'%{_escape_like(value)}%' if value else None


def _daily_counts(db: Session, time_column, start: datetime,
                  *conditions) -> dict[str, int]:
    day = local_day(time_column, db)
    rows = db.execute(
        select(day, func.count()).where(time_column >= start, *conditions).group_by(day)
    ).all()
    return {str(day_value): int(count) for day_value, count in rows}


def _daily_cost(db: Session, start: datetime) -> dict[str, tuple[int, float]]:
    day = local_day(AiUsageLog.created_at, db)
    rows = db.execute(
        select(day, func.count(AiUsageLog.id), func.coalesce(func.sum(AiUsageLog.cost_est), 0))
        .where(AiUsageLog.created_at >= start).group_by(day)
    ).all()
    return {str(day_value): (int(calls), _round(cost or 0)) for day_value, calls, cost in rows}


def _active_users(db: Session, start: datetime) -> int:
    parts = [
        select(HealthScreening.user_id).where(HealthScreening.created_at >= start),
        select(ChatSession.user_id).join(ChatMessage, ChatMessage.session_id == ChatSession.id)
        .where(ChatMessage.created_at >= start),
        select(Pet.user_id).join(DietRecord, DietRecord.pet_id == Pet.id)
        .where(DietRecord.fed_at >= start),
        select(Pet.user_id).join(WeightRecord, WeightRecord.pet_id == Pet.id)
        .where(WeightRecord.measured_at >= start),
    ]
    combined = parts[0].union(*parts[1:]).subquery()
    return int(db.scalar(select(func.count()).select_from(combined)) or 0)


def _task_health(db: Session, start: datetime) -> list[dict]:
    tasks = db.scalars(select(Task).where(Task.created_at >= start)).all()
    grouped: dict[str, dict] = {}
    for task in tasks:
        row = grouped.setdefault(task.type, {
            'type': task.type, 'total': 0, 'succeeded': 0, 'failed': 0,
            'in_flight': 0, 'retried': 0,
        })
        row['total'] += 1
        if task.status == 'succeeded':
            row['succeeded'] += 1
        elif task.status == 'failed':
            row['failed'] += 1
        else:
            row['in_flight'] += 1
        if task.attempts > 1:
            row['retried'] += 1
    result = []
    for row in sorted(grouped.values(), key=lambda item: item['type']):
        finished = row['succeeded'] + row['failed']
        row['success_rate'] = round(row['succeeded'] / finished, 4) if finished else None
        result.append(row)
    return result


def _alerts(*, redline_rate: float, screenings: int, pending_deletions: int,
            quota_denials: int, tasks: list[dict]) -> list[dict]:
    alerts = []
    if screenings >= 10 and redline_rate >= 0.15:
        alerts.append({'level': 'warning', 'title': '红线命中率偏高',
                       'detail': f'窗口内红线率 {redline_rate:.1%}，建议抽查初筛规则与就医引导文案。'})
    failed = sum(row['failed'] for row in tasks)
    total = sum(row['total'] for row in tasks)
    if total and failed / total >= 0.1:
        alerts.append({'level': 'danger', 'title': '后台任务失败率偏高',
                       'detail': f'窗口内 {failed}/{total} 个任务失败，请在「AI 与成本」核对任务明细。'})
    if pending_deletions:
        alerts.append({'level': 'warning', 'title': '有待处理的注销申请',
                       'detail': f'{pending_deletions} 个账号处于 15 天冷静期，到期后会被物理清除。'})
    if quota_denials >= 20:
        alerts.append({'level': 'warning', 'title': '配额拒绝次数较多',
                       'detail': f'窗口内 {quota_denials} 次配额拒绝，可评估是否调整免费额度。'})
    return alerts


def overview(db: Session, *, now: datetime, days: int = 30) -> dict:
    window = _window(now, days)
    start, labels = window['start'], window['labels']

    users_total = int(db.scalar(select(func.count(User.id)).where(User.status != 'deleted')) or 0)
    users_suspended = int(db.scalar(select(func.count(User.id)).where(User.status == 'suspended')) or 0)
    users_new = int(db.scalar(select(func.count(User.id)).where(
        User.created_at >= start, User.status != 'deleted')) or 0)
    users_active = _active_users(db, start)
    pets_total = int(db.scalar(select(func.count(Pet.id)).where(Pet.status != 'deleted')) or 0)
    pets_new = int(db.scalar(select(func.count(Pet.id)).where(
        Pet.created_at >= start, Pet.status != 'deleted')) or 0)
    pending_deletions = int(db.scalar(select(func.count(DeletionJob.id))
                                      .where(DeletionJob.status == 'pending')) or 0)

    screenings = int(db.scalar(select(func.count(HealthScreening.id))
                               .where(HealthScreening.created_at >= start)) or 0)
    redline_hits = int(db.scalar(select(func.count(HealthScreening.id)).where(
        HealthScreening.created_at >= start, HealthScreening.redline_hit.is_(True))) or 0)
    redline_rate = round(redline_hits / screenings, 4) if screenings else 0.0
    chat_messages = int(db.scalar(select(func.count(ChatMessage.id))
                                  .where(ChatMessage.created_at >= start)) or 0)
    diet_records = int(db.scalar(select(func.count(DietRecord.id))
                                 .where(DietRecord.fed_at >= start)) or 0)
    weight_records = int(db.scalar(select(func.count(WeightRecord.id))
                                   .where(WeightRecord.measured_at >= start)) or 0)
    quota_denials = int(db.scalar(select(func.count(QuotaDenial.id))
                                  .where(QuotaDenial.created_at >= start)) or 0)
    ai_calls = int(db.scalar(select(func.count(AiUsageLog.id))
                             .where(AiUsageLog.created_at >= start)) or 0)
    ai_cost = _round(db.scalar(select(func.coalesce(func.sum(AiUsageLog.cost_est), 0))
                               .where(AiUsageLog.created_at >= start)) or 0)

    series = {
        'days': labels,
        'users_new': _daily_counts(db, User.created_at, start),
        'pets_new': _daily_counts(db, Pet.created_at, start),
        'screenings': _daily_counts(db, HealthScreening.created_at, start),
        'redline_hits': _daily_counts(db, HealthScreening.created_at, start,
                                      HealthScreening.redline_hit.is_(True)),
        'chat_messages': _daily_counts(db, ChatMessage.created_at, start),
        'diet_records': _daily_counts(db, DietRecord.fed_at, start),
        'weight_records': _daily_counts(db, WeightRecord.measured_at, start),
    }
    ai_daily = _daily_cost(db, start)
    series['ai_calls'] = {day: value[0] for day, value in ai_daily.items()}
    series['ai_cost'] = {day: value[1] for day, value in ai_daily.items()}
    for key in ('users_new', 'pets_new', 'screenings', 'redline_hits', 'chat_messages',
                'diet_records', 'weight_records', 'ai_calls', 'ai_cost'):
        series[key] = [series[key].get(day, 0) for day in labels]

    state_rows = db.execute(
        select(HealthScreening.state, func.count())
        .where(HealthScreening.created_at >= start)
        .group_by(HealthScreening.state)
    ).all()
    state_counts = {state: int(count) for state, count in state_rows}
    states = [{'state': state, 'count': state_counts.get(state, 0)} for state in STATES]
    states.extend({'state': state, 'count': count} for state, count in state_counts.items()
                  if state not in STATES)

    redlines = db.execute(
        select(HealthScreening.id, HealthScreening.pet_id, Pet.name, HealthScreening.user_id,
               User.nickname, HealthScreening.state, HealthScreening.created_at)
        .join(Pet, Pet.id == HealthScreening.pet_id)
        .join(User, User.id == HealthScreening.user_id)
        .where(HealthScreening.redline_hit.is_(True))
        .order_by(HealthScreening.created_at.desc(), HealthScreening.id.desc())
        .limit(8)
    ).all()

    ai_rows = db.execute(
        select(AiUsageLog.kind, AiUsageLog.model, func.count(AiUsageLog.id),
               func.coalesce(func.sum(AiUsageLog.tokens_in), 0),
               func.coalesce(func.sum(AiUsageLog.tokens_out), 0),
               func.coalesce(func.sum(AiUsageLog.cost_est), 0))
        .where(AiUsageLog.created_at >= start)
        .group_by(AiUsageLog.kind, AiUsageLog.model)
        .order_by(func.count(AiUsageLog.id).desc())
    ).all()

    quota_rows = db.execute(
        select(QuotaDenial.metric, func.count(QuotaDenial.id))
        .where(QuotaDenial.created_at >= start)
        .group_by(QuotaDenial.metric)
        .order_by(func.count(QuotaDenial.id).desc())
    ).all()

    tasks = _task_health(db, start)
    usage_rows = db.execute(
        select(UsageCounter.metric, func.sum(UsageCounter.count))
        .where(UsageCounter.day == now.date())
        .group_by(UsageCounter.metric)
        .order_by(UsageCounter.metric)
    ).all()

    return {
        'generated_at': now.isoformat() + 'Z',
        'window': {'days': window['days'],
                   'start': start.isoformat() + 'Z',
                   'end': now.isoformat() + 'Z',
                   'timezone': 'Asia/Shanghai'},
        'kpis': {
            'users_total': users_total, 'users_new': users_new,
            'users_active': users_active, 'users_suspended': users_suspended,
            'pets_total': pets_total, 'pets_new': pets_new,
            'screenings': screenings, 'redline_hits': redline_hits, 'redline_rate': redline_rate,
            'chat_messages': chat_messages, 'diet_records': diet_records,
            'weight_records': weight_records, 'quota_denials': quota_denials,
            'ai_calls': ai_calls, 'ai_cost': ai_cost,
            'pending_deletions': pending_deletions,
        },
        'series': series,
        'states': states,
        'redlines': [{
            'id': row[0], 'pet_id': row[1], 'pet_name': row[2], 'user_id': row[3],
            'owner_nickname': row[4], 'state': row[5],
            'created_at': row[6].isoformat() + 'Z',
        } for row in redlines],
        'ai_models': [{
            'kind': row[0], 'model': row[1], 'calls': int(row[2]),
            'tokens_in': int(row[3]), 'tokens_out': int(row[4]), 'cost_est': _round(row[5] or 0),
        } for row in ai_rows],
        'quota_metrics': [{'metric': row[0], 'count': int(row[1])} for row in quota_rows],
        'tasks': tasks,
        'quota_today': [{'metric': row[0], 'used': int(row[1] or 0)} for row in usage_rows],
        'alerts': _alerts(redline_rate=redline_rate, screenings=screenings,
                          pending_deletions=pending_deletions,
                          quota_denials=quota_denials, tasks=tasks),
    }


# ---------------------------------------------------------------------------
# Users


def user_email(db: Session, user_id: int) -> Optional[str]:
    return _user_emails(db, [user_id]).get(user_id)


def _user_emails(db: Session, ids: Iterable[int]) -> dict[int, str]:
    ids = list(ids)
    if not ids:
        return {}
    rows = db.execute(select(UserCredential.user_id, UserCredential.identifier).where(
        UserCredential.user_id.in_(ids), UserCredential.type == 'email')).all()
    return {user_id: identifier for user_id, identifier in rows}


def list_users(db: Session, *, query: str = '', status: str = 'all',
               page: int = 1, page_size: int = 20) -> dict:
    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or 20), 100))
    conditions = []
    pattern = _pattern(query)
    if pattern:
        email_owner = select(UserCredential.user_id).where(
            UserCredential.type == 'email',
            UserCredential.identifier.like(pattern, escape='\\'))
        conditions.append(or_(User.nickname.like(pattern, escape='\\'), User.id.in_(email_owner)))
    if status and status != 'all':
        conditions.append(User.status == status)
    base = select(User).where(*conditions)
    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    users = db.scalars(base.order_by(User.created_at.desc(), User.id.desc())
                       .offset((page - 1) * page_size).limit(page_size)).all()
    ids = [user.id for user in users]
    emails = _user_emails(db, ids)
    pet_counts = dict(db.execute(
        select(Pet.user_id, func.count(Pet.id)).where(
            Pet.user_id.in_(ids), Pet.status != 'deleted').group_by(Pet.user_id)).all()) if ids else {}
    pet_names: dict[int, list[str]] = {}
    if ids:
        for pet in db.scalars(select(Pet).where(Pet.user_id.in_(ids), Pet.status != 'deleted')
                              .order_by(Pet.id)).all():
            pet_names.setdefault(pet.user_id, []).append(pet.name)
    screening_counts = dict(db.execute(
        select(HealthScreening.user_id, func.count(HealthScreening.id)).where(
            HealthScreening.user_id.in_(ids)).group_by(HealthScreening.user_id)).all()) if ids else {}
    last_screening = dict(db.execute(
        select(HealthScreening.user_id, func.max(HealthScreening.created_at)).where(
            HealthScreening.user_id.in_(ids)).group_by(HealthScreening.user_id)).all()) if ids else {}
    return {
        'items': [{
            'id': user.id, 'nickname': user.nickname, 'email': emails.get(user.id),
            'status': user.status,
            'created_at': user.created_at.isoformat() + 'Z',
            'pet_count': int(pet_counts.get(user.id, 0)),
            'pet_names': pet_names.get(user.id, []),
            'screening_count': int(screening_counts.get(user.id, 0)),
            'last_screening_at': (last_screening[user.id].isoformat() + 'Z')
            if last_screening.get(user.id) else None,
        } for user in users],
        'total': total, 'page': page, 'page_size': page_size,
    }


def _count(db: Session, model, *conditions) -> int:
    return int(db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0)


def user_detail(db: Session, user_id: int) -> Optional[dict]:
    user = db.get(User, user_id)
    if user is None:
        return None
    email = _user_emails(db, [user.id]).get(user.id)
    pets = db.scalars(select(Pet).where(Pet.user_id == user.id)
                      .order_by(Pet.created_at.desc())).all()
    pet_rows = []
    for pet in pets:
        weight = db.scalar(select(WeightRecord).where(WeightRecord.pet_id == pet.id)
                           .order_by(WeightRecord.measured_at.desc(), WeightRecord.id.desc()).limit(1))
        pet_rows.append({
            'id': pet.id, 'name': pet.name, 'breed': pet.breed, 'sex': pet.sex,
            'birth_date': pet.birth_date.isoformat() if pet.birth_date else None,
            'body_type': pet.body_type, 'status': pet.status,
            'created_at': pet.created_at.isoformat() + 'Z',
            'weight_kg': float(weight.weight_kg) if weight else None,
            'weight_at': weight.measured_at.isoformat() + 'Z' if weight else None,
        })
    consents: dict[str, dict] = {}
    for consent in db.scalars(select(Consent).where(Consent.user_id == user.id)
                              .order_by(Consent.created_at.desc(), Consent.id.desc())).all():
        consents.setdefault(consent.type, {
            'version': consent.version, 'granted': consent.granted,
            'created_at': consent.created_at.isoformat() + 'Z',
        })
    screenings = db.scalars(select(HealthScreening).where(HealthScreening.user_id == user.id)
                            .order_by(HealthScreening.created_at.desc(),
                                      HealthScreening.id.desc()).limit(8)).all()
    deletion = db.scalar(select(DeletionJob).where(DeletionJob.user_id == user.id))
    ai_cost = db.scalar(select(func.coalesce(func.sum(AiUsageLog.cost_est), 0))
                        .where(AiUsageLog.user_id == user.id)) or 0
    return {
        'user': {
            'id': user.id, 'nickname': user.nickname, 'email': email, 'status': user.status,
            'created_at': user.created_at.isoformat() + 'Z',
            'deleted_at': user.deleted_at.isoformat() + 'Z' if user.deleted_at else None,
        },
        'pets': pet_rows,
        'consents': consents,
        'counts': {
            'screenings': _count(db, HealthScreening, HealthScreening.user_id == user.id),
            'redlines': _count(db, HealthScreening, HealthScreening.user_id == user.id,
                               HealthScreening.redline_hit.is_(True)),
            'chat_messages': int(db.scalar(
                select(func.count(ChatMessage.id)).join(ChatSession, ChatSession.id == ChatMessage.session_id)
                .where(ChatSession.user_id == user.id)) or 0),
            'diet_records': int(db.scalar(
                select(func.count(DietRecord.id)).join(Pet, Pet.id == DietRecord.pet_id)
                .where(Pet.user_id == user.id)) or 0),
            'weight_records': int(db.scalar(
                select(func.count(WeightRecord.id)).join(Pet, Pet.id == WeightRecord.pet_id)
                .where(Pet.user_id == user.id)) or 0),
            'ai_calls': _count(db, AiUsageLog, AiUsageLog.user_id == user.id),
            'ai_cost': _round(ai_cost or 0),
        },
        'recent_screenings': [{
            'id': item.id, 'pet_id': item.pet_id, 'state': item.state,
            'redline_hit': item.redline_hit,
            'created_at': item.created_at.isoformat() + 'Z',
        } for item in screenings],
        'deletion_job': None if deletion is None else {
            'status': deletion.status,
            'requested_at': deletion.requested_at.isoformat() + 'Z',
            'purge_after': deletion.purge_after.isoformat() + 'Z',
        },
    }


def set_user_status(db: Session, *, admin: User, user_id: int, status: str,
                    now: datetime) -> dict:
    if status not in ('active', 'suspended'):
        raise ValueError('只能设置为 active 或 suspended')
    target = db.get(User, user_id)
    if target is None:
        raise LookupError('user not found')
    if target.id == admin.id:
        raise PermissionError('不能变更当前登录的管理员账号')
    if target.status == 'deletion_pending':
        raise PermissionError('账号处于注销冷静期，不能变更状态')
    if target.status == 'deleted':
        raise PermissionError('账号已删除，不能变更状态')
    previous = target.status
    if previous != status:
        target.status = status
    if status == 'suspended':
        # A suspension is a lockout: retire every live refresh session so a
        # later reactivation cannot silently resume an old device session.
        db.execute(update(AuthSession).where(
            AuthSession.user_id == target.id, AuthSession.revoked_at.is_(None),
        ).values(revoked_at=now))
    record_audit(db, admin=admin, action='user.status', target_type='user',
                 target_id=target.id, detail={'from': previous, 'to': status}, now=now)
    db.commit()
    return {'id': target.id, 'status': target.status}


def record_audit(db: Session, *, admin: User, action: str, target_type: str,
                 target_id: Optional[int], detail: Optional[dict], now: datetime) -> None:
    db.add(AdminAuditLog(
        admin_user_id=admin.id,
        admin_email=user_email(db, admin.id),
        admin_nickname=admin.nickname,
        action=action, target_type=target_type,
        target_id=target_id, detail=detail, created_at=now,
    ))


# ---------------------------------------------------------------------------
# Pets


def list_pets(db: Session, *, query: str = '', status: str = 'all',
              page: int = 1, page_size: int = 20) -> dict:
    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or 20), 100))
    owner_email = (select(UserCredential.identifier).where(
        UserCredential.user_id == Pet.user_id, UserCredential.type == 'email').limit(1)).scalar_subquery()
    latest_weight = (select(WeightRecord.weight_kg).where(WeightRecord.pet_id == Pet.id)
                     .order_by(WeightRecord.measured_at.desc(), WeightRecord.id.desc())
                     .limit(1)).scalar_subquery()
    screening_count = (select(func.count(HealthScreening.id))
                       .where(HealthScreening.pet_id == Pet.id)).scalar_subquery()
    base = select(Pet, User.nickname, owner_email, latest_weight, screening_count).join(
        User, User.id == Pet.user_id)
    xss: list = []
    pattern = _pattern(query)
    if pattern:
        xss.append(or_(Pet.name.like(pattern, escape='\\'),
                       User.nickname.like(pattern, escape='\\'),
                       owner_email.like(pattern, escape='\\')))
    if status and status != 'all':
        xss.append(Pet.status == status)
    base = base.where(*xss)
    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = db.execute(base.order_by(Pet.created_at.desc(), Pet.id.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    items = []
    for pet, nickname, email, weight, screenings in rows:
        items.append({
            'id': pet.id, 'name': pet.name, 'user_id': pet.user_id,
            'owner_nickname': nickname, 'owner_email': email,
            'breed': pet.breed, 'sex': pet.sex, 'body_type': pet.body_type,
            'birth_date': pet.birth_date.isoformat() if pet.birth_date else None,
            'status': pet.status, 'created_at': pet.created_at.isoformat() + 'Z',
            'weight_kg': float(weight) if weight is not None else None,
            'screening_count': int(screenings or 0),
        })
    return {'items': items, 'total': total, 'page': page, 'page_size': page_size}


# ---------------------------------------------------------------------------
# Screenings


def _screening_labels(bundle: Optional[RulesBundle]) -> dict[str, str]:
    if bundle is None:
        return {}
    return {entry['code']: entry['label'] for entry in bundle.symptoms['symptoms']}


def _redline_labels(bundle: Optional[RulesBundle]) -> dict[str, str]:
    if bundle is None:
        return {}
    labels = {}
    for entry in bundle.redlines['redlines']:
        labels[entry['code']] = entry['label']
        for option in entry.get('options', []):
            labels[option['code']] = option['label']
    return labels


def list_screenings(db: Session, *, query: str = '', state: str = 'all', redline: str = 'all',
                    page: int = 1, page_size: int = 20,
                    bundle: Optional[RulesBundle] = None) -> dict:
    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or 20), 100))
    labels = _screening_labels(bundle)
    redline_labels = _redline_labels(bundle)
    owner_email = (select(UserCredential.identifier).where(
        UserCredential.user_id == HealthScreening.user_id,
        UserCredential.type == 'email').limit(1)).scalar_subquery()
    base = select(HealthScreening, Pet.name, User.nickname, owner_email).join(
        Pet, Pet.id == HealthScreening.pet_id).join(User, User.id == HealthScreening.user_id)
    xss: list = []
    pattern = _pattern(query)
    if pattern:
        xss.append(or_(Pet.name.like(pattern, escape='\\'),
                       User.nickname.like(pattern, escape='\\'),
                       owner_email.like(pattern, escape='\\')))
    if state and state != 'all':
        xss.append(HealthScreening.state == state)
    if redline == 'only':
        xss.append(HealthScreening.redline_hit.is_(True))
    elif redline == 'none':
        xss.append(HealthScreening.redline_hit.is_(False))
    base = base.where(*xss)
    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = db.execute(base.order_by(HealthScreening.created_at.desc(), HealthScreening.id.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    items = []
    for screening, pet_name, nickname, email in rows:
        triage = screening.triage_json or {}
        grades = triage.get('symptom_grades') or {}
        items.append({
            'id': screening.id, 'pet_id': screening.pet_id, 'pet_name': pet_name,
            'user_id': screening.user_id, 'owner_nickname': nickname, 'owner_email': email,
            'state': screening.state, 'redline_hit': screening.redline_hit,
            'spirit': screening.spirit, 'appetite': screening.appetite,
            'rules_version': screening.rules_version,
            'symptoms': [{'code': code, 'label': labels.get(code, code), 'grade': grade}
                         for code, grade in grades.items()],
            'redlines': [{'code': code, 'label': redline_labels.get(code, code)}
                         for code in triage.get('redlines') or []],
            'created_at': screening.created_at.isoformat() + 'Z',
        })
    return {'items': items, 'total': total, 'page': page, 'page_size': page_size}


def screening_detail(db: Session, screening_id: int,
                     bundle: Optional[RulesBundle] = None) -> Optional[dict]:
    screening = db.get(HealthScreening, screening_id)
    if screening is None:
        return None
    pet = db.get(Pet, screening.pet_id)
    user = db.get(User, screening.user_id)
    labels = _screening_labels(bundle)
    redline_labels = _redline_labels(bundle)
    triage = screening.triage_json or {}
    symptoms = db.scalars(select(ScreeningSymptom).where(
        ScreeningSymptom.screening_id == screening.id)).all()
    media_count = _count(db, ScreeningMedia, ScreeningMedia.screening_id == screening.id)
    return {
        'id': screening.id,
        'state': screening.state, 'redline_hit': screening.redline_hit,
        'spirit': screening.spirit, 'appetite': screening.appetite,
        'rules_version': screening.rules_version,
        'created_at': screening.created_at.isoformat() + 'Z',
        'pet': None if pet is None else {
            'id': pet.id, 'name': pet.name, 'breed': pet.breed, 'sex': pet.sex,
            'birth_date': pet.birth_date.isoformat() if pet.birth_date else None,
            'body_type': pet.body_type,
        },
        'owner': None if user is None else {
            'id': user.id, 'nickname': user.nickname,
            'email': _user_emails(db, [user.id]).get(user.id),
        },
        'symptoms': [{
            'code': item.symptom_code, 'label': labels.get(item.symptom_code, item.symptom_code),
            'grade': (triage.get('symptom_grades') or {}).get(item.symptom_code),
            'duration': item.duration, 'frequency': item.frequency,
            'severe': item.severe, 'notes': item.notes,
        } for item in symptoms],
        'redlines': [{'code': code, 'label': redline_labels.get(code, code)}
                     for code in triage.get('redlines') or []],
        'symptom_grades': triage.get('symptom_grades') or {},
        'advice': screening.advice_json,
        'llm_advice': screening.llm_advice,
        'media_count': media_count,
    }


# ---------------------------------------------------------------------------
# AI / cost / audit


def ai_usage(db: Session, *, now: datetime, days: int = 30) -> dict:
    window = _window(now, days)
    start, labels = window['start'], window['labels']
    rows = db.execute(
        select(AiUsageLog.kind, AiUsageLog.model, func.count(AiUsageLog.id),
               func.coalesce(func.sum(AiUsageLog.tokens_in), 0),
               func.coalesce(func.sum(AiUsageLog.tokens_out), 0),
               func.coalesce(func.sum(AiUsageLog.media_seconds), 0),
               func.coalesce(func.sum(AiUsageLog.cost_est), 0))
        .where(AiUsageLog.created_at >= start)
        .group_by(AiUsageLog.kind, AiUsageLog.model)
        .order_by(func.count(AiUsageLog.id).desc())
    ).all()
    models = [{
        'kind': row[0], 'model': row[1], 'calls': int(row[2]),
        'tokens_in': int(row[3]), 'tokens_out': int(row[4]),
        'media_seconds': _round(row[5] or 0, 2), 'cost_est': _round(row[6] or 0),
    } for row in rows]
    totals = {
        'calls': sum(row['calls'] for row in models),
        'tokens_in': sum(row['tokens_in'] for row in models),
        'tokens_out': sum(row['tokens_out'] for row in models),
        'media_seconds': _round(sum(row['media_seconds'] or 0 for row in models), 2),
        'cost_est': _round(sum(row['cost_est'] or 0 for row in models)),
    }
    daily = _daily_cost(db, start)

    per_user_rows = db.execute(
        select(AiUsageLog.user_id, func.count(AiUsageLog.id),
               func.coalesce(func.sum(AiUsageLog.cost_est), 0))
        .where(AiUsageLog.created_at >= start)
        .group_by(AiUsageLog.user_id)
        .order_by(func.coalesce(func.sum(AiUsageLog.cost_est), 0).desc())
        .limit(10)
    ).all()
    emails = _user_emails(db, [row[0] for row in per_user_rows if row[0] is not None])
    per_user = []
    for row in per_user_rows:
        user = db.get(User, row[0]) if row[0] is not None else None
        per_user.append({
            'user_id': row[0],
            'nickname': user.nickname if user is not None else '已注销',
            'email': emails.get(row[0]),
            'calls': int(row[1]), 'cost_est': _round(row[2] or 0),
        })

    denial_rows = db.execute(
        select(QuotaDenial.metric, QuotaDenial.day, func.count(QuotaDenial.id))
        .where(QuotaDenial.created_at >= start)
        .group_by(QuotaDenial.metric, QuotaDenial.day)
        .order_by(QuotaDenial.day.desc(), QuotaDenial.metric)
    ).all()
    return {
        'generated_at': now.isoformat() + 'Z',
        'window': {'days': window['days'], 'start': start.isoformat() + 'Z',
                   'end': now.isoformat() + 'Z'},
        'ai': {
            'totals': totals, 'models': models,
            'days': labels,
            'calls': [daily.get(day, (0, 0))[0] for day in labels],
            'cost': [daily.get(day, (0, 0))[1] for day in labels],
        },
        'per_user': per_user,
        'tasks': _task_health(db, start),
        'quota_denials': [{'metric': metric, 'day': str(day), 'count': int(count)}
                          for metric, day, count in denial_rows],
    }


def audit_log(db: Session, *, page: int = 1, page_size: int = 20) -> dict:
    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or 20), 100))
    total = _count(db, AdminAuditLog)
    rows = db.scalars(
        select(AdminAuditLog)
        .order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        'items': [{
            'id': row.id, 'admin_user_id': row.admin_user_id,
            'admin_nickname': row.admin_nickname, 'admin_email': row.admin_email,
            'action': row.action, 'target_type': row.target_type,
            'target_id': row.target_id, 'detail': row.detail,
            'created_at': row.created_at.isoformat() + 'Z',
        } for row in rows],
        'total': total, 'page': page, 'page_size': page_size,
    }
