"""remove meeting room type

Revision ID: 0077
Revises: 0076
Create Date: 2026-06-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0077"
down_revision = "0076"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("idx_meeting_rooms_org_type", table_name="meeting_rooms")
    op.drop_column("meeting_rooms", "room_type")


def downgrade() -> None:
    op.add_column(
        "meeting_rooms",
        sa.Column("room_type", sa.String(length=32), nullable=False, server_default="quality_business"),
    )
    op.create_index("idx_meeting_rooms_org_type", "meeting_rooms", ["org_id", "room_type"])
