"""Pet profile."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Pet(Base):
    __tablename__ = 'pets'
    __table_args__ = (Index('ix_pets_user_status', 'user_id', 'status'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    species: Mapped[str] = mapped_column(String(16), default='cat')
    breed: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sex: Mapped[str] = mapped_column(String(16), default='unknown')
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    neutered: Mapped[bool] = mapped_column(Boolean, default=False)
    body_type: Mapped[str] = mapped_column(String(16), default='standard', server_default='standard', nullable=False)
    status: Mapped[str] = mapped_column(String(16), default='active')
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
