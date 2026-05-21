"""recreate_agent_execution_metrics_and_config_versions

Revision ID: 0047
Revises: 0046
Create Date: 2026-05-22 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

from app.models.base import UUIDBinary

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_execution_metrics",
        sa.Column("id", UUIDBinary(length=16), nullable=False),
        sa.Column("org_id", UUIDBinary(length=16), nullable=False),
        sa.Column("agent_id", UUIDBinary(length=16), nullable=False),
        sa.Column("execution_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_executed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_execution_metrics_org_id"), "agent_execution_metrics", ["org_id"], unique=False)
    op.create_index(op.f("ix_agent_execution_metrics_agent_id"), "agent_execution_metrics", ["agent_id"], unique=False)
    op.create_index("idx_org_agent_id", "agent_execution_metrics", ["org_id", "agent_id"], unique=False)

    op.create_table(
        "agent_config_versions",
        sa.Column("id", UUIDBinary(length=16), nullable=False),
        sa.Column("org_id", UUIDBinary(length=16), nullable=False),
        sa.Column("agent_id", UUIDBinary(length=16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("config_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_by", UUIDBinary(length=16), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_config_versions_org_id"), "agent_config_versions", ["org_id"], unique=False)
    op.create_index(op.f("ix_agent_config_versions_agent_id"), "agent_config_versions", ["agent_id"], unique=False)
    op.create_index("idx_org_agent_version", "agent_config_versions", ["org_id", "agent_id", "version"], unique=False)


def downgrade():
    op.drop_table("agent_config_versions")
    op.drop_table("agent_execution_metrics")
