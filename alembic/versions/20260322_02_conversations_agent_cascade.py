"""set cascade delete for conversations.agent_id -> agents.id

Revision ID: 20260322_02
Revises: 20260322_01
Create Date: 2026-03-22 13:10:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260322_02"
down_revision = "20260322_01"
branch_labels = None
depends_on = None


def _drop_fk_if_exists(table_name: str, constraint_name: str) -> None:
    op.execute(sa.text(f'ALTER TABLE {table_name} DROP CONSTRAINT IF EXISTS {constraint_name}'))


def upgrade() -> None:
    _drop_fk_if_exists("conversations", "conversations_agent_id_fkey")
    op.create_foreign_key(
        "conversations_agent_id_fkey",
        "conversations",
        "agents",
        ["agent_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    _drop_fk_if_exists("conversations", "conversations_agent_id_fkey")
    op.create_foreign_key(
        "conversations_agent_id_fkey",
        "conversations",
        "agents",
        ["agent_id"],
        ["id"],
    )
