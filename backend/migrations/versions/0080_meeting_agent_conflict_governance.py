"""add meeting agent conflict governance

Revision ID: 0080_meeting_agent_conflict_governance
Revises: 0079_collab_messages_and_memory_tags
Create Date: 2026-06-24
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0080_meeting_agent_conflict_governance"
down_revision = "0079_collab_messages_and_memory_tags"
branch_labels = None
depends_on = None

TS_DEFAULT = sa.text("CURRENT_TIMESTAMP(3)")
TS_UPDATE_DEFAULT = sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")


def upgrade() -> None:
    op.create_table(
        "meeting_conflict_events",
        sa.Column("id", mysql.BINARY(16), nullable=False),
        sa.Column("org_id", mysql.BINARY(16), nullable=False),
        sa.Column("room_id", mysql.BINARY(16), nullable=False),
        sa.Column("conflict_type", sa.String(length=32), nullable=False),
        sa.Column("resource_key", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("initiator_user_id", mysql.BINARY(16), nullable=False),
        sa.Column("workflow_run_id", sa.String(length=128), nullable=True),
        sa.Column("related_message_ids", mysql.JSON(), nullable=True),
        sa.Column("candidate_actions", mysql.JSON(), nullable=True),
        sa.Column("selected_action", sa.String(length=64), nullable=True),
        sa.Column("resolved_by", mysql.BINARY(16), nullable=True),
        sa.Column("resolved_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("metadata_json", mysql.JSON(), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_meeting_conflict_events_org_id", "meeting_conflict_events", ["org_id"])
    op.create_index("ix_meeting_conflict_events_room_id", "meeting_conflict_events", ["room_id"])
    op.create_index("ix_meeting_conflict_events_initiator_user_id", "meeting_conflict_events", ["initiator_user_id"])
    op.create_index("ix_meeting_conflict_events_resolved_by", "meeting_conflict_events", ["resolved_by"])
    op.create_index(
        "idx_meeting_conflict_events_room_status",
        "meeting_conflict_events",
        ["org_id", "room_id", "status"],
    )
    op.create_index(
        "idx_meeting_conflict_events_resource",
        "meeting_conflict_events",
        ["org_id", "room_id", "resource_key", "status"],
    )
    op.create_index(
        "idx_meeting_conflict_events_initiator",
        "meeting_conflict_events",
        ["org_id", "initiator_user_id"],
    )

    op.add_column("meeting_agent_query_audits", sa.Column("response_visibility", sa.String(length=16), nullable=True))
    op.add_column("meeting_agent_query_audits", sa.Column("conflict_ref_id", mysql.BINARY(16), nullable=True))
    op.create_index("ix_meeting_agent_query_audits_conflict_ref_id", "meeting_agent_query_audits", ["conflict_ref_id"])


def downgrade() -> None:
    op.drop_index("ix_meeting_agent_query_audits_conflict_ref_id", table_name="meeting_agent_query_audits")
    op.drop_column("meeting_agent_query_audits", "conflict_ref_id")
    op.drop_column("meeting_agent_query_audits", "response_visibility")

    op.drop_index("idx_meeting_conflict_events_initiator", table_name="meeting_conflict_events")
    op.drop_index("idx_meeting_conflict_events_resource", table_name="meeting_conflict_events")
    op.drop_index("idx_meeting_conflict_events_room_status", table_name="meeting_conflict_events")
    op.drop_index("ix_meeting_conflict_events_resolved_by", table_name="meeting_conflict_events")
    op.drop_index("ix_meeting_conflict_events_initiator_user_id", table_name="meeting_conflict_events")
    op.drop_index("ix_meeting_conflict_events_room_id", table_name="meeting_conflict_events")
    op.drop_index("ix_meeting_conflict_events_org_id", table_name="meeting_conflict_events")
    op.drop_table("meeting_conflict_events")
