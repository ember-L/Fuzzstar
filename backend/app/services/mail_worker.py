"""Drain the verification outbox once; run repeatedly with a process supervisor."""

import os
from datetime import UTC, datetime, timedelta
from hmac import digest

from sqlalchemy import create_engine, delete, select, update
from sqlalchemy.orm import Session

from app.core.env import load_env
from app.models import AuthRateBucket, User, UserCredential, VerificationMail
from app.services.identity import token_hash
from app.services.mail import MailConfigurationError, send_verification_email


def verification_token(secret: str, nonce: str) -> str:
    return digest(secret.encode(), f'verify-email:{nonce}'.encode(), 'sha256').hex()


def deliver_due(engine, secret: str, now: datetime) -> int:
    with Session(engine) as db, db.begin():
        db.execute(delete(AuthRateBucket).where(AuthRateBucket.minute < now - timedelta(days=1)))
        db.execute(delete(VerificationMail).where(VerificationMail.queued_at <= now - timedelta(hours=24)))
        items = db.execute(
            select(
                VerificationMail.credential_id,
                VerificationMail.nonce,
                VerificationMail.due_at,
                VerificationMail.failures,
                UserCredential.identifier,
                UserCredential.verification_hash,
                User.status,
            )
            .join(UserCredential, VerificationMail.credential_id == UserCredential.id)
            .join(User, UserCredential.user_id == User.id)
            .where(VerificationMail.due_at <= now)
            .order_by(VerificationMail.due_at)
            .limit(20)
        ).all()
    delivered = 0
    for credential_id, nonce, due_at, failures, email, current_hash, status in items:
        claimed_at = max(now, datetime.now(UTC).replace(tzinfo=None))
        lease_until = claimed_at + timedelta(minutes=5)
        job = update(VerificationMail).where(
            VerificationMail.credential_id == credential_id, VerificationMail.nonce == nonce
        )
        with Session(engine) as db, db.begin():
            if db.execute(job.where(VerificationMail.due_at == due_at).values(due_at=lease_until)).rowcount != 1:
                continue
        next_attempt = None
        token = verification_token(secret, nonce)
        if status == 'active' and current_hash == token_hash(token):
            try:
                send_verification_email(email, token)
            except (MailConfigurationError, OSError):
                failures += 1
                if failures < 5:
                    next_attempt = claimed_at + timedelta(seconds=30 * 2 ** (failures - 1))
            else:
                delivered += 1
        with Session(engine) as db, db.begin():
            db.execute(job.where(VerificationMail.due_at == lease_until).values(due_at=next_attempt, failures=failures))
    return delivered


if __name__ == '__main__':
    load_env()
    url = os.environ.get('DATABASE_URL')
    secret = os.environ.get('JWT_SECRET', '')
    if not url or len(secret.encode()) < 32:
        raise SystemExit('DATABASE_URL and JWT_SECRET (at least 32 bytes) are required')
    engine = create_engine(url, hide_parameters=True)
    try:
        print(f'Delivered verification emails: {deliver_due(engine, secret, datetime.now(UTC).replace(tzinfo=None))}')
    finally:
        engine.dispose()
