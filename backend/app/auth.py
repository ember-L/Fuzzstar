from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from typing import Literal, Optional

import jwt
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.auth_limits import allow_auth_request
from app.identity import (
    EmailAlreadyRegistered, InvalidCredentials, InvalidVerification, UnverifiedEmail,
    create_email_account, login_email, normalize_email, token_hash, verify_email,
)
from app.mail_worker import verification_token
from app.models import AuthSession, RefreshToken, User, UserCredential, VerificationMail
from app.sessions import create_session, rotate_refresh_token

class APIError(Exception):
    def __init__(self, status: int, code: str, message: str, detail: dict | None = None):
        self.status, self.code, self.message = status, code, message
        self.detail = detail or {}


router = APIRouter(prefix='/api/v1')
bearer = HTTPBearer(auto_error=False)


class LoginInput(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class RefreshInput(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=128)


class VerifyEmailInput(BaseModel):
    token: str = Field(min_length=1, max_length=128)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal['bearer'] = 'bearer'
    expires_in: int = 1800


def api_error(status: int, code: str, message: str, detail: dict | None = None):
    headers = {'Cache-Control': 'no-store'}
    if status == 401:
        headers['WWW-Authenticate'] = 'Bearer'
    return JSONResponse({'code': code, 'message': message, 'detail': detail or {}}, status_code=status, headers=headers)


def auth_required():
    return api_error(401, 'AUTH_REQUIRED', '请检查登录信息或重新登录')


def get_db(request: Request):
    with Session(request.app.state.engine) as db:
        yield db


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


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def auth_rate_limit(request: Request, call_next):
    if request.method == 'POST' and request.url.path.startswith('/api/v1/auth/'):
        now = utcnow()
        minute = now.replace(second=0, microsecond=0)
        address = request.client.host if request.client else 'unknown'
        if not await run_in_threadpool(allow_auth_request, request.app.state.engine,
                                       request.app.state.jwt_secret, address, minute):
            response = api_error(429, 'RATE_LIMITED', '请求过于频繁，请稍后再试')
            response.headers['Retry-After'] = str(60 - now.second)
            return response
    return await call_next(request)


MAIL_ACCEPTED = {'message': '如果请求符合条件，请查收邮箱验证邮件。'}


@router.post('/auth/register', status_code=202)
def register(data: LoginInput, request: Request, db: Session = Depends(get_db)):
    now = utcnow()
    nonce = token_urlsafe(32)
    token = verification_token(request.app.state.jwt_secret, nonce)
    try:
        email = normalize_email(data.email)
        create_email_account(db, email, data.password, now, verification_token=token)
    except EmailAlreadyRegistered:
        return MAIL_ACCEPTED
    except ValueError:
        return api_error(400, 'VALIDATION_ERROR', '请输入有效邮箱及含字母和数字的至少 8 位密码')
    except IntegrityError:
        db.rollback()
        if db.scalar(select(UserCredential.id).where(
            UserCredential.type == 'email', UserCredential.identifier == email,
        )) is not None:
            return MAIL_ACCEPTED
        raise
    credential_id = db.scalar(select(UserCredential.id).where(UserCredential.verification_hash == token_hash(token)))
    db.add(VerificationMail(credential_id=credential_id, nonce=nonce, queued_at=now, due_at=now))
    db.commit()
    return MAIL_ACCEPTED


@router.post('/auth/resend-verification', status_code=202)
def resend_verification(data: LoginInput, request: Request, db: Session = Depends(get_db)):
    try:
        login_email(db, data.email, data.password)
    except UnverifiedEmail:
        pass
    except InvalidCredentials:
        return MAIL_ACCEPTED
    else:
        return MAIL_ACCEPTED
    now = utcnow()
    credential = db.scalar(select(UserCredential).where(
        UserCredential.type == 'email', UserCredential.identifier == normalize_email(data.email),
    ))
    if credential is None or credential.verified_at is not None:
        return MAIL_ACCEPTED
    nonce = token_urlsafe(32)
    token = verification_token(request.app.state.jwt_secret, nonce)
    # Compare-and-swap prevents simultaneous resends or confirmation from replacing a live token.
    mail = db.get(VerificationMail, credential.id)
    if mail is not None and mail.queued_at > now - timedelta(seconds=60):
        return MAIL_ACCEPTED
    changed = db.execute(update(UserCredential).where(
        UserCredential.id == credential.id, UserCredential.verified_at.is_(None),
        UserCredential.verification_hash == credential.verification_hash,
    ).values(verification_hash=token_hash(token), verification_expires_at=now + timedelta(hours=24)))
    if changed.rowcount == 1:
        if mail is None:
            mail = VerificationMail(credential_id=credential.id)
            db.add(mail)
        mail.nonce, mail.queued_at, mail.due_at, mail.failures = nonce, now, now, 0
        db.commit()
    return MAIL_ACCEPTED


@router.get('/auth/verify-email', response_class=HTMLResponse)
def email_verification_page():
    nonce = token_urlsafe(24)
    return HTMLResponse(f"""<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>验证绒星邮箱</title><main><h1>验证绒星邮箱</h1>
<p id="status" role="status">点击下方按钮确认验证。</p><button disabled>确认验证</button>
<noscript>验证邮箱需要启用 JavaScript。</noscript></main>
<script nonce="{nonce}">
const token = new URLSearchParams(location.hash.slice(1)).get('token');
const button = document.querySelector('button');
const status = document.querySelector('#status');
if (!token) status.textContent = '请从验证邮件打开此页面。';
else {{
    button.disabled = false;
    button.onclick = async () => {{
        button.disabled = true;
        try {{
            const response = await fetch(location.pathname, {{
                method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify({{token}})
            }});
            if (!response.ok && response.status !== 400) throw new Error();
            history.replaceState(null, '', location.pathname);
            status.textContent = response.ok ? '邮箱已验证，请返回绒星登录。' : '验证链接无效、已过期或已使用。';
        }} catch {{
            status.textContent = '暂时无法验证，请重试。';
            button.disabled = false;
        }}
    }};
}}
</script></html>""", headers={
        'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
        'Content-Security-Policy': f"default-src 'none'; script-src 'nonce-{nonce}'; connect-src 'self'; frame-ancestors 'none'",
    })


@router.post('/auth/verify-email')
def confirm_email(data: VerifyEmailInput, response: Response, db: Session = Depends(get_db)):
    try:
        verify_email(db, data.token, datetime.now(timezone.utc).replace(tzinfo=None))
    except InvalidVerification:
        return api_error(400, 'VERIFICATION_INVALID', '验证链接无效、已过期或已使用')
    db.commit()
    response.headers['Cache-Control'] = 'no-store'
    return {'verified': True}


@router.post('/auth/login', response_model=TokenPair)
def login(data: LoginInput, request: Request, response: Response, db: Session = Depends(get_db)):
    try:
        user = login_email(db, data.email, data.password)
    except UnverifiedEmail:
        return api_error(401, 'EMAIL_UNVERIFIED', '请先验证邮箱')
    except InvalidCredentials:
        return auth_required()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    pair = token_pair(db, request.app.state.jwt_secret, create_session(db, user.id, now), now)
    db.commit()
    response.headers['Cache-Control'] = 'no-store'
    return pair


@router.post('/auth/refresh', response_model=TokenPair)
def refresh(data: RefreshInput, request: Request, response: Response, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rotated = rotate_refresh_token(db, data.refresh_token, now)
    pair = token_pair(db, request.app.state.jwt_secret, rotated, now) if rotated else None
    # Commit on rejection too: a replay may have revoked the session chain.
    db.commit()
    if pair is None:
        return api_error(401, 'TOKEN_EXPIRED', '会话已失效，请重新登录')
    response.headers['Cache-Control'] = 'no-store'
    return pair


def current_user(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
                 db: Session = Depends(get_db)) -> User:
    unauthorized = APIError(401, 'AUTH_REQUIRED', '请重新登录')
    if credentials is None:
        raise unauthorized
    try:
        claims = jwt.decode(credentials.credentials, request.app.state.jwt_secret, algorithms=['HS256'],
                            issuer='rongxing', options={'require': ['sub', 'sid', 'iat', 'exp', 'iss']})
    except jwt.ExpiredSignatureError as exc:
        raise APIError(401, 'TOKEN_EXPIRED', '会话已失效，请重新登录') from exc
    except jwt.InvalidTokenError as exc:
        raise unauthorized from exc
    if type(claims['sid']) is not int or not 0 < claims['sid'] < 2**63:
        raise unauthorized
    user = db.scalar(select(User).join(AuthSession, AuthSession.user_id == User.id).where(
        AuthSession.id == claims['sid'], AuthSession.revoked_at.is_(None), User.status == 'active',
    ))
    if user is None or str(user.id) != claims['sub']:
        raise unauthorized
    return user


@router.get('/me')
def me(response: Response, user: User = Depends(current_user)):
    response.headers['Cache-Control'] = 'no-store'
    return {'id': user.id, 'nickname': user.nickname}
