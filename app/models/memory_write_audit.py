from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, JSONType, UUIDPrimaryKeyMixin


class MemoryWriteAudit(BaseModel, UUIDPrimaryKeyMixin):
    __tablename__ = "memory_write_audits"
    __table_args__ = (
        Index("ix_memory_write_audits_trace_id", "trace_id"),
        Index("ix_memory_write_audits_conversation_created", "conversation_id", "created_at"),
        Index("ix_memory_write_audits_status_created", "status", "created_at"),
        Index("ix_memory_write_audits_idempotency_key", "idempotency_key"),
    )

    user_id: Mapped[str | None] = mapped_column(String(36))
    agent_id: Mapped[str | None] = mapped_column(String(36))
    conversation_id: Mapped[str | None] = mapped_column(String(36))

    trace_id: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(64))
    idempotency_key: Mapped[str | None] = mapped_column(String(128))

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)

    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer)

    meta: Mapped[dict | None] = mapped_column("metadata", JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
