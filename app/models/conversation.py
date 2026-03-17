from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, JSONType, UUIDPrimaryKeyMixin


class Conversation(BaseModel, UUIDPrimaryKeyMixin):
    __tablename__ = "conversations"

    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    messages: Mapped[list | None] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    agent = relationship("Agent", back_populates="conversations")
    user = relationship("User", back_populates="conversations")
