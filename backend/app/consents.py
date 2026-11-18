from typing import Dict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Consent


def grant_consent(session: Session, user_id: int, consent_type: str, version: str, granted: bool) -> None:
    if consent_type not in ('privacy', 'terms', 'training') or not version or len(version) > 32:
        raise ValueError('invalid consent')
    session.add(Consent(user_id=user_id, type=consent_type, version=version, granted=granted))
    session.flush()


def latest_consents(session: Session, user_id: int) -> Dict[str, Consent]:
    records = session.scalars(select(Consent).where(Consent.user_id == user_id).order_by(Consent.id.desc()))
    latest = {}
    for record in records:
        if record.type not in latest:
            latest[record.type] = record
    return latest


def current_consents(session: Session, user_id: int) -> Dict[str, bool]:
    return {name: record.granted for name, record in latest_consents(session, user_id).items()}


def has_required_consents(session: Session, user_id: int, privacy_version: str, terms_version: str) -> bool:
    records = latest_consents(session, user_id)
    return all(kind in records and records[kind].granted and records[kind].version == version
               for kind, version in (('privacy', privacy_version), ('terms', terms_version)))
