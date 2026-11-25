"""Authentication routes: register, login, refresh, session self-service."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import current_user, deletion_user
from app.core.errors import api_error, auth_required
from app.core.security import token_pair, utcnow
from app.models import User
from app.schemas.auth import LoginInput, RefreshInput, TokenPair
from app.services.identity import (
    EmailAlreadyRegistered,
    InvalidCredentials,
    create_email_account,
    login_email,
)
from app.services.privacy import request_deletion
from app.services.sessions import create_session, rotate_refresh_token

router = APIRouter(prefix='/api/v1')


def _login_pair(db: Session, secret: str, user: User, now: datetime) -> TokenPair:
    pair = token_pair(db, secret, create_session(db, user.id, now), now)
    db.commit()
    return pair


@router.post('/auth/register', response_model=TokenPair)
def register(data: LoginInput, request: Request, response: Response, db: Session = Depends(get_db)):
    """Create an account and sign in immediately; no email verification is required."""
    now = utcnow()
    try:
        user = create_email_account(db, data.email, data.password, now)
    except EmailAlreadyRegistered:
        return api_error(409, 'EMAIL_REGISTERED', '该邮箱已注册，请直接登录')
    except ValueError:
        return api_error(400, 'VALIDATION_ERROR', '请输入有效邮箱及含字母和数字的至少 8 位密码')
    except IntegrityError:
        db.rollback()
        return api_error(409, 'EMAIL_REGISTERED', '该邮箱已注册，请直接登录')
    response.headers['Cache-Control'] = 'no-store'
    return _login_pair(db, request.app.state.jwt_secret, user, now)


@router.post('/auth/login', response_model=TokenPair)
def login(data: LoginInput, request: Request, response: Response, db: Session = Depends(get_db)):
    try:
        user = login_email(db, data.email, data.password)
    except InvalidCredentials:
        return auth_required()
    now = datetime.now(UTC).replace(tzinfo=None)
    response.headers['Cache-Control'] = 'no-store'
    return _login_pair(db, request.app.state.jwt_secret, user, now)


@router.post('/auth/refresh', response_model=TokenPair)
def refresh(data: RefreshInput, request: Request, response: Response, db: Session = Depends(get_db)):
    now = datetime.now(UTC).replace(tzinfo=None)
    rotated = rotate_refresh_token(db, data.refresh_token, now)
    pair = token_pair(db, request.app.state.jwt_secret, rotated, now) if rotated else None
    # Commit on rejection too: a replay may have revoked the session chain.
    db.commit()
    if pair is None:
        return api_error(401, 'TOKEN_EXPIRED', '会话已失效，请重新登录')
    response.headers['Cache-Control'] = 'no-store'
    return pair


@router.get('/me')
def me(response: Response, user: User = Depends(current_user)):
    response.headers['Cache-Control'] = 'no-store'
    return {'id': user.id, 'nickname': user.nickname}


@router.delete('/me', status_code=202)
def delete_me(response: Response, user: User = Depends(deletion_user), db: Session = Depends(get_db)):
    job, created = request_deletion(db, user.id, now=datetime.now(UTC).replace(tzinfo=None))
    db.commit()
    if not created:
        response.status_code = 200
    response.headers['Cache-Control'] = 'no-store'
    return {'status': job.status, 'purge_after': job.purge_after.isoformat()}
