"""Admin console audit trail.

Every mutating admin action writes one row so operations stay attributable even
when several people share the console. The admin email and nickname are
snapshotted so the trail survives the admin account itself being deleted.
Detail stays JSON so new actions do not need a schema change.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AdminAuditLog(Base):
    __tablename__ = 'admin_audit_logs'
    __table_args__ = (Index('ix_admin_audit_logs_created_at', 'created_at'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    admin_email: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    admin_nickname: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    target_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    detail: Mapped[Optional[dict]] = mapped_column(JSON(none_as_null=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
