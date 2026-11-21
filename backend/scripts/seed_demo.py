'''Seed a local demo account and sample data.

Usage (from backend/, after 'alembic upgrade head'):

    python -m scripts.seed_demo

The script is intentionally idempotent: rerunning it reuses the demo user and
pet, adds any missing sample rows, and resets the demo password to the value
passed on the command line. It must only be used for local development.
'''
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from typing import Any, Dict

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import utcnow
from app.models import (
    ChatMessage,
    ChatSession,
    DietRecord,
    HealthScreening,
    Pet,
    User,
    UserCredential,
    WeightRecord,
)
from app.services.advice import template_advice
from app.services.consents import grant_consent, latest_consents
from app.services.feeding import kcal_estimate
from app.services.identity import (
    create_email_account,
    normalize_email,
    password_hasher,
    verify_email,
)
from app.services.pets import PetInput, create_pet
from app.services.triage import triage, validate_answers

DEMO_EMAIL = 'demo@rongxing.app'
DEMO_PASSWORD = 'Rongxing2026'
DEMO_NICKNAME = '团团的铲屎官'
DEMO_PET_NAME = '团团'


def _verified_credential(session: Session, email: str, password: str, now: datetime) -> User:
    '''Create or refresh the demo credential, returning its active user.'''
    credential = session.scalar(select(UserCredential).where(
        UserCredential.type == 'email', UserCredential.identifier == email,
    ))
    if credential is None:
        token = create_email_account(session, email, password, now)
        verify_email(session, token, now)
        credential = session.scalar(select(UserCredential).where(
            UserCredential.type == 'email', UserCredential.identifier == email,
        ))
        if credential is None:
            raise RuntimeError('demo credential was not created')
    else:
        credential.secret_hash = password_hasher.hash(password)
        credential.verified_at = credential.verified_at or now
        credential.verification_hash = None
        credential.verification_expires_at = None
    user = session.get(User, credential.user_id)
    if user is None:
        raise RuntimeError('demo credential points to a missing user')
    if user.status != 'active':
        raise RuntimeError(f'demo user is {user.status!r}, expected active')
    if user.nickname in ('', '猫咪主人'):
        user.nickname = DEMO_NICKNAME
    return user


def _ensure_consents(session: Session, user: User, settings: Settings) -> None:
    versions = settings.policy_versions
    if not all(versions.values()):
        raise RuntimeError('PRIVACY_VERSION and TERMS_VERSION must be configured in backend/.env')
    current = latest_consents(session, user.id)
    for kind, version in versions.items():
        record = current.get(kind)
        if record is None or not record.granted or record.version != version:
            grant_consent(session, user.id, kind, version, True)
    if 'training' not in current:
        grant_consent(session, user.id, 'training', versions['privacy'], False)


def _ensure_pet(session: Session, user: User) -> Pet:
    pet = session.scalar(select(Pet).where(
        Pet.user_id == user.id, Pet.name == DEMO_PET_NAME, Pet.status == 'active',
    ))
    if pet is not None:
        return pet
    return create_pet(session, user.id, PetInput(
        name=DEMO_PET_NAME,
        species='cat',
        breed='中华田园猫',
        sex='female',
        birth_date=date(2023, 5, 20),
        neutered=True,
        body_type='standard',
    ))


def _ensure_weights(session: Session, pet: Pet, now: datetime) -> int:
    if session.scalar(select(WeightRecord.id).where(WeightRecord.pet_id == pet.id).limit(1)) is not None:
        return 0
    # A gentle, healthy 90-day trend for charts and the feeding reference.
    samples = ((56, 4.00), (35, 4.05), (14, 4.10), (3, 4.15), (0, 4.20))
    for days, value in samples:
        session.add(WeightRecord(pet_id=pet.id, weight_kg=value,
                                 measured_at=now - timedelta(days=days)))
    return len(samples)


def _ensure_diet(session: Session, pet: Pet, settings: Settings, now: datetime) -> int:
    if session.scalar(select(DietRecord.id).where(DietRecord.pet_id == pet.id).limit(1)) is not None:
        return 0
    config = settings.feeding_config
    if config is None:
        raise RuntimeError('rules/feeding.yaml is required to seed diet records')
    meals = (
        (8, 'dry', '渴望六种鱼', 35, '早餐'),
        (5, 'wet', '鸡肉主食罐头', 40, '午餐'),
        (2, 'snack', '冻干鸡胸', 8, '下午加餐'),
        (26, 'dry', '渴望六种鱼', 45, '昨天晚餐'),
    )
    for hours_ago, food_type, food_name, amount, note in meals:
        session.add(DietRecord(
            pet_id=pet.id, food_type=food_type, food_name=food_name,
            amount_g=amount, kcal_est=kcal_estimate(config, food_type, amount),
            fed_at=now - timedelta(hours=hours_ago), note=note,
        ))
    return len(meals)


def _ensure_screening(session: Session, pet: Pet, user: User, settings: Settings,
                      now: datetime) -> int:
    if session.scalar(select(HealthScreening.id).where(HealthScreening.pet_id == pet.id).limit(1)) is not None:
        return 0
    bundle = settings.triage_rules
    templates = settings.advice_templates
    if bundle is None or templates is None:
        raise RuntimeError('rules/symptoms.yaml, redlines.yaml and advice_templates.yaml are required')
    answers = {'spirit': 'normal', 'appetite': 'normal', 'symptoms': [], 'redline_options': []}
    errors = validate_answers(bundle, answers)
    if errors:
        raise RuntimeError(f'seed screening answers are invalid: {errors}')
    result = triage(bundle, answers)
    session.add(HealthScreening(
        pet_id=pet.id, user_id=user.id, state=result['state'],
        redline_hit=result['redline_hit'], spirit='normal', appetite='normal',
        triage_json={'redlines': result['redlines'], 'symptom_grades': result['symptom_grades']},
        rules_version=result['rules_version'],
        advice_json=template_advice(templates, result['state']),
        created_at=now - timedelta(hours=3),
    ))
    return 1


def _ensure_chat(session: Session, pet: Pet, user: User, now: datetime) -> int:
    chat = session.scalar(select(ChatSession).where(ChatSession.pet_id == pet.id))
    if chat is None:
        chat = ChatSession(pet_id=pet.id, user_id=user.id)
        session.add(chat)
        session.flush()
    if session.scalar(select(ChatMessage.id).where(ChatMessage.session_id == chat.id).limit(1)) is not None:
        return 0
    messages = (
        ('user', '今天团团的便便正常吗？', now - timedelta(hours=2)),
        ('pet', '喵～今天的便便成形，精神也很好。你摸摸我，我就更开心啦。', now - timedelta(hours=2) + timedelta(minutes=1)),
        ('user', '那就好，今晚给你加一点冻干。', now - timedelta(hours=1)),
        ('pet', '好耶！不过要记得按体重控制份量哦，我陪你一起健康。', now - timedelta(hours=1) + timedelta(minutes=1)),
    )
    for role, text, created_at in messages:
        session.add(ChatMessage(session_id=chat.id, role=role, kind='text',
                                content=text, created_at=created_at))
    return len(messages)


def seed_demo(session: Session, settings: Settings, *, email: str = DEMO_EMAIL,
              password: str = DEMO_PASSWORD) -> Dict[str, Any]:
    '''Create or complete the demo account; caller owns the transaction.'''
    email = normalize_email(email)
    now = utcnow()
    user = _verified_credential(session, email, password, now)
    _ensure_consents(session, user, settings)
    pet = _ensure_pet(session, user)
    weights = _ensure_weights(session, pet, now)
    diet = _ensure_diet(session, pet, settings, now)
    screening = _ensure_screening(session, pet, user, settings, now)
    chat = _ensure_chat(session, pet, user, now)
    session.flush()
    return {
        'email': email,
        'user_id': user.id,
        'pet_id': pet.id,
        'pet_name': pet.name,
        'created': {'weights': weights, 'diet': diet, 'screenings': screening, 'chat_messages': chat},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='创建本地演示账号与示例数据（仅限开发环境）')
    parser.add_argument('--email', default=DEMO_EMAIL, help='演示账号邮箱')
    parser.add_argument('--password', default=DEMO_PASSWORD,
                        help='演示账号密码（8–128 位，含字母和数字）')
    parser.add_argument('--json', action='store_true', help='输出 JSON')
    args = parser.parse_args()

    settings = Settings.from_env()
    engine = create_engine(settings.database_url, pool_pre_ping=True, pool_recycle=1800)
    try:
        with Session(engine) as session:
            summary = seed_demo(session, settings, email=args.email, password=args.password)
            session.commit()
    finally:
        engine.dispose()

    if args.json:
        import json
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print('演示数据已就绪：')
        print(f"  邮箱：{summary['email']}")
        print(f"  密码：{args.password}")
        print(f"  猫猫：{summary['pet_name']}（pet_id={summary['pet_id']}）")
        print(f"  本次新增：{summary['created']}")


if __name__ == '__main__':
    main()
