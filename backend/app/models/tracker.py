"""Diet and weight tracking rows."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DietRecord(Base):
    __tablename__ = 'diet_records'
    __table_args__ = (Index('ix_diet_records_pet_time', 'pet_id', 'fed_at'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pet_id: Mapped[int] = mapped_column(ForeignKey('pets.id'), nullable=False)
    food_type: Mapped[str] = mapped_column(String(8), nullable=False)
    food_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    amount_g: Mapped[float] = mapped_column(Numeric(7, 1), nullable=False)
    kcal_est: Mapped[float | None] = mapped_column(Numeric(7, 1), nullable=True)
    fed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class WeightRecord(Base):
    __tablename__ = 'weight_records'
    __table_args__ = (Index('ix_weight_records_pet_time', 'pet_id', 'measured_at'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pet_id: Mapped[int] = mapped_column(ForeignKey('pets.id'), nullable=False)
    weight_kg: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
