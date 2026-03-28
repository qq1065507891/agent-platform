from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, UUIDPrimaryKeyMixin


class MemoryRecord(BaseModel, UUIDPrimaryKeyMixin):
    __tablename__ = "memory_records"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_memory_records_idempotency_key"),
        Index(
            "ix_memory_records_user_agent_created_at",
            "user_id",
            "agent_id",
            "created_at",
        ),
        Index(
            "ix_memory_records_user_agent_memory_type",
            "user_id",
            "agent_id",
            "memory_type",
        ),
        Index(
            "ix_memory_records_conversation_status_updated_at",
            "conversation_id",
            "status",
            "updated_at",
        ),
    )

    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(String(36))
    conversation_id: Mapped[str | None] = mapped_column(String(36))
    source_message_id: Mapped[str | None] = mapped_column(String(36))

    memory_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_norm: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)

    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    consistency_level: Mapped[str] = mapped_column(String(16), nullable=False, default="strong")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
