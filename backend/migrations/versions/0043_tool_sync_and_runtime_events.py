"""add tool_sync_events and tool_runtime_events tables

Revision ID: 0043
Revises: 0042
Create Date: 2026-05-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql
from sqlalchemy.dialects.mysql import JSON, BINARY

revision: str = "0043"
down_revision: Union[str, None] = "0042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tool_sync_events",
        sa.Column("id", BINARY(16), primary_key=True),
        sa.Column("org_id", BINARY(16), nullable=True),
        sa.Column("tool_id", BINARY(16), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("old_hash", sa.String(64), nullable=True),
        sa.Column("new_hash", sa.String(64), nullable=True),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3)")),
    )

    op.create_table(
        "tool_runtime_events",
        sa.Column("id", BINARY(16), primary_key=True),
        sa.Column("org_id", BINARY(16), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("tool_id", BINARY(16), nullable=True),
        sa.Column("agent_id", BINARY(16), nullable=True),
        sa.Column("execution_id", BINARY(16), nullable=True),
        sa.Column("payload", JSON, nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3)")),
    )


def downgrade() -> None:
    op.drop_table("tool_runtime_events")
    op.drop_table("tool_sync_events")
