"""add tool_definitions, tool_versions, agent_tool_bindings tables

Revision ID: 0042
Revises: 0041
Create Date: 2026-05-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql
from sqlalchemy.dialects.mysql import JSON, BINARY

revision: str = "0042"
down_revision: Union[str, None] = "0041"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── tool_definitions ──
    op.create_table(
        "tool_definitions",
        sa.Column("id", BINARY(16), primary_key=True),
        sa.Column("org_id", BINARY(16), nullable=True),
        sa.Column("tool_key", sa.String(160), nullable=False),
        sa.Column("display_name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("tool_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("risk_level", sa.String(32), nullable=False, server_default="low"),
        sa.Column("is_readonly", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("source_type", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("source_ref", sa.String(512), nullable=True),
        sa.Column("manifest_hash", sa.String(64), nullable=True),
        sa.Column("active_version_id", BINARY(16), nullable=True),
        sa.Column("health_status", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("last_checked_at", sa.DateTime, nullable=True),
        sa.Column("created_by", BINARY(16), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3)")),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.UniqueConstraint("org_id", "tool_key", name="uk_org_tool_key"),
    )

    # ── tool_versions ──
    op.create_table(
        "tool_versions",
        sa.Column("id", BINARY(16), primary_key=True),
        sa.Column("org_id", BINARY(16), nullable=True),
        sa.Column("tool_id", BINARY(16), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("display_name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("endpoint", sa.String(512), nullable=True),
        sa.Column("method", sa.String(16), nullable=True),
        sa.Column("handler_path", sa.String(256), nullable=True),
        sa.Column("parameters_schema", JSON, nullable=False),
        sa.Column("returns_schema", JSON, nullable=False),
        sa.Column("auth_type", sa.String(32), nullable=False, server_default="none"),
        sa.Column("secret_ref", sa.String(256), nullable=True),
        sa.Column("timeout_ms", sa.Integer, nullable=False, server_default="30000"),
        sa.Column("retry_policy", JSON, nullable=True),
        sa.Column("rate_limit_rpm", sa.Integer, nullable=False, server_default="60"),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("created_by", BINARY(16), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3)")),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")),
        sa.UniqueConstraint("org_id", "tool_id", "version", name="uk_tool_version"),
    )

    # ── agent_tool_bindings ──
    op.create_table(
        "agent_tool_bindings",
        sa.Column("id", BINARY(16), primary_key=True),
        sa.Column("org_id", BINARY(16), nullable=False),
        sa.Column("agent_id", BINARY(16), nullable=False),
        sa.Column("tool_id", BINARY(16), nullable=False),
        sa.Column("tool_version_id", BINARY(16), nullable=False),
        sa.Column("binding_status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("allowed_intents", JSON, nullable=True),
        sa.Column("approval_required", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("auto_call_enabled", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3)")),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")),
        sa.UniqueConstraint("org_id", "agent_id", "tool_id", name="uk_agent_tool"),
    )


def downgrade() -> None:
    op.drop_table("agent_tool_bindings")
    op.drop_table("tool_versions")
    op.drop_table("tool_definitions")
