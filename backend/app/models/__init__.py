"""SQLAlchemy models, re-exported by domain module.

Import model classes from :mod:`app.models` so table registration always happens
through this package; `Base.metadata` stays the single Alembic entry point.
"""

from app.models.admin import AdminAuditLog
from app.models.base import Base
from app.models.chat import ChatMessage, ChatSession
from app.models.health import AiUsageLog, HealthEvent, HealthScreening, ScreeningMedia, ScreeningSymptom
from app.models.media import MediaUpload
from app.models.pet import Pet
from app.models.platform import (
    DeletionJob,
    Entitlement,
    Plan,
    QuotaDenial,
    RequestIdempotency,
    UsageCounter,
)
from app.models.task import Task
from app.models.tracker import DietRecord, WeightRecord
from app.models.user import AuthRateBucket, AuthSession, Consent, RefreshToken, User, UserCredential

__all__ = [
    'AdminAuditLog',
    'AiUsageLog',
    'AuthRateBucket',
    'AuthSession',
    'Base',
    'ChatMessage',
    'ChatSession',
    'Consent',
    'DeletionJob',
    'DietRecord',
    'Entitlement',
    'HealthEvent',
    'HealthScreening',
    'MediaUpload',
    'Pet',
    'Plan',
    'QuotaDenial',
    'RefreshToken',
    'RequestIdempotency',
    'ScreeningMedia',
    'ScreeningSymptom',
    'Task',
    'UsageCounter',
    'User',
    'UserCredential',
    'WeightRecord',
]
