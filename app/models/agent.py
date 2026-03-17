from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, JSONType, TimestampMixin, UUIDPrimaryKeyMixin


class Agent(BaseModel, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "agents"

    name: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(200))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    prompt_template: Mapped[str] = mapped_column(String(4000), nullable=False)
    skills: Mapped[list | None] = mapped_column(JSONType, nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)

    owner = relationship("User", back_populates="agents")
    conversations = relationship("Conversation", back_populates="agent")
