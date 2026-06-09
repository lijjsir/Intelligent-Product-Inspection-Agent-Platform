"""add shared memory operational fields

Revision ID: 0075
Revises: 0074
Create Date: 2026-06-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0075"
down_revision = "0074"
branch_labels = None
depends_on = None


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


def _create_index_if_missing(
    table_name: str,
    index_name: str,
    columns: list[str],
    *,
    unique: bool = False,
) -> None:
    if _has_table(table_name) and not _has_index(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def _drop_index_if_exists(table_name: str, index_name: str) -> None:
    if _has_table(table_name) and _has_index(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def upgrade():
    _add_column_if_missing("memory_items", sa.Column("idempotency_key", sa.String(128), nullable=True))
    _add_column_if_missing("memory_items", sa.Column("source_trace_id", sa.String(128), nullable=True))
    _add_column_if_missing("memory_items", sa.Column("source_message_id", sa.String(128), nullable=True))
    _add_column_if_missing("memory_items", sa.Column("source_task_id", sa.String(128), nullable=True))
    _add_column_if_missing(
        "memory_items",
        sa.Column("index_status", sa.String(32), nullable=False, server_default="pending"),
    )
    _add_column_if_missing("memory_items", sa.Column("index_error", sa.Text(), nullable=True))
    _add_column_if_missing("memory_items", sa.Column("policy_key", sa.String(128), nullable=True))
    _add_column_if_missing("memory_items", sa.Column("policy_version", sa.String(32), nullable=True))
    _add_column_if_missing(
        "memory_items",
        sa.Column("last_indexed_at", mysql.DATETIME(fsp=3), nullable=True),
    )
    _add_column_if_missing(
        "memory_items",
        sa.Column("last_accessed_at", mysql.DATETIME(fsp=3), nullable=True),
    )
    _add_column_if_missing(
        "memory_items",
        sa.Column("access_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )

    if _has_column("memory_items", "index_status"):
        op.alter_column("memory_items", "index_status", server_default=None)
    if _has_column("memory_items", "access_count"):
        op.alter_column("memory_items", "access_count", server_default=None)

    _create_index_if_missing(
        "memory_items",
        "uq_memory_items_org_idempotency_key",
        ["org_id", "idempotency_key"],
        unique=True,
    )
    _create_index_if_missing(
        "memory_items",
        "idx_memory_items_org_index_status",
        ["org_id", "index_status", "updated_at"],
    )
    _create_index_if_missing(
        "memory_items",
        "idx_memory_items_source_trace",
        ["org_id", "source_trace_id"],
    )


def downgrade():
    _drop_index_if_exists("memory_items", "idx_memory_items_source_trace")
    _drop_index_if_exists("memory_items", "idx_memory_items_org_index_status")
    _drop_index_if_exists("memory_items", "uq_memory_items_org_idempotency_key")

    _drop_column_if_exists("memory_items", "access_count")
    _drop_column_if_exists("memory_items", "last_accessed_at")
    _drop_column_if_exists("memory_items", "last_indexed_at")
    _drop_column_if_exists("memory_items", "policy_version")
    _drop_column_if_exists("memory_items", "policy_key")
    _drop_column_if_exists("memory_items", "index_error")
    _drop_column_if_exists("memory_items", "index_status")
    _drop_column_if_exists("memory_items", "source_task_id")
    _drop_column_if_exists("memory_items", "source_message_id")
    _drop_column_if_exists("memory_items", "source_trace_id")
    _drop_column_if_exists("memory_items", "idempotency_key")
