from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, UUIDPrimaryKeyMixin


class SkillInvocation(BaseModel, UUIDPrimaryKeyMixin):
    __tablename__ = "skill_invocations"

    skill_id: Mapped[str] = mapped_column(String(50), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(36))
    agent_id: Mapped[str | None] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(32))
    trace_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
