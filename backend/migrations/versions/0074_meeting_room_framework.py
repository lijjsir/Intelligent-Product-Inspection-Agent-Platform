"""extend meeting rooms with agent memory workflow

Revision ID: 0074_meeting_room_framework
Revises: 0073
Create Date: 2026-06-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0074_meeting_room_framework"
down_revision = "0073"
branch_labels = None
depends_on = None

TS_DEFAULT = sa.text("CURRENT_TIMESTAMP(3)")
TS_UPDATE_DEFAULT = sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")


def upgrade() -> None:
    op.add_column("meeting_messages", sa.Column("quote_message_id", mysql.BINARY(16), nullable=True))
    op.add_column("meeting_messages", sa.Column("metadata_json", mysql.JSON(), nullable=True))
    op.create_index("ix_meeting_messages_quote_message_id", "meeting_messages", ["quote_message_id"])

    op.create_table(
        "memory_scope_bindings",
        sa.Column("id", mysql.BINARY(16), nullable=False),
        sa.Column("org_id", mysql.BINARY(16), nullable=False),
        sa.Column("memory_id", sa.String(length=64), nullable=False),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("scope_id", sa.String(length=128), nullable=False),
        sa.Column("permission", sa.String(length=32), nullable=False, server_default="read"),
        sa.Column("created_by", mysql.BINARY(16), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_memory_scope_bindings_org_id", "memory_scope_bindings", ["org_id"])
    op.create_index("ix_memory_scope_bindings_created_by", "memory_scope_bindings", ["created_by"])
    op.create_index("idx_memory_scope_bindings_memory", "memory_scope_bindings", ["org_id", "memory_id"])
    op.create_index(
        "idx_memory_scope_bindings_scope",
        "memory_scope_bindings",
        ["org_id", "scope_type", "scope_id"],
    )

    op.create_table(
        "memory_transfer_logs",
        sa.Column("id", mysql.BINARY(16), nullable=False),
        sa.Column("org_id", mysql.BINARY(16), nullable=False),
        sa.Column("memory_id", sa.String(length=64), nullable=False),
        sa.Column("from_scope_type", sa.String(length=32), nullable=False),
        sa.Column("from_scope_id", sa.String(length=128), nullable=False),
        sa.Column("to_scope_type", sa.String(length=32), nullable=False),
        sa.Column("to_scope_id", sa.String(length=128), nullable=False),
        sa.Column("transfer_reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="candidate"),
        sa.Column("operator_id", mysql.BINARY(16), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_memory_transfer_logs_org_id", "memory_transfer_logs", ["org_id"])
    op.create_index("ix_memory_transfer_logs_operator_id", "memory_transfer_logs", ["operator_id"])
    op.create_index("idx_memory_transfer_logs_memory", "memory_transfer_logs", ["org_id", "memory_id"])
    op.create_index(
        "idx_memory_transfer_logs_target",
        "memory_transfer_logs",
        ["org_id", "to_scope_type", "to_scope_id"],
    )

    op.create_table(
        "meeting_action_items",
        sa.Column("id", mysql.BINARY(16), nullable=False),
        sa.Column("org_id", mysql.BINARY(16), nullable=False),
        sa.Column("room_id", mysql.BINARY(16), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_id", mysql.BINARY(16), nullable=True),
        sa.Column("due_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("source_message_id", mysql.BINARY(16), nullable=True),
        sa.Column("created_by", mysql.BINARY(16), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_meeting_action_items_org_id", "meeting_action_items", ["org_id"])
    op.create_index("ix_meeting_action_items_room_id", "meeting_action_items", ["room_id"])
    op.create_index("ix_meeting_action_items_owner_id", "meeting_action_items", ["owner_id"])
    op.create_index("ix_meeting_action_items_source_message_id", "meeting_action_items", ["source_message_id"])
    op.create_index("ix_meeting_action_items_created_by", "meeting_action_items", ["created_by"])
    op.create_index(
        "idx_meeting_action_items_room_status",
        "meeting_action_items",
        ["org_id", "room_id", "status"],
    )
    op.create_index("idx_meeting_action_items_owner", "meeting_action_items", ["org_id", "owner_id"])


def downgrade() -> None:
    op.drop_index("idx_meeting_action_items_owner", table_name="meeting_action_items")
    op.drop_index("idx_meeting_action_items_room_status", table_name="meeting_action_items")
    op.drop_index("ix_meeting_action_items_created_by", table_name="meeting_action_items")
    op.drop_index("ix_meeting_action_items_source_message_id", table_name="meeting_action_items")
    op.drop_index("ix_meeting_action_items_owner_id", table_name="meeting_action_items")
    op.drop_index("ix_meeting_action_items_room_id", table_name="meeting_action_items")
    op.drop_index("ix_meeting_action_items_org_id", table_name="meeting_action_items")
    op.drop_table("meeting_action_items")

    op.drop_index("idx_memory_transfer_logs_target", table_name="memory_transfer_logs")
    op.drop_index("idx_memory_transfer_logs_memory", table_name="memory_transfer_logs")
    op.drop_index("ix_memory_transfer_logs_operator_id", table_name="memory_transfer_logs")
    op.drop_index("ix_memory_transfer_logs_org_id", table_name="memory_transfer_logs")
    op.drop_table("memory_transfer_logs")

    op.drop_index("idx_memory_scope_bindings_scope", table_name="memory_scope_bindings")
    op.drop_index("idx_memory_scope_bindings_memory", table_name="memory_scope_bindings")
    op.drop_index("ix_memory_scope_bindings_created_by", table_name="memory_scope_bindings")
    op.drop_index("ix_memory_scope_bindings_org_id", table_name="memory_scope_bindings")
    op.drop_table("memory_scope_bindings")

    op.drop_index("ix_meeting_messages_quote_message_id", table_name="meeting_messages")
    op.drop_column("meeting_messages", "metadata_json")
    op.drop_column("meeting_messages", "quote_message_id")
