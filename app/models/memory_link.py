from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, UUIDPrimaryKeyMixin


class MemoryLink(BaseModel, UUIDPrimaryKeyMixin):
    __tablename__ = "memory_links"
    __table_args__ = (
        UniqueConstraint(
            "from_memory_id",
            "to_memory_id",
            "relation_type",
            name="uq_memory_links_from_to_relation",
        ),
        Index("ix_memory_links_from_memory", "from_memory_id"),
        Index("ix_memory_links_to_memory", "to_memory_id"),
        Index("ix_memory_links_relation_type", "relation_type"),
    )

    from_memory_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("memory_records.id", ondelete="CASCADE"),
        nullable=False,
    )
    to_memory_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("memory_records.id", ondelete="CASCADE"),
        nullable=False,
    )
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
