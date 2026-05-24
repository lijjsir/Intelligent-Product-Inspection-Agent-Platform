"""create agent ops tables for agent management, prompt management and intent routing

Revision ID: 0013_agent_ops_tables
Revises: 0012_consolidate_roles
Create Date: 2026-03-31

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0013_agent_ops_tables"
down_revision = "0012_consolidate_roles"
branch_labels = None
depends_on = None

TS_DEFAULT = sa.text("CURRENT_TIMESTAMP(3)")
TS_UPDATE_DEFAULT = sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")


def upgrade() -> None:
    op.create_table(
        "agent_definitions",
        sa.Column("id", sa.BINARY(16), nullable=False),
        sa.Column("org_id", sa.BINARY(16), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("prompt_version_id", sa.BINARY(16), nullable=True),
        sa.Column("workflow_binding", sa.String(100), nullable=True),
        sa.Column("intent_config_id", sa.BINARY(16), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="Agent definitions for workflow orchestration",
    )
    op.create_index("idx_org_name", "agent_definitions", ["org_id", "name"])
    op.create_index("idx_org_active", "agent_definitions", ["org_id", "is_active"])

    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.BINARY(16), nullable=False),
        sa.Column("org_id", sa.BINARY(16), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("created_by", sa.BINARY(16), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="Prompt version management for agent configuration",
    )
    op.create_index("idx_org_name_version", "prompt_versions", ["org_id", "name", "version"])
    op.create_index("idx_org_status", "prompt_versions", ["org_id", "status"])

    op.create_table(
        "intent_routes",
        sa.Column("id", sa.BINARY(16), nullable=False),
        sa.Column("org_id", sa.BINARY(16), nullable=False),
        sa.Column("intent_name", sa.String(100), nullable=False),
        sa.Column("agent_id", sa.BINARY(16), nullable=True),
        sa.Column("priority", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("sample_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="Intent routing configuration for agent dispatch",
    )
    op.create_index("idx_org_intent", "intent_routes", ["org_id", "intent_name"])
    op.create_index("idx_org_active_priority", "intent_routes", ["org_id", "is_active", "priority"])


def downgrade() -> None:
    op.drop_index("idx_org_active_priority", "intent_routes")
    op.drop_index("idx_org_intent", "intent_routes")
    op.drop_table("intent_routes")

    op.drop_index("idx_org_status", "prompt_versions")
    op.drop_index("idx_org_name_version", "prompt_versions")
    op.drop_table("prompt_versions")

    op.drop_index("idx_org_active", "agent_definitions")
    op.drop_index("idx_org_name", "agent_definitions")
    op.drop_table("agent_definitions")
