"""add conversation_id for observability tables

Revision ID: 20260322_01
Revises: 20260320_01
Create Date: 2026-03-22 10:00:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260322_01"
down_revision = "20260320_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("llm_usage", sa.Column("conversation_id", sa.String(length=36), nullable=True))
    op.add_column("skill_invocations", sa.Column("conversation_id", sa.String(length=36), nullable=True))
    op.add_column("event_logs", sa.Column("conversation_id", sa.String(length=36), nullable=True))


def downgrade() -> None:
    op.drop_column("event_logs", "conversation_id")
    op.drop_column("skill_invocations", "conversation_id")
    op.drop_column("llm_usage", "conversation_id")
