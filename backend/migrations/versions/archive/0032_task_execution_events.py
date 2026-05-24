"""add task execution events

Revision ID: 0032_task_execution_events
Revises: 0031_rag_chunks_and_jobs
Create Date: 2026-05-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0032_task_execution_events"
down_revision = "0031_rag_chunks_and_jobs"
branch_labels = None
depends_on = None

TS_DEFAULT = sa.text("CURRENT_TIMESTAMP(3)")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "task_execution_events" in set(inspector.get_table_names()):
        return

    op.create_table(
        "task_execution_events",
        sa.Column("id", sa.BINARY(16), nullable=False),
        sa.Column("org_id", sa.BINARY(16), nullable=False),
        sa.Column("task_id", sa.BINARY(16), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("payload_json", mysql.JSON(), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_task_execution_events_task",
        "task_execution_events",
        ["org_id", "task_id", "created_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "task_execution_events" not in set(inspector.get_table_names()):
        return
    op.drop_index("idx_task_execution_events_task", table_name="task_execution_events")
    op.drop_table("task_execution_events")
