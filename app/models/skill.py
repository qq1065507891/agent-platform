from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, JSONType, UUIDPrimaryKeyMixin


class Skill(BaseModel, UUIDPrimaryKeyMixin):
    __tablename__ = "skills"

    skill_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    author: Mapped[str | None] = mapped_column(String(100))
    yaml_definition: Mapped[dict | None] = mapped_column(JSONType)
    inputs_schema: Mapped[dict | None] = mapped_column(JSONType)
    outputs_schema: Mapped[dict | None] = mapped_column(JSONType)
    execution_config: Mapped[dict | None] = mapped_column(JSONType)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_version: Mapped[str | None] = mapped_column(String(100))
    checksum: Mapped[str | None] = mapped_column(String(128))
    installed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dependency_lock: Mapped[dict | None] = mapped_column(JSONType)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True, default="active")
