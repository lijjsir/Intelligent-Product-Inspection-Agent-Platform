"""memory fail-fast outbox and indexes

Revision ID: 0078
Revises: 0077
Create Date: 2026-06-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0078"
down_revision = "0077"
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


def _create_index_if_missing(table_name: str, index_name: str, columns: list[str]) -> None:
    if _has_table(table_name) and not _has_index(table_name, index_name):
        op.create_index(index_name, table_name, columns)


def _drop_index_if_exists(table_name: str, index_name: str) -> None:
    if _has_table(table_name) and _has_index(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def upgrade() -> None:
    _add_column_if_missing(
        "memory_rollbacks",
        sa.Column("execution_status", sa.String(32), nullable=False, server_default="planned"),
    )
    _add_column_if_missing("memory_rollbacks", sa.Column("execution_error", sa.Text(), nullable=True))
    if _has_column("memory_rollbacks", "execution_status"):
        op.alter_column("memory_rollbacks", "execution_status", server_default=None)

    if not _has_table("memory_sync_outbox"):
        op.create_table(
            "memory_sync_outbox",
            sa.Column("id", sa.String(64), nullable=False),
            sa.Column("org_id", sa.BINARY(16), nullable=False),
            sa.Column("memory_id", sa.String(64), nullable=False),
            sa.Column("action", sa.String(64), nullable=False),
            sa.Column("target_backend", sa.String(32), nullable=False),
            sa.Column("payload_json", mysql.JSON(), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
            sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("trace_id", sa.String(128), nullable=True),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
            sa.Column(
                "updated_at",
                mysql.DATETIME(fsp=3),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"),
            ),
            sa.PrimaryKeyConstraint("id"),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
            comment="shared memory external sync outbox",
        )

    for table_name, index_name, columns in (
        ("memory_sync_outbox", "idx_memory_sync_claim", ["org_id", "status", "retry_count", "created_at"]),
        ("memory_sync_outbox", "idx_memory_sync_memory", ["org_id", "memory_id", "target_backend"]),
        ("memory_items", "idx_memory_org_status_type", ["org_id", "status", "memory_type"]),
        ("memory_items", "idx_memory_org_user_status", ["org_id", "user_id", "status"]),
        ("memory_items", "idx_memory_trace", ["org_id", "trace_id"]),
        ("memory_items", "idx_memory_candidate_status", ["org_id", "candidate_key", "status"]),
        ("memory_items", "idx_memory_expires", ["org_id", "status", "expires_at"]),
        (
            "memory_dependency_edges",
            "idx_mem_edge_source",
            ["org_id", "source_memory_id", "edge_type", "deleted_at"],
        ),
        (
            "memory_dependency_edges",
            "idx_mem_edge_target",
            ["org_id", "target_memory_id", "edge_type", "deleted_at"],
        ),
        ("memory_dependency_edges", "idx_mem_edge_type", ["org_id", "edge_type", "deleted_at"]),
        ("memory_rollbacks", "idx_memory_rollback_status", ["org_id", "execution_status", "created_at"]),
    ):
        _create_index_if_missing(table_name, index_name, columns)


def downgrade() -> None:
    for table_name, index_name in (
        ("memory_rollbacks", "idx_memory_rollback_status"),
        ("memory_dependency_edges", "idx_mem_edge_type"),
        ("memory_dependency_edges", "idx_mem_edge_target"),
        ("memory_dependency_edges", "idx_mem_edge_source"),
        ("memory_items", "idx_memory_expires"),
        ("memory_items", "idx_memory_candidate_status"),
        ("memory_items", "idx_memory_trace"),
        ("memory_items", "idx_memory_org_user_status"),
        ("memory_items", "idx_memory_org_status_type"),
        ("memory_sync_outbox", "idx_memory_sync_memory"),
        ("memory_sync_outbox", "idx_memory_sync_claim"),
    ):
        _drop_index_if_exists(table_name, index_name)
    if _has_table("memory_sync_outbox"):
        op.drop_table("memory_sync_outbox")
    _drop_column_if_exists("memory_rollbacks", "execution_error")
    _drop_column_if_exists("memory_rollbacks", "execution_status")
