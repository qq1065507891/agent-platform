"""industrial memory platform tables

Revision ID: 20260323_07
Revises: 20260322_05
Create Date: 2026-03-23 00:00:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260323_07"
down_revision = "20260322_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memory_events",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=36)),
        sa.Column("agent_id", sa.String(length=36)),
        sa.Column("conversation_id", sa.String(length=36)),
        sa.Column("trace_id", sa.String(length=64)),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="created"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(length=64)),
        sa.Column("error_message", sa.Text()),
        sa.Column("payload", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_memory_events_status_next_retry_at",
        "memory_events",
        ["status", "next_retry_at"],
        unique=False,
    )
    op.create_index("ix_memory_events_trace_id", "memory_events", ["trace_id"], unique=False)
    op.create_index(
        "ix_memory_events_conversation_id_created_at",
        "memory_events",
        ["conversation_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "memory_items",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36)),
        sa.Column("memory_type", sa.String(length=32), nullable=False),
        sa.Column("consistency_level", sa.String(length=16), nullable=False, server_default="eventual"),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="user"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("normalized_content", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("supersedes_memory_id", sa.String(length=36)),
        sa.Column("ttl_seconds", sa.Integer()),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("tags", sa.JSON()),
        sa.Column("created_by_event_id", sa.String(length=36)),
        sa.Column("trace_id", sa.String(length=64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_memory_items_user_agent_type_state_updated_at",
        "memory_items",
        ["user_id", "agent_id", "memory_type", "state", "updated_at"],
        unique=False,
    )
    op.create_index("ix_memory_items_user_state", "memory_items", ["user_id", "state"], unique=False)

    op.create_table(
        "memory_outbox",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("topic", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("headers", sa.JSON()),
        sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("fail_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_memory_outbox_published_created_at",
        "memory_outbox",
        ["published", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_memory_outbox_published_created_at", table_name="memory_outbox")
    op.drop_table("memory_outbox")

    op.drop_index("ix_memory_items_user_state", table_name="memory_items")
    op.drop_index("ix_memory_items_user_agent_type_state_updated_at", table_name="memory_items")
    op.drop_table("memory_items")

    op.drop_index("ix_memory_events_conversation_id_created_at", table_name="memory_events")
    op.drop_index("ix_memory_events_trace_id", table_name="memory_events")
    op.drop_index("ix_memory_events_status_next_retry_at", table_name="memory_events")
    op.drop_table("memory_events")
