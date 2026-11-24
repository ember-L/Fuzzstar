import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuthSession, RefreshToken, User
from app.services.identity import token_hash


def _issue_token(db: Session, session_id: int, now: datetime) -> str:
    token = secrets.token_urlsafe(32)
    db.add(RefreshToken(session_id=session_id, token_hash=token_hash(token), expires_at=now + timedelta(days=30)))
    db.flush()
    return token


def create_session(db: Session, user_id: int, now: datetime) -> str:
    user = db.get(User, user_id)
    if user is None or user.status != 'active':
        raise ValueError('inactive user')
    session = AuthSession(user_id=user_id)
    db.add(session)
    db.flush()
    return _issue_token(db, session.id, now)


def rotate_refresh_token(db: Session, token: str, now: datetime) -> str | None:
    """Return a new token or None; commit even on None to persist replay revocation."""
    digest = token_hash(token)
    session_id = db.scalar(select(RefreshToken.session_id).where(RefreshToken.token_hash == digest))
    if session_id is None:
        return None
    session = db.scalar(
        select(AuthSession)
        .where(AuthSession.id == session_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    record = db.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == digest)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if session is None or record is None or session.revoked_at is not None:
        return None
    if record.used_at is not None:
        session.revoked_at = now
        db.flush()
        return None
    user = db.get(User, session.user_id)
    if record.expires_at <= now or user is None or user.status != 'active':
        return None
    record.used_at = now
    return _issue_token(db, session.id, now)
