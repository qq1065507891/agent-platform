"""memory v3 pgvector schema

Revision ID: 20260324_01
Revises: 20260323_07
Create Date: 2026-03-24 00:00:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


revision = "20260324_01"
down_revision = "20260323_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "memory_records",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36)),
        sa.Column("conversation_id", sa.String(length=36)),
        sa.Column("source_message_id", sa.String(length=36)),
        sa.Column("memory_type", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_norm", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("consistency_level", sa.String(length=16), nullable=False, server_default="strong"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_memory_records_idempotency_key"),
    )
    op.create_index(
        "ix_memory_records_user_agent_created_at",
        "memory_records",
        ["user_id", "agent_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_memory_records_user_agent_memory_type",
        "memory_records",
        ["user_id", "agent_id", "memory_type"],
        unique=False,
    )
    op.create_index(
        "ix_memory_records_conversation_status_updated_at",
        "memory_records",
        ["conversation_id", "status", "updated_at"],
        unique=False,
    )

    op.create_table(
        "memory_embeddings",
        sa.Column("memory_id", sa.String(length=36), nullable=False),
        sa.Column("embedding", Vector(dim=1536), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False, server_default="1536"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["memory_id"], ["memory_records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("memory_id"),
    )
    op.create_index("ix_memory_embeddings_model", "memory_embeddings", ["model"], unique=False)
    op.create_index("ix_memory_embeddings_created_at", "memory_embeddings", ["created_at"], unique=False)

    op.create_table(
        "memory_links",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("from_memory_id", sa.String(length=36), nullable=False),
        sa.Column("to_memory_id", sa.String(length=36), nullable=False),
        sa.Column("relation_type", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["from_memory_id"], ["memory_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_memory_id"], ["memory_records.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("from_memory_id", "to_memory_id", "relation_type", name="uq_memory_links_from_to_relation"),
    )
    op.create_index("ix_memory_links_from_memory", "memory_links", ["from_memory_id"], unique=False)
    op.create_index("ix_memory_links_to_memory", "memory_links", ["to_memory_id"], unique=False)
    op.create_index("ix_memory_links_relation_type", "memory_links", ["relation_type"], unique=False)

    op.create_table(
        "memory_write_audits",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(length=36)),
        sa.Column("agent_id", sa.String(length=36)),
        sa.Column("conversation_id", sa.String(length=36)),
        sa.Column("trace_id", sa.String(length=64)),
        sa.Column("request_id", sa.String(length=64)),
        sa.Column("idempotency_key", sa.String(length=128)),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("error_code", sa.String(length=64)),
        sa.Column("error_message", sa.Text()),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("metadata", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_memory_write_audits_trace_id", "memory_write_audits", ["trace_id"], unique=False)
    op.create_index(
        "ix_memory_write_audits_conversation_created",
        "memory_write_audits",
        ["conversation_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_memory_write_audits_status_created",
        "memory_write_audits",
        ["status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_memory_write_audits_idempotency_key",
        "memory_write_audits",
        ["idempotency_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_memory_write_audits_idempotency_key", table_name="memory_write_audits")
    op.drop_index("ix_memory_write_audits_status_created", table_name="memory_write_audits")
    op.drop_index("ix_memory_write_audits_conversation_created", table_name="memory_write_audits")
    op.drop_index("ix_memory_write_audits_trace_id", table_name="memory_write_audits")
    op.drop_table("memory_write_audits")

    op.drop_index("ix_memory_links_relation_type", table_name="memory_links")
    op.drop_index("ix_memory_links_to_memory", table_name="memory_links")
    op.drop_index("ix_memory_links_from_memory", table_name="memory_links")
    op.drop_table("memory_links")

    op.drop_index("ix_memory_embeddings_created_at", table_name="memory_embeddings")
    op.drop_index("ix_memory_embeddings_model", table_name="memory_embeddings")
    op.drop_table("memory_embeddings")

    op.drop_index("ix_memory_records_conversation_status_updated_at", table_name="memory_records")
    op.drop_index("ix_memory_records_user_agent_memory_type", table_name="memory_records")
    op.drop_index("ix_memory_records_user_agent_created_at", table_name="memory_records")
    op.drop_table("memory_records")
