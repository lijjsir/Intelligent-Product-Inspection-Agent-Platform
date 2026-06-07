"""add meeting room v2 permission boundaries

Revision ID: 0075
Revises: 0074
Create Date: 2026-06-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0075"
down_revision = "0074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "meeting_rooms",
        sa.Column("room_type", sa.String(length=32), nullable=False, server_default="quality_business"),
    )
    op.add_column(
        "meeting_rooms",
        sa.Column("visibility", sa.String(length=32), nullable=False, server_default="private"),
    )
    op.add_column("meeting_rooms", sa.Column("allowed_data_domains", mysql.JSON(), nullable=True))
    op.add_column("meeting_rooms", sa.Column("memory_policy", mysql.JSON(), nullable=True))
    op.add_column("meeting_rooms", sa.Column("audit_policy", mysql.JSON(), nullable=True))
    op.create_index("idx_meeting_rooms_org_type", "meeting_rooms", ["org_id", "room_type"])

    op.add_column("meeting_room_agents", sa.Column("allowed_domains", mysql.JSON(), nullable=True))
    op.add_column("meeting_room_agents", sa.Column("allowed_tools", mysql.JSON(), nullable=True))

    op.create_table(
        "meeting_agent_query_audits",
        sa.Column("id", mysql.BINARY(16), nullable=False),
        sa.Column("org_id", mysql.BINARY(16), nullable=False),
        sa.Column("room_id", mysql.BINARY(16), nullable=False),
        sa.Column("user_id", mysql.BINARY(16), nullable=False),
        sa.Column("agent_id", sa.String(length=64), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(length=64), nullable=True),
        sa.Column("requested_domains", mysql.JSON(), nullable=True),
        sa.Column("allowed_domains", mysql.JSON(), nullable=True),
        sa.Column("denied_domains", mysql.JSON(), nullable=True),
        sa.Column("tool_calls", mysql.JSON(), nullable=True),
        sa.Column("source_refs", mysql.JSON(), nullable=True),
        sa.Column("redacted_fields", mysql.JSON(), nullable=True),
        sa.Column("decision", sa.String(length=32), nullable=False, server_default="allowed"),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3)")),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=3),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"),
        ),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_meeting_agent_query_audits_org_id", "meeting_agent_query_audits", ["org_id"])
    op.create_index("ix_meeting_agent_query_audits_room_id", "meeting_agent_query_audits", ["room_id"])
    op.create_index("ix_meeting_agent_query_audits_user_id", "meeting_agent_query_audits", ["user_id"])
    op.create_index("ix_meeting_agent_query_audits_agent_id", "meeting_agent_query_audits", ["agent_id"])
    op.create_index(
        "idx_meeting_agent_query_audits_room",
        "meeting_agent_query_audits",
        ["org_id", "room_id"],
    )
    op.create_index(
        "idx_meeting_agent_query_audits_user",
        "meeting_agent_query_audits",
        ["org_id", "user_id"],
    )
    op.create_index(
        "idx_meeting_agent_query_audits_agent",
        "meeting_agent_query_audits",
        ["org_id", "agent_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_meeting_agent_query_audits_agent", table_name="meeting_agent_query_audits")
    op.drop_index("idx_meeting_agent_query_audits_user", table_name="meeting_agent_query_audits")
    op.drop_index("idx_meeting_agent_query_audits_room", table_name="meeting_agent_query_audits")
    op.drop_index("ix_meeting_agent_query_audits_agent_id", table_name="meeting_agent_query_audits")
    op.drop_index("ix_meeting_agent_query_audits_user_id", table_name="meeting_agent_query_audits")
    op.drop_index("ix_meeting_agent_query_audits_room_id", table_name="meeting_agent_query_audits")
    op.drop_index("ix_meeting_agent_query_audits_org_id", table_name="meeting_agent_query_audits")
    op.drop_table("meeting_agent_query_audits")

    op.drop_column("meeting_room_agents", "allowed_tools")
    op.drop_column("meeting_room_agents", "allowed_domains")

    op.drop_index("idx_meeting_rooms_org_type", table_name="meeting_rooms")
    op.drop_column("meeting_rooms", "audit_policy")
    op.drop_column("meeting_rooms", "memory_policy")
    op.drop_column("meeting_rooms", "allowed_data_domains")
    op.drop_column("meeting_rooms", "visibility")
    op.drop_column("meeting_rooms", "room_type")
