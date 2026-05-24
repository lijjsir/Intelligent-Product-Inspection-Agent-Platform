"""add rag tree nodes and documents

Revision ID: 0026_rag_tree_nodes
Revises: 0025_quality_tracing_langfuse
Create Date: 2026-05-16
"""

from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0026_rag_tree_nodes"
down_revision = "0025_quality_tracing_langfuse"
branch_labels = None
depends_on = None

TS_DEFAULT = sa.text("CURRENT_TIMESTAMP(3)")
TS_UPDATE_DEFAULT = sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    rag_space_columns = {column["name"] for column in inspector.get_columns("rag_spaces")}

    if "folder_count" not in rag_space_columns:
        op.add_column("rag_spaces", sa.Column("folder_count", sa.Integer(), nullable=False, server_default="0"))
    if "chunk_count" not in rag_space_columns:
        op.add_column("rag_spaces", sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"))
    if "index_status" not in rag_space_columns:
        op.add_column("rag_spaces", sa.Column("index_status", sa.String(length=32), nullable=False, server_default="ready"))

    existing_tables = set(inspector.get_table_names())
    if "rag_nodes" not in existing_tables:
        op.create_table(
            "rag_nodes",
            sa.Column("id", sa.BINARY(16), nullable=False),
            sa.Column("org_id", sa.BINARY(16), nullable=False),
            sa.Column("rag_space_id", sa.BINARY(16), nullable=False),
            sa.Column("parent_id", sa.BINARY(16), nullable=True),
            sa.Column("created_by", sa.BINARY(16), nullable=True),
            sa.Column("node_type", sa.String(32), nullable=False, server_default="folder"),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("full_path", sa.Text(), nullable=False),
            sa.Column("depth", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(32), nullable=False, server_default="ready"),
            sa.Column("children_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
            sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
            comment="Tree nodes for RAG spaces",
        )
    rag_node_indexes = {index["name"] for index in inspector.get_indexes("rag_nodes")} if "rag_nodes" in set(sa.inspect(bind).get_table_names()) else set()
    if "idx_rag_nodes_org" not in rag_node_indexes:
        op.create_index("idx_rag_nodes_org", "rag_nodes", ["org_id"])
    if "idx_rag_nodes_space_parent" not in rag_node_indexes:
        op.create_index("idx_rag_nodes_space_parent", "rag_nodes", ["rag_space_id", "parent_id"])
    if "idx_rag_nodes_org_space" not in rag_node_indexes:
        op.create_index("idx_rag_nodes_org_space", "rag_nodes", ["org_id", "rag_space_id"])

    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if "rag_documents" not in existing_tables:
        op.create_table(
            "rag_documents",
            sa.Column("id", sa.BINARY(16), nullable=False),
            sa.Column("org_id", sa.BINARY(16), nullable=False),
            sa.Column("rag_space_id", sa.BINARY(16), nullable=False),
            sa.Column("node_id", sa.BINARY(16), nullable=False),
            sa.Column("uploaded_by", sa.BINARY(16), nullable=True),
            sa.Column("file_name", sa.String(255), nullable=False),
            sa.Column("content_type", sa.String(120), nullable=True),
            sa.Column("file_url", sa.Text(), nullable=False),
            sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("checksum_sha256", sa.String(64), nullable=False, server_default=""),
            sa.Column("storage_backend", sa.String(32), nullable=False, server_default="local"),
            sa.Column("object_key", sa.Text(), nullable=False),
            sa.Column("parse_status", sa.String(32), nullable=False, server_default="parsed"),
            sa.Column("index_status", sa.String(32), nullable=False, server_default="ready"),
            sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
            sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
            comment="Document metadata for tree file nodes",
        )
    rag_document_indexes = {index["name"] for index in inspector.get_indexes("rag_documents")} if "rag_documents" in set(sa.inspect(bind).get_table_names()) else set()
    if "idx_rag_documents_org" not in rag_document_indexes:
        op.create_index("idx_rag_documents_org", "rag_documents", ["org_id"])
    if "idx_rag_documents_space" not in rag_document_indexes:
        op.create_index("idx_rag_documents_space", "rag_documents", ["rag_space_id"])
    if "idx_rag_documents_node" not in rag_document_indexes:
        op.create_index("idx_rag_documents_node", "rag_documents", ["node_id"])

    _migrate_existing_files()


def downgrade() -> None:
    op.drop_index("idx_rag_documents_node", table_name="rag_documents")
    op.drop_index("idx_rag_documents_space", table_name="rag_documents")
    op.drop_index("idx_rag_documents_org", table_name="rag_documents")
    op.drop_table("rag_documents")

    op.drop_index("idx_rag_nodes_org_space", table_name="rag_nodes")
    op.drop_index("idx_rag_nodes_space_parent", table_name="rag_nodes")
    op.drop_index("idx_rag_nodes_org", table_name="rag_nodes")
    op.drop_table("rag_nodes")

    op.drop_column("rag_spaces", "index_status")
    op.drop_column("rag_spaces", "chunk_count")
    op.drop_column("rag_spaces", "folder_count")


def _migrate_existing_files() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    rag_space_files = sa.Table("rag_space_files", metadata, autoload_with=bind)
    rag_spaces = sa.Table("rag_spaces", metadata, autoload_with=bind)
    rag_nodes = sa.Table("rag_nodes", metadata, autoload_with=bind)
    rag_documents = sa.Table("rag_documents", metadata, autoload_with=bind)

    rows = list(bind.execute(sa.select(rag_space_files)).mappings())
    if not rows:
        return

    node_rows: list[dict[str, object]] = []
    document_rows: list[dict[str, object]] = []
    counters: dict[bytes, dict[str, int]] = {}

    for order, row in enumerate(rows, start=1):
        node_id = uuid.uuid4().bytes
        document_id = uuid.uuid4().bytes
        rag_space_id = row["rag_space_id"]
        deleted_at = row["deleted_at"]
        active = deleted_at is None
        if active:
            info = counters.setdefault(rag_space_id, {"file_count": 0, "chunk_count": 0})
            info["file_count"] += 1
            info["chunk_count"] += 1

        node_rows.append(
            {
                "id": node_id,
                "org_id": row["org_id"],
                "rag_space_id": rag_space_id,
                "parent_id": None,
                "created_by": row["uploaded_by"],
                "node_type": "file",
                "name": row["file_name"],
                "full_path": row["file_name"],
                "depth": 0,
                "sort_order": order,
                "status": row["status"] or "ready",
                "children_count": 0,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "deleted_at": deleted_at,
            }
        )
        document_rows.append(
            {
                "id": document_id,
                "org_id": row["org_id"],
                "rag_space_id": rag_space_id,
                "node_id": node_id,
                "uploaded_by": row["uploaded_by"],
                "file_name": row["file_name"],
                "content_type": row["content_type"],
                "file_url": row["file_url"],
                "size_bytes": row["size_bytes"],
                "checksum_sha256": "",
                "storage_backend": "local",
                "object_key": row["file_url"],
                "parse_status": "parsed",
                "index_status": row["status"] or "ready",
                "chunk_count": 1 if active else 0,
                "error_message": None,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "deleted_at": deleted_at,
            }
        )

    if node_rows:
        bind.execute(rag_nodes.insert(), node_rows)
    if document_rows:
        bind.execute(rag_documents.insert(), document_rows)

    for rag_space_id, info in counters.items():
        bind.execute(
            rag_spaces.update()
            .where(rag_spaces.c.id == rag_space_id)
            .values(
                file_count=info["file_count"],
                folder_count=0,
                chunk_count=info["chunk_count"],
                index_status="ready",
            )
        )
