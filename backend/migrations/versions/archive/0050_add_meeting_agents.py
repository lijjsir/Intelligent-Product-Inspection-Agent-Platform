"""add meeting room agents and message metadata

Revision ID: 0050
Revises: 0049
Create Date: 2026-05-22 16:00:00.000000

Add meeting_room_agents table, message_type/agent_id/mentions columns to meeting_messages.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None

TS_DEFAULT = sa.text("CURRENT_TIMESTAMP(3)")
TS_UPDATE_DEFAULT = sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")


def upgrade() -> None:
    op.create_table(
        "meeting_room_agents",
        sa.Column("id", sa.BINARY(16), nullable=False),
        sa.Column("org_id", sa.BINARY(16), nullable=False),
        sa.Column("room_id", sa.BINARY(16), nullable=False),
        sa.Column("agent_id", sa.BINARY(16), nullable=False),
        sa.Column("added_by", sa.BINARY(16), nullable=False),
        sa.Column("role", sa.String(length=24), nullable=False, server_default="participant"),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("room_id", "agent_id", name="uq_meeting_room_agents_room_agent"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("idx_meeting_room_agents_room", "meeting_room_agents", ["room_id"])
    op.create_index("idx_meeting_room_agents_org_room", "meeting_room_agents", ["org_id", "room_id"])

    op.add_column("meeting_messages", sa.Column("message_type", sa.String(length=32), nullable=False, server_default="user"))
    op.add_column("meeting_messages", sa.Column("agent_id", sa.BINARY(16), nullable=True))
    op.add_column("meeting_messages", sa.Column("mentions", mysql.JSON(), nullable=True))
    op.create_index("idx_meeting_messages_agent", "meeting_messages", ["agent_id"])


def downgrade() -> None:
    op.drop_index("idx_meeting_messages_agent", table_name="meeting_messages")
    op.drop_column("meeting_messages", "mentions")
    op.drop_column("meeting_messages", "agent_id")
    op.drop_column("meeting_messages", "message_type")

    op.drop_index("idx_meeting_room_agents_org_room", table_name="meeting_room_agents")
    op.drop_index("idx_meeting_room_agents_room", table_name="meeting_room_agents")
    op.drop_table("meeting_room_agents")
