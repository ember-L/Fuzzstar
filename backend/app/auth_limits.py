from datetime import datetime
from hmac import digest

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AuthRateBucket


def allow_auth_request(engine, secret: str, address: str, minute: datetime) -> bool:
    source = digest(secret.encode(), f'auth-ip:{address}'.encode(), 'sha256').hex()
    increment = update(AuthRateBucket).where(
        AuthRateBucket.source_hash == source, AuthRateBucket.minute == minute,
        AuthRateBucket.requests < 30,
    ).values(requests=AuthRateBucket.requests + 1)
    with Session(engine) as db, db.begin():
        if db.execute(increment).rowcount == 1:
            return True
        try:
            with db.begin_nested():
                db.add(AuthRateBucket(source_hash=source, minute=minute, requests=1))
                db.flush()
        except IntegrityError:
            return db.execute(increment).rowcount == 1
        return True
