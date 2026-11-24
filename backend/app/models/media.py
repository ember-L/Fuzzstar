"""Uploaded media bookkeeping."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MediaUpload(Base):
    __tablename__ = 'media_uploads'

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    pet_id: Mapped[int] = mapped_column(ForeignKey('pets.id'), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(8), default='photo', server_default='photo', nullable=False)
    content_type: Mapped[str] = mapped_column(String(16), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    version_id: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    @property
    def object_key(self) -> str:
        prefix = 'videos' if self.kind == 'video' else 'audio' if self.kind == 'audio' else 'photos'
        return f'{prefix}/{self.pet_id}/{self.id}'
