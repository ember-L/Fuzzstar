"""One-command local preview of the operations console.

This is a developer/demo entry point, not production. It creates a local SQLite
database, seeds a demo account plus sample cats/screenings/AI usage, then serves
the real FastAPI app (including ``/admin``) on 127.0.0.1.

Usage (from backend/):

    python -m scripts.run_admin_demo
    python -m scripts.run_admin_demo --reset --port 8000
"""
from __future__ import annotations

import argparse
import os
from datetime import timedelta
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEMO_DB = Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'RongXing' / 'admin_demo.db'
DEMO_EMAIL = 'demo@rongxing.app'
DEMO_PASSWORD = 'Rongxing2026'
DEMO_PET_OWNERS = [
    ('林小满', 'owner1@example.com'),
    ('陈一川', 'owner2@example.com'),
    ('周栀', 'owner3@example.com'),
    ('许星野', 'owner4@example.com'),
    ('苏禾', 'owner5@example.com'),
    ('顾明', 'owner6@example.com'),
    ('沈青', 'owner7@example.com'),
    ('叶晚', 'owner8@example.com'),
]


def configure_env(db_path: Path) -> None:
    """Pin the process to an isolated demo database and demo administrator."""
    os.environ['DATABASE_URL'] = f'sqlite:///{db_path.as_posix()}'
    os.environ['ADMIN_EMAILS'] = DEMO_EMAIL
    os.environ.setdefault('JWT_SECRET', 'rongxing-admin-demo-jwt-secret-32-bytes-long')
    os.environ['PRIVACY_VERSION'] = 'p1'
    os.environ['TERMS_VERSION'] = 't1'
    os.environ['PRIVACY_URL'] = 'https://example.com/privacy'
    os.environ['TERMS_URL'] = 'https://example.com/terms'
    os.environ.setdefault('RULES_DIR', str(BACKEND_ROOT / 'rules'))
    os.environ.setdefault('PLACEHOLDER_DIR', str(BACKEND_ROOT / 'assets' / 'placeholders'))


def seed_demo_data() -> None:
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.core.config import Settings
    from app.core.security import utcnow
    from app.models import (
        AiUsageLog, Base, ChatMessage, ChatSession, DeletionJob, DietRecord,
        HealthScreening, Pet, QuotaDenial, ScreeningSymptom, Task, UsageCounter,
        User, UserCredential, WeightRecord,
    )
    from app.services.identity import create_email_account, verify_email
    from app.services.pets import PetInput, create_pet
    from scripts.seed_demo import seed_demo

    engine = create_engine(os.environ['DATABASE_URL'])
    Base.metadata.create_all(engine)
    now = utcnow()

    with Session(engine) as db, db.begin():
        existing = db.scalar(select(User.id).limit(1))
        if existing is not None:
            print('复用已有演示库。')
            return

        settings = Settings.from_env()
        summary = seed_demo(db, settings, email=DEMO_EMAIL, password=DEMO_PASSWORD)
        demo = db.get(User, summary['user_id'])

        breed_pool = ['中华田园猫', '英短蓝猫', '布偶猫', '美短起司', '暹罗猫']
        states = [('normal', False), ('normal', False), ('observe', False),
                  ('observe', False), ('vet', False), ('urgent', True)]
        owners = []
        for index, (nickname, email) in enumerate(DEMO_PET_OWNERS):
            token = create_email_account(db, email, 'Owner12345', now)
            verify_email(db, token, now)
            owner = db.scalar(select(User).join(
                UserCredential, UserCredential.user_id == User.id,
            ).where(UserCredential.identifier == email))
            owner.nickname = nickname
            owners.append(owner)
            pet = create_pet(db, owner.id, PetInput(
                name=['奶糖', '豆包', '花卷', '可乐', '年糕', '布丁', '小满', '橘子'][index],
                breed=breed_pool[index % len(breed_pool)],
                sex='female' if index % 2 == 0 else 'male',
                birth_date=now.date() - timedelta(days=900 + index * 40),
                neutered=True,
            ))
            db.add(DietRecord(pet_id=pet.id, food_type='dry', amount_g=35,
                              kcal_est=120, fed_at=now - timedelta(hours=2 + index)))
            db.add(WeightRecord(pet_id=pet.id, weight_kg=3.8 + index * 0.14,
                                measured_at=now - timedelta(days=index)))
            chat = ChatSession(pet_id=pet.id, user_id=owner.id)
            db.add(chat)
            db.flush()
            db.add(ChatMessage(session_id=chat.id, role='user', kind='text',
                               content='今天精神怎么样？', created_at=now - timedelta(hours=1 + index)))
            for step in range(4):
                state, redline = states[(index + step) % len(states)]
                screening = HealthScreening(
                    pet_id=pet.id, user_id=owner.id, state=state, redline_hit=redline,
                    spirit='normal' if state == 'normal' else 'slightly_down',
                    appetite='normal' if state == 'normal' else 'decreased',
                    triage_json={
                        'redlines': ['breathing'] if redline else [],
                        'symptom_grades': {} if state == 'normal' else {'vomiting': 'vet'},
                    },
                    rules_version='sx-2026-11-19+rl-2026-11-19',
                    created_at=now - timedelta(days=(index * 2 + step) % 24, hours=index),
                )
                db.add(screening)
                db.flush()
                if state != 'normal':
                    db.add(ScreeningSymptom(
                        screening_id=screening.id, symptom_code='vomiting',
                        duration='12-24h', frequency='4-6', severe=redline,
                        notes='夜里开始，精神变差',
                    ))
            for metric in ('screening', 'chat_msg', 'avatar_gen'):
                db.add(UsageCounter(user_id=owner.id, day=now.date(), metric=metric,
                                    count=index + 1))
            db.add(AiUsageLog(user_id=owner.id, provider='dashscope', model='qwen-plus',
                              kind='chat', tokens_in=120 + index * 10, tokens_out=60,
                              cost_est=0.01 + index * 0.002,
                              created_at=now - timedelta(days=index % 20)))
            db.add(AiUsageLog(user_id=owner.id, provider='dashscope', model='qwen-max',
                              kind='llm', tokens_in=80, tokens_out=40, cost_est=0.02,
                              created_at=now - timedelta(days=(index + 3) % 20)))
            db.add(QuotaDenial(user_id=owner.id, metric='screening', day=now.date(),
                               created_at=now - timedelta(hours=index)))
            for step, status in enumerate(('succeeded', 'failed', 'succeeded')):
                db.add(Task(
                    id=f'demo-task-{index:02d}-{step}', pet_id=pet.id,
                    type='avatar_batch', status=status,
                    request_key=f'demo-req-{index:02d}-{step}', payload={},
                    attempts=1 + (step % 2),
                    created_at=now - timedelta(days=index % 5, hours=step),
                    updated_at=now - timedelta(days=index % 5, hours=step)
                    + timedelta(minutes=2),
                ))

        # Give the console a suspended account and a pending deletion to exercise.
        owners[1].status = 'suspended'
        owners[2].status = 'deletion_pending'
        db.add(DeletionJob(user_id=owners[2].id, status='pending',
                           requested_at=now - timedelta(days=2),
                           purge_after=now + timedelta(days=13)))
        print('演示数据已创建。')


def main() -> None:
    parser = argparse.ArgumentParser(description='绒星运营管理台 · 本地演示启动器')
    parser.add_argument('--port', type=int, default=8000, help='监听端口，默认 8000')
    parser.add_argument('--host', default='127.0.0.1',
                        help='监听地址；团队联调用 0.0.0.0（默认仅本机 127.0.0.1）')
    parser.add_argument('--reset', action='store_true', help='删除演示库后重新创建')
    parser.add_argument('--db', default=str(DEFAULT_DEMO_DB),
                        help='演示库路径，默认用户目录下的 RongXing/admin_demo.db')
    args = parser.parse_args()

    db_path = Path(args.db).expanduser()
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SystemExit(f'无法创建演示库目录：{db_path.parent}（{exc}）') from exc
    if args.reset and db_path.exists():
        db_path.unlink()
    configure_env(db_path)
    seed_demo_data()

    import uvicorn

    print('')
    print('  绒星 · 运营管理台（本地演示）', flush=True)
    print(f'  地址：http://127.0.0.1:{args.port}/admin', flush=True)
    print(f'  管理员：{DEMO_EMAIL}', flush=True)
    print(f'  密码：{DEMO_PASSWORD}', flush=True)
    print(f'  演示库：{db_path}', flush=True)
    print('  这是本地 SQLite 演示数据，不用于生产；按 Ctrl+C 停止。', flush=True)
    print('', flush=True)
    uvicorn.run('app.main:create_dev_app', factory=True,
                host=args.host, port=args.port, log_level='info')


if __name__ == '__main__':
    main()
