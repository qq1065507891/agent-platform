"""add timestamps to skills

Revision ID: 20260324_02
Revises: 20260324_01
Create Date: 2026-03-24 00:00:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260324_02"
down_revision = "20260324_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "skills",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.add_column(
        "skills",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.alter_column("skills", "created_at", server_default=None)
    op.alter_column("skills", "updated_at", server_default=None)


def downgrade() -> None:
    op.drop_column("skills", "updated_at")
    op.drop_column("skills", "created_at")
