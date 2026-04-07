"""create rag spaces and files

Revision ID: 0015_rag_spaces_and_files
Revises: 0014_chat_sessions_and_messages
Create Date: 2026-04-02

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0015_rag_spaces_and_files"
down_revision = "0014_chat_sessions_and_messages"
branch_labels = None
depends_on = None

TS_DEFAULT = sa.text("CURRENT_TIMESTAMP(3)")
TS_UPDATE_DEFAULT = sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")


def upgrade() -> None:
    op.create_table(
        "rag_spaces",
        sa.Column("id", sa.BINARY(16), nullable=False),
        sa.Column("org_id", sa.BINARY(16), nullable=False),
        sa.Column("created_by", sa.BINARY(16), nullable=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="ready"),
        sa.Column("file_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("selected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="User managed RAG spaces",
    )
    op.create_index("idx_rag_spaces_org", "rag_spaces", ["org_id"])
    op.create_index("idx_rag_spaces_org_name", "rag_spaces", ["org_id", "name"])

    op.create_table(
        "rag_space_files",
        sa.Column("id", sa.BINARY(16), nullable=False),
        sa.Column("rag_space_id", sa.BINARY(16), nullable=False),
        sa.Column("org_id", sa.BINARY(16), nullable=False),
        sa.Column("uploaded_by", sa.BINARY(16), nullable=True),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=True),
        sa.Column("file_url", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="ready"),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="Uploaded documents in RAG spaces",
    )
    op.create_index("idx_rag_space_files_space", "rag_space_files", ["rag_space_id"])
    op.create_index("idx_rag_space_files_org_space", "rag_space_files", ["org_id", "rag_space_id"])


def downgrade() -> None:
    op.drop_index("idx_rag_space_files_org_space", "rag_space_files")
    op.drop_index("idx_rag_space_files_space", "rag_space_files")
    op.drop_table("rag_space_files")

    op.drop_index("idx_rag_spaces_org_name", "rag_spaces")
    op.drop_index("idx_rag_spaces_org", "rag_spaces")
    op.drop_table("rag_spaces")
