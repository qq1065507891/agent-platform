from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, JSONType, UUIDPrimaryKeyMixin


class MemoryOutbox(BaseModel, UUIDPrimaryKeyMixin):
    __tablename__ = "memory_outbox"

    topic: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONType, nullable=False)
    headers: Mapped[dict | None] = mapped_column(JSONType)
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fail_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


Index("ix_memory_outbox_published_created_at", MemoryOutbox.published, MemoryOutbox.created_at)
