from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nickname: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default='active')
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class UserCredential(Base):
    __tablename__ = 'user_credentials'
    __table_args__ = (UniqueConstraint('type', 'identifier', name='uk_credential_type_identifier'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    identifier: Mapped[str] = mapped_column(String(128), nullable=False)
    secret_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    verification_hash: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True)
    verification_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Consent(Base):
    __tablename__ = 'consents'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class AuthSession(Base):
    __tablename__ = 'auth_sessions'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True, nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class RefreshToken(Base):
    __tablename__ = 'refresh_tokens'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey('auth_sessions.id'), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Pet(Base):
    __tablename__ = 'pets'
    __table_args__ = (Index('ix_pets_user_status', 'user_id', 'status'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    species: Mapped[str] = mapped_column(String(16), default='cat')
    breed: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    sex: Mapped[str] = mapped_column(String(16), default='unknown')
    birth_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    neutered: Mapped[bool] = mapped_column(Boolean, default=False)
    body_type: Mapped[str] = mapped_column(String(16), default='standard', server_default='standard', nullable=False)
    status: Mapped[str] = mapped_column(String(16), default='active')
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class VerificationMail(Base):
    __tablename__ = 'verification_mail'

    credential_id: Mapped[int] = mapped_column(ForeignKey('user_credentials.id', ondelete='CASCADE'), primary_key=True)
    nonce: Mapped[str] = mapped_column(String(48), nullable=False)
    queued_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class AuthRateBucket(Base):
    __tablename__ = 'auth_rate_buckets'

    source_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    minute: Mapped[datetime] = mapped_column(DateTime, primary_key=True, index=True)
    requests: Mapped[int] = mapped_column(Integer, nullable=False)


class Task(Base):
    __tablename__ = 'tasks'

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    pet_id: Mapped[int] = mapped_column(ForeignKey('pets.id'), index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    request_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    result: Mapped[Optional[dict]] = mapped_column(JSON(none_as_null=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    lease_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp())


class MediaUpload(Base):
    __tablename__ = 'media_uploads'

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    pet_id: Mapped[int] = mapped_column(ForeignKey('pets.id'), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(8), default='photo', server_default='photo', nullable=False)
    content_type: Mapped[str] = mapped_column(String(16), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    version_id: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    @property
    def object_key(self) -> str:
        prefix = 'videos' if self.kind == 'video' else 'audio' if self.kind == 'audio' else 'photos'
        return f'{prefix}/{self.pet_id}/{self.id}'


class HealthScreening(Base):
    __tablename__ = 'health_screenings'
    __table_args__ = (Index('ix_health_screenings_pet_time', 'pet_id', 'created_at'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pet_id: Mapped[int] = mapped_column(ForeignKey('pets.id'), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    redline_hit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    spirit: Mapped[str] = mapped_column(String(16), nullable=False)
    appetite: Mapped[str] = mapped_column(String(16), nullable=False)
    llm_advice: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    advice_json: Mapped[Optional[dict]] = mapped_column(JSON(none_as_null=True), nullable=True)
    triage_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    rules_version: Mapped[str] = mapped_column(String(32), nullable=False)
    task_id: Mapped[Optional[str]] = mapped_column(String(32), ForeignKey('tasks.id'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class ScreeningSymptom(Base):
    __tablename__ = 'screening_symptoms'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    screening_id: Mapped[int] = mapped_column(ForeignKey('health_screenings.id', ondelete='CASCADE'), index=True, nullable=False)
    symptom_code: Mapped[str] = mapped_column(String(32), nullable=False)
    duration: Mapped[str] = mapped_column(String(8), nullable=False)
    frequency: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    severe: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ScreeningMedia(Base):
    __tablename__ = 'screening_media'
    __table_args__ = (UniqueConstraint('screening_id', 'media_id', name='uk_screening_media'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    screening_id: Mapped[int] = mapped_column(ForeignKey('health_screenings.id', ondelete='CASCADE'), index=True, nullable=False)
    media_id: Mapped[str] = mapped_column(String(32), ForeignKey('media_uploads.id'), nullable=False)
    type: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class HealthEvent(Base):
    __tablename__ = 'health_events'
    __table_args__ = (Index('ix_health_events_pet_active', 'pet_id', 'active'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pet_id: Mapped[int] = mapped_column(ForeignKey('pets.id'), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    source_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    score_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class AiUsageLog(Base):
    __tablename__ = 'ai_usage_logs'
    __table_args__ = (Index('ix_ai_usage_logs_created_at', 'created_at'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id'), nullable=True)
    task_id: Mapped[Optional[str]] = mapped_column(String(32), ForeignKey('tasks.id'), nullable=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    tokens_in: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    media_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cost_est: Mapped[Optional[float]] = mapped_column(Numeric(10, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class DietRecord(Base):
    __tablename__ = 'diet_records'
    __table_args__ = (Index('ix_diet_records_pet_time', 'pet_id', 'fed_at'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pet_id: Mapped[int] = mapped_column(ForeignKey('pets.id'), nullable=False)
    food_type: Mapped[str] = mapped_column(String(8), nullable=False)
    food_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    amount_g: Mapped[float] = mapped_column(Numeric(7, 1), nullable=False)
    kcal_est: Mapped[Optional[float]] = mapped_column(Numeric(7, 1), nullable=True)
    fed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class WeightRecord(Base):
    __tablename__ = 'weight_records'
    __table_args__ = (Index('ix_weight_records_pet_time', 'pet_id', 'measured_at'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pet_id: Mapped[int] = mapped_column(ForeignKey('pets.id'), nullable=False)
    weight_kg: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ChatSession(Base):
    __tablename__ = 'chat_sessions'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pet_id: Mapped[int] = mapped_column(ForeignKey('pets.id'), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class ChatMessage(Base):
    __tablename__ = 'chat_messages'
    __table_args__ = (Index('ix_chat_messages_session_time', 'session_id', 'created_at'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey('chat_sessions.id'), nullable=False)
    role: Mapped[str] = mapped_column(String(8), nullable=False)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    audio_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    emotion_label: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    emotion_confidence: Mapped[Optional[float]] = mapped_column(Numeric(4, 3), nullable=True)
    task_id: Mapped[Optional[str]] = mapped_column(String(32), ForeignKey('tasks.id'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class RequestIdempotency(Base):
    __tablename__ = 'request_idempotency'
    __table_args__ = (UniqueConstraint('user_id', 'key', name='uk_idempotency_user_key'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True, nullable=False)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_json: Mapped[Optional[dict]] = mapped_column(JSON(none_as_null=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class DeletionJob(Base):
    __tablename__ = 'deletion_jobs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default='pending', server_default='pending', nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    purge_after: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)


class UsageCounter(Base):
    __tablename__ = 'usage_counters'
    __table_args__ = (UniqueConstraint('user_id', 'day', 'metric', name='uk_usage_user_day_metric'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True, nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    metric: Mapped[str] = mapped_column(String(16), nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=0, server_default='0', nullable=False)


class Plan(Base):
    __tablename__ = 'plans'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    entitlements: Mapped[dict] = mapped_column(JSON, nullable=False)


class Entitlement(Base):
    __tablename__ = 'entitlements'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), unique=True, nullable=False)
    plan_id: Mapped[int] = mapped_column(ForeignKey('plans.id'), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default='reserved', server_default='reserved', nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
