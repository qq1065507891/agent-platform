from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, JSONType, TimestampMixin, UUIDPrimaryKeyMixin


class Skill(BaseModel, UUIDPrimaryKeyMixin, TimestampMixin):
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
    current_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("external_skill_revisions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True, default="active")

    revisions: Mapped[list["ExternalSkillRevision"]] = relationship(
        "ExternalSkillRevision",
        back_populates="skill",
        cascade="all, delete-orphan",
        foreign_keys="ExternalSkillRevision.skill_id",
    )
    current_revision: Mapped["ExternalSkillRevision | None"] = relationship(
        "ExternalSkillRevision",
        foreign_keys=[current_revision_id],
    )


class ExternalSkillRevision(BaseModel, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "external_skill_revisions"

    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[str | None] = mapped_column(String(100))
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    code_content: Mapped[str] = mapped_column(Text, nullable=False)
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    expected_hash: Mapped[str | None] = mapped_column(String(128))
    hash_verified: Mapped[bool] = mapped_column(default=False, nullable=False)
    scan_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    scan_report: Mapped[dict | None] = mapped_column(JSONType)
    sandbox_policy: Mapped[dict | None] = mapped_column(JSONType)
    load_task_id: Mapped[str | None] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text)

    skill: Mapped[Skill] = relationship("Skill", back_populates="revisions", foreign_keys=[skill_id])
