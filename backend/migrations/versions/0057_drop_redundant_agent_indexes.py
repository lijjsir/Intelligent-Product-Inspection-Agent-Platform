"""drop redundant composite agent indexes

Revision ID: 0057
Revises: 0056
Create Date: 2026-05-23 03:37:27.902609
"""

from alembic import op

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index(op.f("idx_org_agent_version"), table_name="agent_config_versions")
    op.drop_index(op.f("idx_org_agent_id"), table_name="agent_execution_metrics")


def downgrade():
    op.create_index(
        op.f("idx_org_agent_id"),
        "agent_execution_metrics",
        ["org_id", "agent_id"],
        unique=False,
    )
    op.create_index(
        op.f("idx_org_agent_version"),
        "agent_config_versions",
        ["org_id", "agent_id", "version"],
        unique=False,
    )
