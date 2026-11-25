import hashlib
from datetime import datetime

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from email_validator import EmailNotValidError, validate_email
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User, UserCredential

password_hasher = PasswordHasher()


class InvalidCredentials(Exception):
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


def create_email_account(session: Session, email: str, password: str, now: datetime) -> User:
    """Create an email account that is immediately usable (no verification step)."""
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
    user = User(nickname='猫咪主人')
    session.add(user)
    session.flush()
    session.add(
        UserCredential(
            user_id=user.id,
            type='email',
            identifier=email,
            secret_hash=password_hasher.hash(password),
            verified_at=now,
        )
    )
    session.flush()
    return user


def login_email(session: Session, email: str, password: str) -> User:
    """Authenticate with email + password."""
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
    return user
