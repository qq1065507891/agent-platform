"""add title column to conversations

Revision ID: 20260322_04
Revises: 20260322_03
Create Date: 2026-03-22 14:00:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260322_04"
down_revision = "20260322_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("title", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("conversations", "title")
