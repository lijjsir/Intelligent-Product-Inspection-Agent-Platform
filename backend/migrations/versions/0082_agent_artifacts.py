"""agent artifacts

Revision ID: 0082
Revises: 0081
Create Date: 2026-06-22 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0082"
down_revision = "0081"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _has_table("agent_artifacts"):
        return
    op.create_table(
        "agent_artifacts",
        sa.Column("id", sa.BINARY(length=16), nullable=False),
        sa.Column("org_id", sa.BINARY(length=16), nullable=False),
        sa.Column("session_id", sa.BINARY(length=16), nullable=True),
        sa.Column("task_id", sa.BINARY(length=16), nullable=True),
        sa.Column("workflow_run_id", sa.String(length=128), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("artifact_id", sa.String(length=64), nullable=False),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("capability", sa.String(length=128), nullable=True),
        sa.Column("artifact_type", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="success"),
        sa.Column("content_json", mysql.JSON(), nullable=True),
        sa.Column("metrics_json", mysql.JSON(), nullable=True),
        sa.Column("citations_json", mysql.JSON(), nullable=True),
        sa.Column("error_json", mysql.JSON(), nullable=True),
        sa.Column("confidence", sa.Numeric(8, 6), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3)")),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_agent_artifacts_org_request", "agent_artifacts", ["org_id", "request_id"])
    op.create_index("idx_agent_artifacts_org_session", "agent_artifacts", ["org_id", "session_id"])
    op.create_index("idx_agent_artifacts_org_task", "agent_artifacts", ["org_id", "task_id"])
    op.create_index("idx_agent_artifacts_workflow", "agent_artifacts", ["workflow_run_id"])
    op.create_index("idx_agent_artifacts_agent", "agent_artifacts", ["agent_name"])
    op.create_index("idx_agent_artifacts_type", "agent_artifacts", ["artifact_type"])
    op.create_index(
        "uq_agent_artifacts_request_artifact",
        "agent_artifacts",
        ["org_id", "request_id", "artifact_id"],
        unique=True,
    )


def downgrade() -> None:
    if _has_table("agent_artifacts"):
        op.drop_table("agent_artifacts")
