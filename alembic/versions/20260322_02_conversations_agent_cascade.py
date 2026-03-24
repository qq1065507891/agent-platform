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


def upgrade() -> None:
    op.drop_constraint("conversations_agent_id_fkey", "conversations", type_="foreignkey")
    op.create_foreign_key(
        "conversations_agent_id_fkey",
        "conversations",
        "agents",
        ["agent_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("conversations_agent_id_fkey", "conversations", type_="foreignkey")
    op.create_foreign_key(
        "conversations_agent_id_fkey",
        "conversations",
        "agents",
        ["agent_id"],
        ["id"],
    )
