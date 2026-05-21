"""tool_registry v2 — add category/tool_type/status/risk_level/source_type/health_status/manifest_hash columns;
extend tool_executions with agent_id/trace_id/execution_type/input_redacted/output_redacted

Revision ID: 0041
Revises: 0040
Create Date: 2026-05-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import JSON, BINARY

revision: str = "0041"
down_revision: Union[str, None] = "0040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── tool_registry new columns ──
    op.add_column("tool_registry", sa.Column("category", sa.String(64), nullable=False, server_default="inspection_calc"))
    op.add_column("tool_registry", sa.Column("tool_type", sa.String(32), nullable=False, server_default="native"))
    op.add_column("tool_registry", sa.Column("status", sa.String(32), nullable=False, server_default="active"))
    op.add_column("tool_registry", sa.Column("risk_level", sa.String(32), nullable=False, server_default="low"))
    op.add_column("tool_registry", sa.Column("source_type", sa.String(32), nullable=False, server_default="manual"))
    op.add_column("tool_registry", sa.Column("health_status", sa.String(32), nullable=False, server_default="unknown"))
    op.add_column("tool_registry", sa.Column("manifest_hash", sa.String(64), nullable=True))

    # Migrate existing data: is_active -> status, is_readonly affects risk_level
    op.execute("UPDATE tool_registry SET status = CASE WHEN is_active = 1 THEN 'active' ELSE 'disabled' END")
    op.execute("UPDATE tool_registry SET risk_level = CASE WHEN is_readonly = 1 THEN 'low' ELSE 'medium' END")

    # Drop old server_defaults and set new ones (MySQL compatible)
    op.alter_column("tool_registry", "status", existing_type=sa.String(32), server_default=None, nullable=False)
    op.execute("ALTER TABLE tool_registry ALTER COLUMN status SET DEFAULT 'active'")
    op.execute("ALTER TABLE tool_registry ALTER COLUMN risk_level SET DEFAULT 'low'")
    op.execute("ALTER TABLE tool_registry ALTER COLUMN source_type SET DEFAULT 'manual'")

    # ── tool_executions new columns ──
    op.add_column("tool_executions", sa.Column("agent_id", BINARY(16), nullable=True))
    op.add_column("tool_executions", sa.Column("trace_id", sa.String(128), nullable=True))
    op.add_column("tool_executions", sa.Column("execution_type", sa.String(32), nullable=False, server_default="runtime"))
    op.add_column("tool_executions", sa.Column("input_redacted", JSON, nullable=True))
    op.add_column("tool_executions", sa.Column("output_redacted", JSON, nullable=True))

    # Add index on trace_id
    op.create_index("ix_tool_executions_trace_id", "tool_executions", ["trace_id"])


def downgrade() -> None:
    op.drop_index("ix_tool_executions_trace_id", table_name="tool_executions")

    op.drop_column("tool_executions", "output_redacted")
    op.drop_column("tool_executions", "input_redacted")
    op.drop_column("tool_executions", "execution_type")
    op.drop_column("tool_executions", "trace_id")
    op.drop_column("tool_executions", "agent_id")

    op.drop_column("tool_registry", "manifest_hash")
    op.drop_column("tool_registry", "health_status")
    op.drop_column("tool_registry", "source_type")
    op.drop_column("tool_registry", "risk_level")
    op.drop_column("tool_registry", "status")
    op.drop_column("tool_registry", "tool_type")
    op.drop_column("tool_registry", "category")
