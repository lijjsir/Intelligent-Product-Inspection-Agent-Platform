"""add collaboration messages and memory tags

Revision ID: 0079
Revises: 0078
Create Date: 2026-06-22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0079"
down_revision = "0078"
branch_labels = None
depends_on = None

TS_DEFAULT = sa.text("CURRENT_TIMESTAMP(3)")
TS_UPDATE_DEFAULT = sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")


def upgrade() -> None:
    op.create_table(
        "collab_threads",
        sa.Column("id", mysql.BINARY(16), nullable=False),
        sa.Column("org_id", mysql.BINARY(16), nullable=False),
        sa.Column("thread_type", sa.String(length=32), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_by", mysql.BINARY(16), nullable=False),
        sa.Column("last_message_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("metadata_json", mysql.JSON(), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_collab_threads_org_id", "collab_threads", ["org_id"])
    op.create_index("ix_collab_threads_created_by", "collab_threads", ["created_by"])
    op.create_index(
        "idx_collab_threads_org_source",
        "collab_threads",
        ["org_id", "source_type", "source_id"],
    )
    op.create_index(
        "idx_collab_threads_org_target",
        "collab_threads",
        ["org_id", "target_type", "target_id"],
    )
    op.create_index(
        "idx_collab_threads_org_last_message",
        "collab_threads",
        ["org_id", "last_message_at"],
    )

    op.create_table(
        "collab_thread_participants",
        sa.Column("id", mysql.BINARY(16), nullable=False),
        sa.Column("org_id", mysql.BINARY(16), nullable=False),
        sa.Column("thread_id", mysql.BINARY(16), nullable=False),
        sa.Column("participant_type", sa.String(length=32), nullable=False),
        sa.Column("participant_id", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="participant"),
        sa.Column("last_read_message_id", mysql.BINARY(16), nullable=True),
        sa.Column("mute_until", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "thread_id",
            "participant_type",
            "participant_id",
            name="uq_collab_thread_participant",
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_collab_thread_participants_org_id", "collab_thread_participants", ["org_id"])
    op.create_index("ix_collab_thread_participants_thread_id", "collab_thread_participants", ["thread_id"])
    op.create_index(
        "idx_collab_participants_lookup",
        "collab_thread_participants",
        ["org_id", "participant_type", "participant_id"],
    )
    op.create_index(
        "idx_collab_participants_thread",
        "collab_thread_participants",
        ["org_id", "thread_id"],
    )

    op.create_table(
        "collab_messages",
        sa.Column("id", mysql.BINARY(16), nullable=False),
        sa.Column("org_id", mysql.BINARY(16), nullable=False),
        sa.Column("thread_id", mysql.BINARY(16), nullable=False),
        sa.Column("sender_type", sa.String(length=32), nullable=False),
        sa.Column("sender_id", sa.String(length=128), nullable=False),
        sa.Column("message_type", sa.String(length=32), nullable=False, server_default="text"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("reply_to_message_id", mysql.BINARY(16), nullable=True),
        sa.Column("metadata_json", mysql.JSON(), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_collab_messages_org_id", "collab_messages", ["org_id"])
    op.create_index("ix_collab_messages_thread_id", "collab_messages", ["thread_id"])
    op.create_index(
        "idx_collab_messages_thread_created",
        "collab_messages",
        ["thread_id", "created_at"],
    )
    op.create_index("idx_collab_messages_org_thread", "collab_messages", ["org_id", "thread_id"])

    op.create_table(
        "collab_message_receipts",
        sa.Column("id", mysql.BINARY(16), nullable=False),
        sa.Column("org_id", mysql.BINARY(16), nullable=False),
        sa.Column("message_id", mysql.BINARY(16), nullable=False),
        sa.Column("thread_id", mysql.BINARY(16), nullable=False),
        sa.Column("recipient_type", sa.String(length=32), nullable=False),
        sa.Column("recipient_id", sa.String(length=128), nullable=False),
        sa.Column("delivered_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("read_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("acted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("action_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "message_id",
            "recipient_type",
            "recipient_id",
            name="uq_collab_message_receipt",
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_collab_message_receipts_org_id", "collab_message_receipts", ["org_id"])
    op.create_index("ix_collab_message_receipts_message_id", "collab_message_receipts", ["message_id"])
    op.create_index("ix_collab_message_receipts_thread_id", "collab_message_receipts", ["thread_id"])
    op.create_index(
        "idx_collab_receipts_recipient",
        "collab_message_receipts",
        ["org_id", "recipient_type", "recipient_id", "read_at"],
    )
    op.create_index(
        "idx_collab_receipts_message",
        "collab_message_receipts",
        ["message_id", "recipient_id"],
    )

    op.create_table(
        "file_assets",
        sa.Column("id", mysql.BINARY(16), nullable=False),
        sa.Column("org_id", mysql.BINARY(16), nullable=False),
        sa.Column("bucket", sa.String(length=120), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("checksum", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("uploaded_by", mysql.BINARY(16), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_file_assets_org_id", "file_assets", ["org_id"])
    op.create_index("ix_file_assets_uploaded_by", "file_assets", ["uploaded_by"])
    op.create_index("idx_file_assets_org_uploaded", "file_assets", ["org_id", "uploaded_by"])
    op.create_index("idx_file_assets_object", "file_assets", ["org_id", "bucket", "object_key"], mysql_length={"object_key": 191})

    op.create_table(
        "message_attachments",
        sa.Column("id", mysql.BINARY(16), nullable=False),
        sa.Column("org_id", mysql.BINARY(16), nullable=False),
        sa.Column("message_id", mysql.BINARY(16), nullable=False),
        sa.Column("file_id", mysql.BINARY(16), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "file_id", name="uq_message_attachment_file"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_message_attachments_org_id", "message_attachments", ["org_id"])
    op.create_index("ix_message_attachments_message_id", "message_attachments", ["message_id"])
    op.create_index("ix_message_attachments_file_id", "message_attachments", ["file_id"])
    op.create_index(
        "idx_message_attachments_message",
        "message_attachments",
        ["message_id", "sort_order"],
    )

    op.create_table(
        "memory_tags",
        sa.Column("id", mysql.BINARY(16), nullable=False),
        sa.Column("org_id", mysql.BINARY(16), nullable=False),
        sa.Column("memory_id", sa.String(length=64), nullable=False),
        sa.Column("tag_type", sa.String(length=32), nullable=False),
        sa.Column("tag_value", sa.String(length=128), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("idx_memory_tags_memory", "memory_tags", ["org_id", "memory_id"])
    op.create_index("idx_memory_tags_lookup", "memory_tags", ["org_id", "tag_type", "tag_value"])


def downgrade() -> None:
    op.drop_index("idx_memory_tags_lookup", table_name="memory_tags")
    op.drop_index("idx_memory_tags_memory", table_name="memory_tags")
    op.drop_table("memory_tags")

    op.drop_index("idx_message_attachments_message", table_name="message_attachments")
    op.drop_index("ix_message_attachments_file_id", table_name="message_attachments")
    op.drop_index("ix_message_attachments_message_id", table_name="message_attachments")
    op.drop_index("ix_message_attachments_org_id", table_name="message_attachments")
    op.drop_table("message_attachments")

    op.drop_index("idx_file_assets_object", table_name="file_assets")
    op.drop_index("idx_file_assets_org_uploaded", table_name="file_assets")
    op.drop_index("ix_file_assets_uploaded_by", table_name="file_assets")
    op.drop_index("ix_file_assets_org_id", table_name="file_assets")
    op.drop_table("file_assets")

    op.drop_index("idx_collab_receipts_message", table_name="collab_message_receipts")
    op.drop_index("idx_collab_receipts_recipient", table_name="collab_message_receipts")
    op.drop_index("ix_collab_message_receipts_thread_id", table_name="collab_message_receipts")
    op.drop_index("ix_collab_message_receipts_message_id", table_name="collab_message_receipts")
    op.drop_index("ix_collab_message_receipts_org_id", table_name="collab_message_receipts")
    op.drop_table("collab_message_receipts")

    op.drop_index("idx_collab_messages_org_thread", table_name="collab_messages")
    op.drop_index("idx_collab_messages_thread_created", table_name="collab_messages")
    op.drop_index("ix_collab_messages_thread_id", table_name="collab_messages")
    op.drop_index("ix_collab_messages_org_id", table_name="collab_messages")
    op.drop_table("collab_messages")

    op.drop_index("idx_collab_participants_thread", table_name="collab_thread_participants")
    op.drop_index("idx_collab_participants_lookup", table_name="collab_thread_participants")
    op.drop_index("ix_collab_thread_participants_thread_id", table_name="collab_thread_participants")
    op.drop_index("ix_collab_thread_participants_org_id", table_name="collab_thread_participants")
    op.drop_table("collab_thread_participants")

    op.drop_index("idx_collab_threads_org_last_message", table_name="collab_threads")
    op.drop_index("idx_collab_threads_org_target", table_name="collab_threads")
    op.drop_index("idx_collab_threads_org_source", table_name="collab_threads")
    op.drop_index("ix_collab_threads_created_by", table_name="collab_threads")
    op.drop_index("ix_collab_threads_org_id", table_name="collab_threads")
    op.drop_table("collab_threads")
