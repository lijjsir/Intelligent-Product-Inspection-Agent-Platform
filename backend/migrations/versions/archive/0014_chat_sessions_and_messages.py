"""create chat sessions and messages

Revision ID: 0014_chat_sessions_and_messages
Revises: 0013_agent_ops_tables
Create Date: 2026-04-01

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0014_chat_sessions_and_messages"
down_revision = "0013_agent_ops_tables"
branch_labels = None
depends_on = None

TS_DEFAULT = sa.text("CURRENT_TIMESTAMP(3)")
TS_UPDATE_DEFAULT = sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.BINARY(16), nullable=False),
        sa.Column("org_id", sa.BINARY(16), nullable=False),
        sa.Column("user_id", sa.BINARY(16), nullable=False),
        sa.Column("title", sa.String(120), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("last_message_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="Chat sessions for quality assistant",
    )
    op.create_index("idx_chat_sessions_org_user", "chat_sessions", ["org_id", "user_id"])
    op.create_index("idx_chat_sessions_org_status", "chat_sessions", ["org_id", "status"])

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.BINARY(16), nullable=False),
        sa.Column("session_id", sa.BINARY(16), nullable=False),
        sa.Column("org_id", sa.BINARY(16), nullable=False),
        sa.Column("user_id", sa.BINARY(16), nullable=True),
        sa.Column("seq_no", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("message_type", sa.String(32), nullable=False, server_default="text"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("payload", mysql.JSON(), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="Chat messages for quality assistant",
    )
    op.create_index("idx_chat_messages_session_seq", "chat_messages", ["session_id", "seq_no"])
    op.create_index("idx_chat_messages_org_session", "chat_messages", ["org_id", "session_id"])


def downgrade() -> None:
    op.drop_index("idx_chat_messages_org_session", "chat_messages")
    op.drop_index("idx_chat_messages_session_seq", "chat_messages")
    op.drop_table("chat_messages")

    op.drop_index("idx_chat_sessions_org_status", "chat_sessions")
    op.drop_index("idx_chat_sessions_org_user", "chat_sessions")
    op.drop_table("chat_sessions")
