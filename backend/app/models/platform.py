"""Platform-level rows: idempotency, deletion, quota and entitlements."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RequestIdempotency(Base):
    __tablename__ = 'request_idempotency'
    __table_args__ = (UniqueConstraint('user_id', 'key', name='uk_idempotency_user_key'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True, nullable=False)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_json: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
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


class QuotaDenial(Base):
    __tablename__ = 'quota_denials'
    __table_args__ = (Index('ix_quota_denials_day', 'day'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    metric: Mapped[str] = mapped_column(String(16), nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


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
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
