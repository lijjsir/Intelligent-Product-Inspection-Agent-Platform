"""create meeting rooms

Revision ID: 0035_meeting_rooms
Revises: 0034_chat_route_obs
Create Date: 2026-05-18
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0035_meeting_rooms"
down_revision = "0034_chat_route_obs"
branch_labels = None
depends_on = None

TS_DEFAULT = sa.text("CURRENT_TIMESTAMP(3)")
TS_UPDATE_DEFAULT = sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")


def upgrade() -> None:
    op.create_table(
        "meeting_rooms",
        sa.Column("id", sa.BINARY(16), nullable=False),
        sa.Column("org_id", sa.BINARY(16), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("access_code", sa.String(length=16), nullable=False),
        sa.Column("password_hash", sa.String(length=256), nullable=True),
        sa.Column("created_by", sa.BINARY(16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("last_message_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "access_code", name="uq_meeting_rooms_org_code"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_meeting_rooms_org_id", "meeting_rooms", ["org_id"])
    op.create_index("ix_meeting_rooms_created_by", "meeting_rooms", ["created_by"])
    op.create_index("idx_meeting_rooms_org_status", "meeting_rooms", ["org_id", "status"])

    op.create_table(
        "meeting_room_members",
        sa.Column("id", sa.BINARY(16), nullable=False),
        sa.Column("org_id", sa.BINARY(16), nullable=False),
        sa.Column("room_id", sa.BINARY(16), nullable=False),
        sa.Column("user_id", sa.BINARY(16), nullable=False),
        sa.Column("role", sa.String(length=24), nullable=False, server_default="member"),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("room_id", "user_id", name="uq_meeting_room_members_user"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_meeting_room_members_org_id", "meeting_room_members", ["org_id"])
    op.create_index("ix_meeting_room_members_room_id", "meeting_room_members", ["room_id"])
    op.create_index("ix_meeting_room_members_user_id", "meeting_room_members", ["user_id"])
    op.create_index("idx_meeting_room_members_org_user", "meeting_room_members", ["org_id", "user_id"])

    op.create_table(
        "meeting_messages",
        sa.Column("id", sa.BINARY(16), nullable=False),
        sa.Column("org_id", sa.BINARY(16), nullable=False),
        sa.Column("room_id", sa.BINARY(16), nullable=False),
        sa.Column("user_id", sa.BINARY(16), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("seq_no", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("room_id", "seq_no", name="uq_meeting_messages_room_seq"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_meeting_messages_org_id", "meeting_messages", ["org_id"])
    op.create_index("ix_meeting_messages_room_id", "meeting_messages", ["room_id"])
    op.create_index("ix_meeting_messages_user_id", "meeting_messages", ["user_id"])
    op.create_index("idx_meeting_messages_org_room", "meeting_messages", ["org_id", "room_id"])


def downgrade() -> None:
    op.drop_index("idx_meeting_messages_org_room", table_name="meeting_messages")
    op.drop_index("ix_meeting_messages_user_id", table_name="meeting_messages")
    op.drop_index("ix_meeting_messages_room_id", table_name="meeting_messages")
    op.drop_index("ix_meeting_messages_org_id", table_name="meeting_messages")
    op.drop_table("meeting_messages")

    op.drop_index("idx_meeting_room_members_org_user", table_name="meeting_room_members")
    op.drop_index("ix_meeting_room_members_user_id", table_name="meeting_room_members")
    op.drop_index("ix_meeting_room_members_room_id", table_name="meeting_room_members")
    op.drop_index("ix_meeting_room_members_org_id", table_name="meeting_room_members")
    op.drop_table("meeting_room_members")

    op.drop_index("idx_meeting_rooms_org_status", table_name="meeting_rooms")
    op.drop_index("ix_meeting_rooms_created_by", table_name="meeting_rooms")
    op.drop_index("ix_meeting_rooms_org_id", table_name="meeting_rooms")
    op.drop_table("meeting_rooms")
