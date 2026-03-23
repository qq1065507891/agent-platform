from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, JSONType, UUIDPrimaryKeyMixin


class Conversation(BaseModel, UUIDPrimaryKeyMixin):
    __tablename__ = "conversations"

    agent_id: Mapped[str] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(120))
    messages: Mapped[list | None] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    agent = relationship("Agent", back_populates="conversations")
    user = relationship("User", back_populates="conversations")
