from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, TimestampMixin, UUIDPrimaryKeyMixin


class User(BaseModel, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    agents = relationship(
        "Agent", back_populates="owner", cascade="all, delete-orphan", passive_deletes=True
    )
    conversations = relationship(
        "Conversation", back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
