"""Consent records and the request-time consent state used by route guards."""

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import APIError
from app.models import Consent, User


def grant_consent(session: Session, user_id: int, consent_type: str, version: str, granted: bool) -> None:
    if consent_type not in ('privacy', 'terms', 'training') or not version or len(version) > 32:
        raise ValueError('invalid consent')
    session.add(Consent(user_id=user_id, type=consent_type, version=version, granted=granted))
    session.flush()


def latest_consents(session: Session, user_id: int) -> dict[str, Consent]:
    records = session.scalars(select(Consent).where(Consent.user_id == user_id).order_by(Consent.id.desc()))
    latest = {}
    for record in records:
        if record.type not in latest:
            latest[record.type] = record
    return latest


def current_consents(session: Session, user_id: int) -> dict[str, bool]:
    return {name: record.granted for name, record in latest_consents(session, user_id).items()}


def has_required_consents(session: Session, user_id: int, privacy_version: str, terms_version: str) -> bool:
    records = latest_consents(session, user_id)
    return all(
        kind in records and records[kind].granted and records[kind].version == version
        for kind, version in (('privacy', privacy_version), ('terms', terms_version))
    )


def consent_state(session: Session, user: User, request: Request) -> dict:
    """Current policy versions, links and whether this user has accepted them."""
    versions = request.app.state.policy_versions
    if not all(versions.values()):
        raise APIError(503, 'CONSENT_UNAVAILABLE', '隐私政策和服务协议版本尚未配置')
    latest = latest_consents(session, user.id)
    return {
        'required': versions,
        'links': request.app.state.policy_links,
        'granted': all(
            kind in latest and latest[kind].granted and latest[kind].version == version
            for kind, version in versions.items()
        ),
        'training_granted': 'training' in latest and latest['training'].granted,
    }
