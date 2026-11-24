"""Request-scoped database session dependency."""

from fastapi import Request
from sqlalchemy.orm import Session

from app.services.quota import flush_quota_denials


def get_db(request: Request):
    with Session(request.app.state.engine) as db:
        try:
            yield db
        finally:
            db.rollback()
            flush_quota_denials(db)
