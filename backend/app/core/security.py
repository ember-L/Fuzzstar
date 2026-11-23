"""Token, clock and HTTP bearer primitives shared by auth deps and routes."""
from datetime import datetime, timedelta, timezone

import jwt
from fastapi.security import HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuthSession, RefreshToken
from app.schemas.auth import TokenPair
from app.services.identity import token_hash

bearer = HTTPBearer(auto_error=False)


def utcnow() -> datetime:
    """Naive UTC timestamp used by the database layer."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def token_pair(db: Session, secret: str, refresh_token: str, now: datetime) -> TokenPair:
    session = db.execute(select(AuthSession).join(
        RefreshToken, RefreshToken.session_id == AuthSession.id,
    ).where(RefreshToken.token_hash == token_hash(refresh_token))).scalar_one()
    issued = now.replace(tzinfo=timezone.utc)
    access_token = jwt.encode({
        'iss': 'rongxing', 'sub': str(session.user_id), 'sid': session.id,
        'iat': issued, 'exp': issued + timedelta(minutes=30),
    }, secret, algorithm='HS256')
    return TokenPair(access_token=access_token, refresh_token=refresh_token)
