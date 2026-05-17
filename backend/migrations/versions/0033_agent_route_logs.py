"""add agent route logs table

Revision ID: 0033_agent_route_logs
Revises: 0032_task_execution_events
Create Date: 2026-05-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0033_agent_route_logs"
down_revision = "0032_task_execution_events"
branch_labels = None
depends_on = None

TS_DEFAULT = sa.text("CURRENT_TIMESTAMP(3)")
TS_UPDATE_DEFAULT = sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "agent_route_logs" in set(inspector.get_table_names()):
        return

    op.create_table(
        "agent_route_logs",
        sa.Column("id", sa.BINARY(16), nullable=False),
        sa.Column("org_id", sa.BINARY(16), nullable=False),
        sa.Column("user_id", sa.BINARY(16), nullable=True),
        sa.Column("session_id", sa.BINARY(16), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("selected_agent", sa.String(length=64), nullable=False),
        sa.Column("intent_name", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False, server_default="0"),
        sa.Column("route_source", sa.String(length=32), nullable=False, server_default="rule"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_route_logs_session", "agent_route_logs", ["org_id", "session_id", "created_at"])
    op.create_index("idx_route_logs_agent", "agent_route_logs", ["org_id", "selected_agent", "created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "agent_route_logs" not in set(inspector.get_table_names()):
        return
    op.drop_index("idx_route_logs_agent", table_name="agent_route_logs")
    op.drop_index("idx_route_logs_session", table_name="agent_route_logs")
    op.drop_table("agent_route_logs")
