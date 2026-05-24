"""add bucket to rag documents

Revision ID: 0030_rag_document_bucket
Revises: 0029_normalize_embed_type
Create Date: 2026-05-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0030_rag_document_bucket"
down_revision = "0029_normalize_embed_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("rag_documents")}
    if "bucket" not in columns:
        op.add_column("rag_documents", sa.Column("bucket", sa.String(length=120), nullable=False, server_default=""))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("rag_documents")}
    if "bucket" in columns:
        op.drop_column("rag_documents", "bucket")
