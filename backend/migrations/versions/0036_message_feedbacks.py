"""create message feedbacks

Revision ID: 0036_message_feedbacks
Revises: 0035_meeting_rooms
Create Date: 2026-05-19
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0036_message_feedbacks"
down_revision = "0035_meeting_rooms"
branch_labels = None
depends_on = None

TS_DEFAULT = sa.text("CURRENT_TIMESTAMP(3)")
TS_UPDATE_DEFAULT = sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")


def upgrade() -> None:
    op.create_table(
        "message_feedbacks",
        sa.Column("id", sa.BINARY(16), nullable=False),
        sa.Column("org_id", sa.BINARY(16), nullable=False),
        sa.Column("target_type", sa.String(length=24), nullable=False),
        sa.Column("target_id", sa.BINARY(16), nullable=False),
        sa.Column("actor_id", sa.BINARY(16), nullable=False),
        sa.Column("feedback_type", sa.String(length=16), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("actor_id", "target_type", "target_id", name="uk_actor_message_feedback"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_message_feedbacks_org_id", "message_feedbacks", ["org_id"])
    op.create_index("ix_message_feedbacks_target_type", "message_feedbacks", ["target_type"])
    op.create_index("ix_message_feedbacks_target_id", "message_feedbacks", ["target_id"])
    op.create_index("ix_message_feedbacks_actor_id", "message_feedbacks", ["actor_id"])
    op.create_index("idx_message_feedbacks_org_target", "message_feedbacks", ["org_id", "target_type", "target_id"])


def downgrade() -> None:
    op.drop_index("idx_message_feedbacks_org_target", table_name="message_feedbacks")
    op.drop_index("ix_message_feedbacks_actor_id", table_name="message_feedbacks")
    op.drop_index("ix_message_feedbacks_target_id", table_name="message_feedbacks")
    op.drop_index("ix_message_feedbacks_target_type", table_name="message_feedbacks")
    op.drop_index("ix_message_feedbacks_org_id", table_name="message_feedbacks")
    op.drop_table("message_feedbacks")
