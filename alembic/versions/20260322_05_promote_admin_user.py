"""promote admin account role to admin

Revision ID: 20260322_05
Revises: 20260322_04
Create Date: 2026-03-22 14:20:00

"""
from __future__ import annotations

from alembic import op


revision = "20260322_05"
down_revision = "20260322_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE users
        SET role = 'admin'
        WHERE username = 'admin';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE users
        SET role = 'user'
        WHERE username = 'admin' AND role = 'admin';
        """
    )
