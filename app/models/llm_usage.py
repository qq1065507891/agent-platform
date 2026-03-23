from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, UUIDPrimaryKeyMixin


class LLMUsage(BaseModel, UUIDPrimaryKeyMixin):
    __tablename__ = "llm_usage"

    user_id: Mapped[str | None] = mapped_column(String(36))
    agent_id: Mapped[str | None] = mapped_column(String(36))
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(64))
    conversation_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
