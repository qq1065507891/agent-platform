"""add external skill revisions and current revision pointer

Revision ID: 20260320_01
Revises: 20260319_03
Create Date: 2026-03-20 10:00:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260320_01"
down_revision = "20260319_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_skill_revisions",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("skill_id", sa.String(length=36), sa.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=True),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("code_content", sa.Text(), nullable=False),
        sa.Column("code_hash", sa.String(length=128), nullable=False),
        sa.Column("expected_hash", sa.String(length=128), nullable=True),
        sa.Column("hash_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("scan_status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("scan_report", sa.JSON(), nullable=True),
        sa.Column("sandbox_policy", sa.JSON(), nullable=True),
        sa.Column("load_task_id", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_external_skill_revisions_skill_id", "external_skill_revisions", ["skill_id"], unique=False)
    op.create_index("ix_external_skill_revisions_code_hash", "external_skill_revisions", ["code_hash"], unique=False)
    op.create_index("ix_external_skill_revisions_load_task_id", "external_skill_revisions", ["load_task_id"], unique=False)
    op.create_index("ix_external_skill_revisions_status", "external_skill_revisions", ["status"], unique=False)

    op.add_column("skills", sa.Column("current_revision_id", sa.String(length=36), nullable=True))
    op.create_index("ix_skills_current_revision_id", "skills", ["current_revision_id"], unique=False)
    op.create_foreign_key(
        "fk_skills_current_revision_id_external_skill_revisions",
        source_table="skills",
        referent_table="external_skill_revisions",
        local_cols=["current_revision_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_skills_current_revision_id_external_skill_revisions", "skills", type_="foreignkey")
    op.drop_index("ix_skills_current_revision_id", table_name="skills")
    op.drop_column("skills", "current_revision_id")

    op.drop_index("ix_external_skill_revisions_status", table_name="external_skill_revisions")
    op.drop_index("ix_external_skill_revisions_load_task_id", table_name="external_skill_revisions")
    op.drop_index("ix_external_skill_revisions_code_hash", table_name="external_skill_revisions")
    op.drop_index("ix_external_skill_revisions_skill_id", table_name="external_skill_revisions")
    op.drop_table("external_skill_revisions")
