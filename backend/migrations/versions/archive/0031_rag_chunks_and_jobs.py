"""add rag chunk metadata and index jobs

Revision ID: 0031_rag_chunks_and_jobs
Revises: 0030_rag_document_bucket
Create Date: 2026-05-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0031_rag_chunks_and_jobs"
down_revision = "0030_rag_document_bucket"
branch_labels = None
depends_on = None

TS_DEFAULT = sa.text("CURRENT_TIMESTAMP(3)")
TS_UPDATE_DEFAULT = sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "rag_document_chunks" not in tables:
        op.create_table(
            "rag_document_chunks",
            sa.Column("id", sa.BINARY(16), nullable=False),
            sa.Column("org_id", sa.BINARY(16), nullable=False),
            sa.Column("rag_space_id", sa.BINARY(16), nullable=False),
            sa.Column("document_id", sa.BINARY(16), nullable=False),
            sa.Column("node_id", sa.BINARY(16), nullable=False),
            sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("content_text", sa.Text(), nullable=False),
            sa.Column("content_preview", sa.Text(), nullable=False),
            sa.Column("page_number", sa.Integer(), nullable=True),
            sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("qdrant_point_id", sa.String(length=191), nullable=False, server_default=""),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
            sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_rag_chunks_doc", "rag_document_chunks", ["document_id"])
        op.create_index("idx_rag_chunks_space", "rag_document_chunks", ["rag_space_id"])

    if "rag_index_jobs" not in tables:
        op.create_table(
            "rag_index_jobs",
            sa.Column("id", sa.BINARY(16), nullable=False),
            sa.Column("org_id", sa.BINARY(16), nullable=False),
            sa.Column("rag_space_id", sa.BINARY(16), nullable=False),
            sa.Column("document_id", sa.BINARY(16), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
            sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_rag_index_jobs_doc", "rag_index_jobs", ["document_id"])
        op.create_index("idx_rag_index_jobs_space", "rag_index_jobs", ["rag_space_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "rag_index_jobs" in tables:
        op.drop_index("idx_rag_index_jobs_space", table_name="rag_index_jobs")
        op.drop_index("idx_rag_index_jobs_doc", table_name="rag_index_jobs")
        op.drop_table("rag_index_jobs")
    if "rag_document_chunks" in tables:
        op.drop_index("idx_rag_chunks_space", table_name="rag_document_chunks")
        op.drop_index("idx_rag_chunks_doc", table_name="rag_document_chunks")
        op.drop_table("rag_document_chunks")
