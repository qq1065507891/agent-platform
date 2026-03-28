"""align memory embedding dimension to 1024

Revision ID: 20260324_03
Revises: 20260324_02
Create Date: 2026-03-24 00:30:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260324_03"
down_revision = "20260324_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE memory_embeddings ALTER COLUMN embedding TYPE vector(1024) USING subvector(embedding, 1, 1024)")
    op.alter_column("memory_embeddings", "dim", existing_type=sa.Integer(), server_default="1024")


def downgrade() -> None:
    op.execute("ALTER TABLE memory_embeddings ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector(1536)")
    op.alter_column("memory_embeddings", "dim", existing_type=sa.Integer(), server_default="1536")
