"""add roles and permission grants

Revision ID: 20260319_02
Revises: 20260319_01
Create Date: 2026-03-19 00:10:00

"""
from __future__ import annotations

from alembic import op


revision = "20260319_02"
down_revision = "20260319_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS roles (
            id VARCHAR(36) PRIMARY KEY,
            name VARCHAR(64) NOT NULL UNIQUE,
            permissions JSON NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_roles_name ON roles (name)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS permission_grants (
            id VARCHAR(36) PRIMARY KEY,
            subject_type VARCHAR(16) NOT NULL,
            subject_id VARCHAR(36) NOT NULL,
            object_type VARCHAR(16) NOT NULL,
            object_id VARCHAR(36) NOT NULL,
            actions JSON NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_permission_grants_subject_id ON permission_grants (subject_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_permission_grants_object_id ON permission_grants (object_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS permission_grants")
    op.execute("DROP TABLE IF EXISTS roles")
