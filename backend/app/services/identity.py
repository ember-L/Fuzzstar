import hashlib
import secrets
from datetime import datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from email_validator import EmailNotValidError, validate_email
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import User, UserCredential

password_hasher = PasswordHasher()


class InvalidCredentials(Exception):
    pass


class UnverifiedEmail(InvalidCredentials):
    pass


class InvalidVerification(Exception):
    pass


class EmailAlreadyRegistered(ValueError):
    pass


def normalize_email(email: str) -> str:
    try:
        normalized = validate_email(email, check_deliverability=False).normalized.lower()
    except EmailNotValidError as exc:
        raise ValueError('invalid email') from exc
    if len(normalized) > 128:
        raise ValueError('email too long')
    return normalized


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def create_email_account(
    session: Session, email: str, password: str, now: datetime, *, verification_token: str | None = None
) -> str:
    email = normalize_email(email)
    if (
        not 8 <= len(password) <= 128
        or not any(c.isascii() and c.isalpha() for c in password)
        or not any(c.isascii() and c.isdigit() for c in password)
    ):
        raise ValueError('password must contain letters and digits and have 8 to 128 characters')
    if (
        session.scalar(
            select(UserCredential.id).where(UserCredential.type == 'email', UserCredential.identifier == email)
        )
        is not None
    ):
        raise EmailAlreadyRegistered('email already registered')
    token = verification_token if verification_token is not None else secrets.token_urlsafe(32)
    user = User(nickname='猫咪主人')
    session.add(user)
    session.flush()
    session.add(
        UserCredential(
            user_id=user.id,
            type='email',
            identifier=email,
            secret_hash=password_hasher.hash(password),
            verification_hash=token_hash(token),
            verification_expires_at=now + timedelta(hours=24),
        )
    )
    session.flush()
    return token


def verify_email(session: Session, token: str, now: datetime) -> None:
    result = session.execute(
        update(UserCredential)
        .where(
            UserCredential.type == 'email',
            UserCredential.verification_hash == token_hash(token),
            UserCredential.verification_expires_at > now,
            UserCredential.verified_at.is_(None),
        )
        .values(verified_at=now, verification_hash=None, verification_expires_at=None)
    )
    if result.rowcount != 1:
        raise InvalidVerification()


def login_email(session: Session, email: str, password: str, *, allow_unverified: bool = False) -> User:
    """Authenticate with email + password.

    ``allow_unverified`` lets whitelisted console admins sign in without
    completing the email verification flow; regular accounts must still verify.
    """
    try:
        email = normalize_email(email)
    except ValueError as exc:
        raise InvalidCredentials() from exc
    credential = session.scalar(
        select(UserCredential).where(UserCredential.type == 'email', UserCredential.identifier == email)
    )
    if credential is None or credential.secret_hash is None:
        raise InvalidCredentials()
    try:
        password_hasher.verify(credential.secret_hash, password)
    except (VerifyMismatchError, InvalidHashError) as exc:
        raise InvalidCredentials() from exc
    user = session.get(User, credential.user_id)
    if user is None or user.status != 'active':
        raise InvalidCredentials()
    if credential.verified_at is None and not allow_unverified:
        raise UnverifiedEmail()
    return user
