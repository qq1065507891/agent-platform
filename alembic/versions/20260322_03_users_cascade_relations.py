"""set cascade delete for agents.owner_id and conversations.user_id

Revision ID: 20260322_03
Revises: 20260322_02
Create Date: 2026-03-22 13:25:00

"""
from __future__ import annotations

from alembic import op


revision = "20260322_03"
down_revision = "20260322_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("agents_owner_id_fkey", "agents", type_="foreignkey")
    op.create_foreign_key(
        "agents_owner_id_fkey",
        "agents",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint("conversations_user_id_fkey", "conversations", type_="foreignkey")
    op.create_foreign_key(
        "conversations_user_id_fkey",
        "conversations",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("conversations_user_id_fkey", "conversations", type_="foreignkey")
    op.create_foreign_key(
        "conversations_user_id_fkey",
        "conversations",
        "users",
        ["user_id"],
        ["id"],
    )

    op.drop_constraint("agents_owner_id_fkey", "agents", type_="foreignkey")
    op.create_foreign_key(
        "agents_owner_id_fkey",
        "agents",
        "users",
        ["owner_id"],
        ["id"],
    )
