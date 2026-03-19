"""init schema

Revision ID: 20260319_01
Revises: 
Create Date: 2026-03-19 00:00:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260319_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False, unique=True),
        sa.Column("email", sa.String(length=128), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "roles",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False),
    )
    op.create_index("ix_roles_name", "roles", ["name"], unique=True)

    op.create_table(
        "permission_grants",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("subject_type", sa.String(length=16), nullable=False),
        sa.Column("subject_id", sa.String(length=36), nullable=False),
        sa.Column("object_type", sa.String(length=16), nullable=False),
        sa.Column("object_id", sa.String(length=36), nullable=False),
        sa.Column("actions", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_permission_grants_subject_id", "permission_grants", ["subject_id"], unique=False)
    op.create_index("ix_permission_grants_object_id", "permission_grants", ["object_id"], unique=False)

    op.create_table(
        "agents",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=255)),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("prompt_template", sa.Text(), nullable=False),
        sa.Column("skills", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agents_owner_id", "agents", ["owner_id"], unique=False)

    op.create_table(
        "conversations",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("messages", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"], unique=False)
    op.create_index("ix_conversations_agent_id", "conversations", ["agent_id"], unique=False)

    op.create_table(
        "skills",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("skill_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=255)),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("author", sa.String(length=128)),
        sa.Column("yaml_definition", sa.JSON(), nullable=False),
        sa.Column("inputs_schema", sa.JSON()),
        sa.Column("outputs_schema", sa.JSON()),
        sa.Column("execution_config", sa.JSON()),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_url", sa.String(length=255)),
        sa.Column("source_version", sa.String(length=64)),
        sa.Column("checksum", sa.String(length=128)),
        sa.Column("installed_at", sa.DateTime(timezone=True)),
        sa.Column("dependency_lock", sa.JSON()),
        sa.Column("status", sa.String(length=16), nullable=False),
    )
    op.create_index("ix_skills_category", "skills", ["category"], unique=False)
    op.create_index("ix_skills_source_type", "skills", ["source_type"], unique=False)
    op.create_index("ix_skills_status", "skills", ["status"], unique=False)

    op.create_table(
        "event_logs",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("user_id", sa.String(length=36)),
        sa.Column("agent_id", sa.String(length=36)),
        sa.Column("metadata", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "request_logs",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("path", sa.String(length=255), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("trace_id", sa.String(length=64)),
        sa.Column("user_id", sa.String(length=36)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "llm_usage",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(length=36)),
        sa.Column("agent_id", sa.String(length=36)),
        sa.Column("model", sa.String(length=64)),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("cost", sa.Float()),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("trace_id", sa.String(length=64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "skill_invocations",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("skill_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=36)),
        sa.Column("agent_id", sa.String(length=36)),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("error_code", sa.String(length=32)),
        sa.Column("trace_id", sa.String(length=64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("skill_invocations")
    op.drop_table("llm_usage")
    op.drop_table("request_logs")
    op.drop_table("event_logs")
    op.drop_index("ix_skills_status", table_name="skills")
    op.drop_index("ix_skills_source_type", table_name="skills")
    op.drop_index("ix_skills_category", table_name="skills")
    op.drop_table("skills")
    op.drop_index("ix_conversations_agent_id", table_name="conversations")
    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.drop_table("conversations")
    op.drop_index("ix_agents_owner_id", table_name="agents")
    op.drop_table("agents")
    op.drop_index("ix_permission_grants_object_id", table_name="permission_grants")
    op.drop_index("ix_permission_grants_subject_id", table_name="permission_grants")
    op.drop_table("permission_grants")
    op.drop_index("ix_roles_name", table_name="roles")
    op.drop_table("roles")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
