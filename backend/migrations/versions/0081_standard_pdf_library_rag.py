"""standard pdf library rag

Revision ID: 0081
Revises: 0080_shared_memory_full_refactor
Create Date: 2026-06-19 01:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0081"
down_revision = "0080_shared_memory_full_refactor"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return column_name in {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if not _has_column(table_name, column.name):
        op.add_column(table_name, column)


def upgrade() -> None:
    _add_column_if_missing("inspection_standard_libraries", sa.Column("domain", sa.String(length=100), nullable=True))
    _add_column_if_missing("inspection_standard_libraries", sa.Column("product_category", sa.String(length=100), nullable=True))
    _add_column_if_missing("inspection_standard_libraries", sa.Column("qdrant_collection", sa.String(length=128), nullable=True))
    _add_column_if_missing("inspection_standard_libraries", sa.Column("pdf_root_dir", sa.Text(), nullable=True))
    _add_column_if_missing("inspection_standard_libraries", sa.Column("file_glob", sa.String(length=64), nullable=False, server_default="*.pdf"))
    _add_column_if_missing("inspection_standard_libraries", sa.Column("chunk_strategy", sa.String(length=32), nullable=False, server_default="heading_then_size"))
    _add_column_if_missing("inspection_standard_libraries", sa.Column("standard_status", sa.String(length=32), nullable=False, server_default="现行"))
    _add_column_if_missing("inspection_standard_libraries", sa.Column("auto_reindex", sa.Boolean(), nullable=False, server_default=sa.false()))
    _add_column_if_missing("inspection_standard_libraries", sa.Column("pdf_count", sa.Integer(), nullable=False, server_default="0"))
    _add_column_if_missing("inspection_standard_libraries", sa.Column("document_count", sa.Integer(), nullable=False, server_default="0"))
    _add_column_if_missing("inspection_standard_libraries", sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"))
    _add_column_if_missing("inspection_standard_libraries", sa.Column("import_status", sa.String(length=32), nullable=False, server_default="not_scanned"))
    _add_column_if_missing("inspection_standard_libraries", sa.Column("last_scanned_at", sa.DateTime(), nullable=True))
    _add_column_if_missing("inspection_standard_libraries", sa.Column("last_indexed_at", sa.DateTime(), nullable=True))
    _add_column_if_missing("inspection_standard_libraries", sa.Column("error_message", sa.Text(), nullable=True))

    if not _has_table("standard_documents"):
        op.create_table(
            "standard_documents",
            sa.Column("id", sa.BINARY(length=16), nullable=False),
            sa.Column("library_id", sa.BINARY(length=16), nullable=False),
            sa.Column("org_id", sa.BINARY(length=16), nullable=True),
            sa.Column("domain", sa.String(length=100), nullable=False),
            sa.Column("product_category", sa.String(length=100), nullable=True),
            sa.Column("standard_no", sa.String(length=100), nullable=False),
            sa.Column("standard_name", sa.String(length=255), nullable=False),
            sa.Column("standard_level", sa.String(length=32), nullable=False),
            sa.Column("standard_status", sa.String(length=32), nullable=False, server_default="现行"),
            sa.Column("file_name", sa.String(length=255), nullable=False),
            sa.Column("file_path", sa.Text(), nullable=False),
            sa.Column("file_hash", sa.String(length=64), nullable=True),
            sa.Column("file_size", sa.BigInteger(), nullable=True),
            sa.Column("page_count", sa.Integer(), nullable=True),
            sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("qdrant_collection", sa.String(length=128), nullable=True),
            sa.Column("import_status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("last_indexed_at", sa.DateTime(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3)")),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")),
            sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.ForeignKeyConstraint(["library_id"], ["inspection_standard_libraries.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_standard_documents_library_id", "standard_documents", ["library_id"])
        op.create_index("idx_standard_documents_standard_no", "standard_documents", ["standard_no"])
        op.create_index("idx_standard_documents_domain_product", "standard_documents", ["domain", "product_category"])
        op.create_index("idx_standard_documents_import_status", "standard_documents", ["import_status"])

    if not _has_table("standard_document_chunks"):
        op.create_table(
            "standard_document_chunks",
            sa.Column("id", sa.BINARY(length=16), nullable=False),
            sa.Column("document_id", sa.BINARY(length=16), nullable=False),
            sa.Column("library_id", sa.BINARY(length=16), nullable=False),
            sa.Column("chunk_index", sa.Integer(), nullable=False),
            sa.Column("page_from", sa.Integer(), nullable=True),
            sa.Column("page_to", sa.Integer(), nullable=True),
            sa.Column("section_title", sa.String(length=255), nullable=True),
            sa.Column("chunk_text", sa.Text(), nullable=False),
            sa.Column("payload_json", sa.JSON(), nullable=True),
            sa.Column("qdrant_point_id", sa.String(length=128), nullable=False),
            sa.Column("token_count", sa.Integer(), nullable=True),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3)")),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")),
            sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.ForeignKeyConstraint(["document_id"], ["standard_documents.id"]),
            sa.ForeignKeyConstraint(["library_id"], ["inspection_standard_libraries.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_standard_chunks_document_id", "standard_document_chunks", ["document_id"])
        op.create_index("idx_standard_chunks_library_id", "standard_document_chunks", ["library_id"])
        op.create_index("idx_standard_chunks_point_id", "standard_document_chunks", ["qdrant_point_id"])


def downgrade() -> None:
    if _has_table("standard_document_chunks"):
        op.drop_table("standard_document_chunks")
    if _has_table("standard_documents"):
        op.drop_table("standard_documents")
