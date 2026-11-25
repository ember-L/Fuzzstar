"""Create or reset a console admin account.

Accounts are usable immediately (the email verification flow was removed),
so SMTP and verification mail are never needed.

Usage (from backend/):

    python -m scripts.create_admin --email admin@rongxing.app --password Admin2026

Password rules: 8-128 characters, must contain both letters and digits.
The email must also appear in ADMIN_EMAILS (.env) for console access.
"""

from __future__ import annotations

import argparse
import os

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.env import load_env
from app.core.security import utcnow
from app.models import User, UserCredential
from app.services.identity import (
    EmailAlreadyRegistered,
    create_email_account,
    normalize_email,
    password_hasher,
)


def main() -> None:
    parser = argparse.ArgumentParser(description='创建/重置运营管理台管理员账户')
    parser.add_argument('--email', required=True, help='管理员登录邮箱')
    parser.add_argument('--password', required=True, help='登录密码（8-128位，需含字母和数字）')
    args = parser.parse_args()

    load_env()
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise SystemExit('未找到 DATABASE_URL，请确认 backend/.env 已配置')

    email = normalize_email(args.email)
    admins = {item.strip().lower() for item in (os.environ.get('ADMIN_EMAILS') or '').split(',') if item.strip()}
    if email not in admins:
        print(f'提醒：{email} 不在 ADMIN_EMAILS 中，将无法进入管理台。')
        print('请把该邮箱加入 backend/.env 的 ADMIN_EMAILS（多个用英文逗号分隔）后重启后端。')

    engine = create_engine(database_url)
    now = utcnow()
    with Session(engine) as db, db.begin():
        credential = db.scalar(
            select(UserCredential).where(UserCredential.type == 'email', UserCredential.identifier == email)
        )
        if credential is None:
            try:
                create_email_account(db, email, args.password, now)
                print('已创建新管理员账户。')
            except EmailAlreadyRegistered as exc:  # pragma: no cover - race window
                raise SystemExit(f'邮箱已被注册：{exc}') from exc
        else:
            credential.secret_hash = password_hasher.hash(args.password)
            credential.verified_at = now
            user = db.get(User, credential.user_id)
            if user is not None and user.status != 'active':
                user.status = 'active'
                print('已将该账户状态恢复为 active。')
            print('已重置现有账户的密码。')
    print(f'管理员账户已就绪：{email}')


if __name__ == '__main__':
    main()
