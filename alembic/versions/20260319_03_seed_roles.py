"""seed default roles

Revision ID: 20260319_03
Revises: 20260319_02
Create Date: 2026-03-19 02:00:00

"""
from __future__ import annotations

from alembic import op


revision = "20260319_03"
down_revision = "20260319_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO roles (id, name, permissions)
        SELECT gen_random_uuid()::text, 'admin',
               '["agent:create","agent:publish","agent:manage","skill:manage","user:manage","role:manage","permission:grant"]'
        WHERE NOT EXISTS (SELECT 1 FROM roles WHERE name = 'admin');
        """
    )
    op.execute(
        """
        INSERT INTO roles (id, name, permissions)
        SELECT gen_random_uuid()::text, 'manager',
               '["agent:create","agent:publish","skill:manage","user:manage"]'
        WHERE NOT EXISTS (SELECT 1 FROM roles WHERE name = 'manager');
        """
    )
    op.execute(
        """
        INSERT INTO roles (id, name, permissions)
        SELECT gen_random_uuid()::text, 'user',
               '["agent:use"]'
        WHERE NOT EXISTS (SELECT 1 FROM roles WHERE name = 'user');
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM roles WHERE name IN ('admin','manager','user')")
