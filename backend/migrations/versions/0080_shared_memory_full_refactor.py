"""shared memory full refactor

Revision ID: 0080_shared_memory_full_refactor
Revises: 0079_drop_memory_dependency_edges
Create Date: 2026-06-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0080_shared_memory_full_refactor"
down_revision = "0079_drop_memory_dependency_edges"
branch_labels = None
depends_on = None

TS_DEFAULT = sa.text("CURRENT_TIMESTAMP(3)")


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(col["name"] == column_name for col in _inspector().get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if _has_table(table_name) and not _has_column(table_name, column.name):
        op.add_column(table_name, column)


def _drop_column_if_exists(table_name: str, column_name: str) -> None:
    if _has_table(table_name) and _has_column(table_name, column_name):
        op.drop_column(table_name, column_name)


def _create_index_if_missing(table_name: str, index_name: str, columns: list[str], *, unique: bool = False) -> None:
    if _has_table(table_name) and not _has_index(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def _drop_index_if_exists(table_name: str, index_name: str) -> None:
    if _has_table(table_name) and _has_index(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def upgrade() -> None:
    for column in (
        sa.Column("vector_status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("graph_status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("last_vector_sync_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("last_graph_sync_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("vector_error", sa.Text(), nullable=True),
        sa.Column("graph_error", sa.Text(), nullable=True),
        sa.Column("task_id", sa.String(128), nullable=True),
        sa.Column("product_line", sa.String(128), nullable=True),
        sa.Column("rag_space_id", sa.String(64), nullable=True),
        sa.Column("standard_code", sa.String(128), nullable=True),
        sa.Column("standard_version", sa.String(64), nullable=True),
        sa.Column("production_date", sa.Date(), nullable=True),
        sa.Column("target_market", sa.String(64), nullable=True),
        sa.Column("product_category", sa.String(128), nullable=True),
    ):
        _add_column_if_missing("memory_items", column)

    if _has_table("memory_items"):
        op.execute(
            """
            UPDATE memory_items
            SET
              vector_status = COALESCE(NULLIF(vector_status, ''), index_status, 'pending'),
              graph_status = COALESCE(NULLIF(graph_status, ''), 'pending'),
              task_id = COALESCE(task_id, JSON_UNQUOTE(JSON_EXTRACT(scope_json, '$.task_id'))),
              product_line = COALESCE(product_line, JSON_UNQUOTE(JSON_EXTRACT(scope_json, '$.product_line'))),
              rag_space_id = COALESCE(rag_space_id, JSON_UNQUOTE(JSON_EXTRACT(scope_json, '$.rag_space_id'))),
              standard_code = COALESCE(standard_code, JSON_UNQUOTE(JSON_EXTRACT(scope_json, '$.standard_code'))),
              standard_version = COALESCE(standard_version, JSON_UNQUOTE(JSON_EXTRACT(scope_json, '$.standard_version'))),
              target_market = COALESCE(target_market, JSON_UNQUOTE(JSON_EXTRACT(scope_json, '$.target_market'))),
              product_category = COALESCE(product_category, JSON_UNQUOTE(JSON_EXTRACT(scope_json, '$.product_category')))
            """
        )
        for column_name in ("vector_status", "graph_status"):
            if _has_column("memory_items", column_name):
                op.alter_column("memory_items", column_name, server_default=None)

    for index_name, columns, unique in (
        ("uk_memory_org_memory_id", ["org_id", "memory_id"], True),
        ("idx_memory_retrieval_global", ["org_id", "status", "memory_type", "vector_status", "updated_at"], False),
        ("idx_memory_retrieval_user", ["org_id", "user_id", "status", "memory_type", "vector_status", "updated_at"], False),
        ("idx_memory_product_line", ["org_id", "status", "memory_type", "product_line", "updated_at"], False),
        ("idx_memory_rag_space", ["org_id", "status", "memory_type", "rag_space_id", "updated_at"], False),
        ("idx_memory_task", ["org_id", "status", "task_id", "updated_at"], False),
        ("idx_memory_graph_status", ["org_id", "graph_status", "updated_at"], False),
    ):
        _create_index_if_missing("memory_items", index_name, columns, unique=unique)

    _add_column_if_missing("memory_sync_outbox", sa.Column("idempotency_key", sa.String(256), nullable=True))
    _create_index_if_missing("memory_sync_outbox", "idx_memory_sync_idempotency", ["org_id", "idempotency_key"], unique=True)

    if not _has_table("memory_conflict_cases"):
        op.create_table(
            "memory_conflict_cases",
            sa.Column("id", sa.String(64), nullable=False),
            sa.Column("org_id", sa.BINARY(16), nullable=False),
            sa.Column("conflict_id", sa.String(128), nullable=False),
            sa.Column("source_memory_id", sa.String(64), nullable=False),
            sa.Column("target_memory_id", sa.String(64), nullable=False),
            sa.Column("conflict_type", sa.String(64), nullable=False),
            sa.Column("severity", sa.String(32), nullable=False, server_default="medium"),
            sa.Column("status", sa.String(32), nullable=False, server_default="open"),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("applicability_context_json", mysql.JSON(), nullable=True),
            sa.Column("resolution", sa.Text(), nullable=True),
            sa.Column("resolved_by", sa.String(128), nullable=True),
            sa.Column("resolved_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("org_id", "conflict_id", name="uk_memory_conflict_org_conflict"),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
        )
    _create_index_if_missing("memory_conflict_cases", "idx_memory_conflict_case_status", ["org_id", "status", "created_at"])

    _add_column_if_missing("graph_checkpoints", sa.Column("expires_at", mysql.DATETIME(fsp=3), nullable=True))
    _add_column_if_missing("graph_checkpoints", sa.Column("payload_ref", sa.String(512), nullable=True))
    _create_index_if_missing("graph_checkpoints", "uk_graph_checkpoint_identity", ["thread_id", "checkpoint_ns", "checkpoint_id"], unique=True)
    _create_index_if_missing("graph_checkpoints", "idx_graph_checkpoint_ttl", ["expires_at"])


def downgrade() -> None:
    _drop_index_if_exists("graph_checkpoints", "idx_graph_checkpoint_ttl")
    _drop_index_if_exists("graph_checkpoints", "uk_graph_checkpoint_identity")
    _drop_column_if_exists("graph_checkpoints", "payload_ref")
    _drop_column_if_exists("graph_checkpoints", "expires_at")

    if _has_table("memory_conflict_cases"):
        op.drop_table("memory_conflict_cases")

    _drop_index_if_exists("memory_sync_outbox", "idx_memory_sync_idempotency")
    _drop_column_if_exists("memory_sync_outbox", "idempotency_key")

    for index_name in (
        "idx_memory_graph_status",
        "idx_memory_task",
        "idx_memory_rag_space",
        "idx_memory_product_line",
        "idx_memory_retrieval_user",
        "idx_memory_retrieval_global",
        "uk_memory_org_memory_id",
    ):
        _drop_index_if_exists("memory_items", index_name)

    for column_name in (
        "product_category",
        "target_market",
        "production_date",
        "standard_version",
        "standard_code",
        "rag_space_id",
        "product_line",
        "task_id",
        "graph_error",
        "vector_error",
        "last_graph_sync_at",
        "last_vector_sync_at",
        "graph_status",
        "vector_status",
    ):
        _drop_column_if_exists("memory_items", column_name)
