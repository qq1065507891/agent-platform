from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class MemoryEmbedding(BaseModel):
    __tablename__ = "memory_embeddings"
    __table_args__ = (
        Index("ix_memory_embeddings_model", "model"),
        Index("ix_memory_embeddings_created_at", "created_at"),
    )

    memory_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("memory_records.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(1024), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False, default=1024)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
