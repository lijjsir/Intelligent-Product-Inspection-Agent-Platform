"""create agent management tables for metrics and version control

Revision ID: 0014_agent_management_tables
Revises: 0013_agent_ops_tables
Create Date: 2026-04-01

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0014_agent_management_tables"
down_revision = "0013_agent_ops_tables"
branch_labels = None
depends_on = None

TS_DEFAULT = sa.text("CURRENT_TIMESTAMP(3)")
TS_UPDATE_DEFAULT = sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")


def upgrade() -> None:
    op.create_table(
        "agent_execution_metrics",
        sa.Column("id", sa.BINARY(16), nullable=False),
        sa.Column("org_id", sa.BINARY(16), nullable=False),
        sa.Column("agent_id", sa.BINARY(16), nullable=False),
        sa.Column("execution_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("success_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("total_latency_ms", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("last_executed_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="Agent execution performance metrics",
    )
    op.create_index("idx_org_agent_id", "agent_execution_metrics", ["org_id", "agent_id"])

    op.create_table(
        "agent_config_versions",
        sa.Column("id", sa.BINARY(16), nullable=False),
        sa.Column("org_id", sa.BINARY(16), nullable=False),
        sa.Column("agent_id", sa.BINARY(16), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("config_snapshot", mysql.JSON, nullable=False),
        sa.Column("created_by", sa.BINARY(16), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="Agent configuration version history",
    )
    op.create_index("idx_org_agent_version", "agent_config_versions", ["org_id", "agent_id", "version"])

    # Add foreign key constraint for agent_config_versions.agent_id
    op.create_foreign_key(
        "fk_agent_config_versions_agent_id",
        "agent_config_versions",
        "agent_definitions",
        ["agent_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Add current_version column to agent_definitions
    op.add_column("agent_definitions", sa.Column("current_version", sa.Integer, nullable=False, server_default=sa.text("1")))


def downgrade() -> None:
    # Drop foreign key constraint first
    op.drop_constraint("fk_agent_config_versions_agent_id", "agent_config_versions", type_="foreignkey")
    op.drop_column("agent_definitions", "current_version")
    op.drop_index("idx_org_agent_version", "agent_config_versions")
    op.drop_table("agent_config_versions")
    op.drop_index("idx_org_agent_id", "agent_execution_metrics")
    op.drop_table("agent_execution_metrics")
