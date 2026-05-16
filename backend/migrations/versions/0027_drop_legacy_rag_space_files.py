"""drop legacy rag_space_files table

Revision ID: 0027_drop_legacy_rag
Revises: 0026_rag_tree_nodes
Create Date: 2026-05-16
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0027_drop_legacy_rag"
down_revision = "0026_rag_tree_nodes"
branch_labels = None
depends_on = None

TS_DEFAULT = sa.text("CURRENT_TIMESTAMP(3)")
TS_UPDATE_DEFAULT = sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "rag_space_files" not in set(inspector.get_table_names()):
        return
    index_names = {index["name"] for index in inspector.get_indexes("rag_space_files")}
    if "idx_rag_space_files_org_space" in index_names:
        op.drop_index("idx_rag_space_files_org_space", table_name="rag_space_files")
    if "idx_rag_space_files_space" in index_names:
        op.drop_index("idx_rag_space_files_space", table_name="rag_space_files")
    op.drop_table("rag_space_files")


def downgrade() -> None:
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
