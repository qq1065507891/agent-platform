from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, JSONType, UUIDPrimaryKeyMixin


class MemoryItemModel(BaseModel, UUIDPrimaryKeyMixin):
    __tablename__ = "memory_items"

    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(String(36))
    memory_type: Mapped[str] = mapped_column(String(32), nullable=False)
    consistency_level: Mapped[str] = mapped_column(String(16), nullable=False, default="eventual")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="user")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_content: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    supersedes_memory_id: Mapped[str | None] = mapped_column(String(36))
    ttl_seconds: Mapped[int | None] = mapped_column(Integer)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tags: Mapped[dict | None] = mapped_column(JSONType)
    created_by_event_id: Mapped[str | None] = mapped_column(String(36))
    trace_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


Index(
    "ix_memory_items_user_agent_type_state_updated_at",
    MemoryItemModel.user_id,
    MemoryItemModel.agent_id,
    MemoryItemModel.memory_type,
    MemoryItemModel.state,
    MemoryItemModel.updated_at,
)
Index("ix_memory_items_user_state", MemoryItemModel.user_id, MemoryItemModel.state)
