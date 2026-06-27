"""merge standard library rag schema with meeting branch

Revision ID: 0085_merge_standard_library_rag_schema
Revises: 0083, 0084_localize_product_master_legacy_labels
Create Date: 2026-06-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0085_merge_standard_library_rag_schema"
down_revision = ("0083", "0084_localize_product_master_legacy_labels")
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return column_name in {column["name"] for column in _inspector().get_columns(table_name)}


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if _has_table(table_name) and not _has_column(table_name, column.name):
        op.add_column(table_name, column)


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    if _has_table(table_name) and not _has_index(table_name, index_name):
        op.create_index(index_name, table_name, columns)


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

    _create_index_if_missing("ix_inspection_standard_libraries_domain", "inspection_standard_libraries", ["domain"])
    _create_index_if_missing("ix_inspection_standard_libraries_product_category", "inspection_standard_libraries", ["product_category"])

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

    _create_index_if_missing("idx_standard_documents_library_id", "standard_documents", ["library_id"])
    _create_index_if_missing("idx_standard_documents_standard_no", "standard_documents", ["standard_no"])
    _create_index_if_missing("idx_standard_documents_domain_product", "standard_documents", ["domain", "product_category"])
    _create_index_if_missing("idx_standard_documents_import_status", "standard_documents", ["import_status"])

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
            sa.Column("payload_json", mysql.JSON(), nullable=True),
            sa.Column("qdrant_point_id", sa.String(length=128), nullable=False),
            sa.Column("token_count", sa.Integer(), nullable=True),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3)")),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")),
            sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.ForeignKeyConstraint(["document_id"], ["standard_documents.id"]),
            sa.ForeignKeyConstraint(["library_id"], ["inspection_standard_libraries.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    _create_index_if_missing("idx_standard_chunks_document_id", "standard_document_chunks", ["document_id"])
    _create_index_if_missing("idx_standard_chunks_library_id", "standard_document_chunks", ["library_id"])
    _create_index_if_missing("idx_standard_chunks_point_id", "standard_document_chunks", ["qdrant_point_id"])


def downgrade() -> None:
    pass
