"""add isolated meeting context summaries and business object candidates

Revision ID: 0093_meeting_context_and_objects
Revises: 0092_drop_stale_memory_workspace_columns
Create Date: 2026-08-24
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0093_meeting_context_and_objects"
down_revision = "0092_drop_stale_memory_workspace_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "meeting_context_summaries",
        sa.Column("id", sa.BINARY(16), nullable=False),
        sa.Column("org_id", sa.BINARY(16), nullable=False),
        sa.Column("room_id", sa.BINARY(16), nullable=False),
        sa.Column("context_scope", sa.String(24), nullable=False, server_default="room"),
        sa.Column("user_key", sa.String(64), nullable=False, server_default="public"),
        sa.Column("through_seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "room_id",
            "context_scope",
            "user_key",
            name="uq_meeting_context_summaries_scope",
        ),
    )
    op.create_index(
        "idx_meeting_context_summaries_room",
        "meeting_context_summaries",
        ["org_id", "room_id"],
    )
    op.create_table(
        "meeting_business_object_candidates",
        sa.Column("id", sa.BINARY(16), nullable=False),
        sa.Column("org_id", sa.BINARY(16), nullable=False),
        sa.Column("room_id", sa.BINARY(16), nullable=False),
        sa.Column("object_type", sa.String(32), nullable=False),
        sa.Column("object_value", sa.String(128), nullable=False),
        sa.Column("resolved_value", sa.String(128), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="candidate"),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("source_message_ids", sa.JSON(), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.BINARY(16), nullable=True),
        sa.Column("resolved_by", sa.BINARY(16), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "room_id",
            "object_type",
            "object_value",
            name="uq_meeting_business_object_candidate",
        ),
    )
    op.create_index(
        "idx_meeting_business_object_candidates_room_status",
        "meeting_business_object_candidates",
        ["org_id", "room_id", "status"],
    )
    op.execute(
        "UPDATE meeting_rooms "
        "SET audit_policy = JSON_SET(COALESCE(audit_policy, JSON_OBJECT()), "
        "'$.auto_participation_mode', 'off') "
        "WHERE JSON_UNQUOTE(JSON_EXTRACT(audit_policy, '$.auto_participation_mode')) = 'shadow'"
    )


def downgrade() -> None:
    op.drop_index(
        "idx_meeting_business_object_candidates_room_status",
        table_name="meeting_business_object_candidates",
    )
    op.drop_table("meeting_business_object_candidates")
    op.drop_index("idx_meeting_context_summaries_room", table_name="meeting_context_summaries")
    op.drop_table("meeting_context_summaries")
