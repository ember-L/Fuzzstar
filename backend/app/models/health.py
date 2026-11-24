"""Health screening, events and AI usage audit rows."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


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
    llm_advice: Mapped[str | None] = mapped_column(Text, nullable=True)
    advice_json: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    triage_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    rules_version: Mapped[str] = mapped_column(String(32), nullable=False)
    task_id: Mapped[str | None] = mapped_column(String(32), ForeignKey('tasks.id'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class ScreeningSymptom(Base):
    __tablename__ = 'screening_symptoms'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    screening_id: Mapped[int] = mapped_column(
        ForeignKey('health_screenings.id', ondelete='CASCADE'), index=True, nullable=False
    )
    symptom_code: Mapped[str] = mapped_column(String(32), nullable=False)
    duration: Mapped[str] = mapped_column(String(8), nullable=False)
    frequency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    severe: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ScreeningMedia(Base):
    __tablename__ = 'screening_media'
    __table_args__ = (UniqueConstraint('screening_id', 'media_id', name='uk_screening_media'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    screening_id: Mapped[int] = mapped_column(
        ForeignKey('health_screenings.id', ondelete='CASCADE'), index=True, nullable=False
    )
    media_id: Mapped[str] = mapped_column(String(32), ForeignKey('media_uploads.id'), nullable=False)
    type: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class HealthEvent(Base):
    __tablename__ = 'health_events'
    __table_args__ = (Index('ix_health_events_pet_active', 'pet_id', 'active'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pet_id: Mapped[int] = mapped_column(ForeignKey('pets.id'), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    score_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class AiUsageLog(Base):
    __tablename__ = 'ai_usage_logs'
    __table_args__ = (Index('ix_ai_usage_logs_created_at', 'created_at'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(32), ForeignKey('tasks.id'), nullable=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    media_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_est: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
