"""add candidate memory support tracking

Revision ID: 0077
Revises: 0076
Create Date: 2026-06-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0077"
down_revision = "0076"
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
    _add_column_if_missing("memory_items", sa.Column("candidate_key", sa.String(256), nullable=True))
    _add_column_if_missing("memory_items", sa.Column("canonical_claim", mysql.JSON(), nullable=True))
    _add_column_if_missing(
        "memory_items",
        sa.Column("support_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    _add_column_if_missing(
        "memory_items",
        sa.Column("negative_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    _add_column_if_missing(
        "memory_items",
        sa.Column("conflict_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    _add_column_if_missing(
        "memory_items",
        sa.Column("rag_evidence_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    _add_column_if_missing(
        "memory_items",
        sa.Column("agent_verifier_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    _add_column_if_missing(
        "memory_items",
        sa.Column("human_approved", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    _add_column_if_missing("memory_items", sa.Column("promotion_score", sa.DECIMAL(6, 4), nullable=True))
    _add_column_if_missing("memory_items", sa.Column("last_supported_at", mysql.DATETIME(fsp=3), nullable=True))

    for column_name in (
        "support_count",
        "negative_count",
        "conflict_count",
        "rag_evidence_count",
        "agent_verifier_count",
        "human_approved",
    ):
        if _has_column("memory_items", column_name):
            op.alter_column("memory_items", column_name, server_default=None)

    _create_index_if_missing(
        "memory_items",
        "idx_memory_candidate_key",
        ["org_id", "memory_type", "status", "candidate_key"],
    )
    _create_index_if_missing(
        "memory_items",
        "idx_memory_status_updated",
        ["org_id", "status", "updated_at"],
    )
    _create_index_if_missing(
        "memory_items",
        "idx_memory_scope_status",
        ["org_id", "memory_type", "status", "user_id"],
    )

    if not _has_table("memory_candidate_supports"):
        op.create_table(
            "memory_candidate_supports",
            sa.Column("id", sa.BINARY(16), nullable=False),
            sa.Column("org_id", sa.BINARY(16), nullable=False),
            sa.Column("candidate_memory_id", sa.String(64), nullable=False),
            sa.Column("support_type", sa.String(64), nullable=False),
            sa.Column("source_kind", sa.String(64), nullable=True),
            sa.Column("source_agent", sa.String(128), nullable=True),
            sa.Column("task_id", sa.String(128), nullable=True),
            sa.Column("trace_id", sa.String(128), nullable=True),
            sa.Column("rag_space_id", sa.String(64), nullable=True),
            sa.Column("document_id", sa.String(64), nullable=True),
            sa.Column("chunk_id", sa.String(128), nullable=True),
            sa.Column("evidence_pointer", mysql.JSON(), nullable=True),
            sa.Column("confidence", sa.DECIMAL(5, 4), nullable=True),
            sa.Column("similarity", sa.DECIMAL(5, 4), nullable=True),
            sa.Column("weight", sa.DECIMAL(5, 4), nullable=True),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
            sa.PrimaryKeyConstraint("id"),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
            comment="candidate memory support evidence details",
        )

    _create_index_if_missing(
        "memory_candidate_supports",
        "idx_candidate_support_memory",
        ["org_id", "candidate_memory_id", "created_at"],
    )
    _create_index_if_missing(
        "memory_candidate_supports",
        "idx_candidate_support_trace",
        ["org_id", "trace_id"],
    )
    _create_index_if_missing(
        "memory_candidate_supports",
        "idx_candidate_support_task",
        ["org_id", "task_id"],
    )
    _create_index_if_missing(
        "memory_candidate_supports",
        "idx_candidate_support_type",
        ["org_id", "support_type", "created_at"],
    )


def downgrade() -> None:
    for index_name in (
        "idx_candidate_support_type",
        "idx_candidate_support_task",
        "idx_candidate_support_trace",
        "idx_candidate_support_memory",
    ):
        _drop_index_if_exists("memory_candidate_supports", index_name)
    if _has_table("memory_candidate_supports"):
        op.drop_table("memory_candidate_supports")

    _drop_index_if_exists("memory_items", "idx_memory_scope_status")
    _drop_index_if_exists("memory_items", "idx_memory_status_updated")
    _drop_index_if_exists("memory_items", "idx_memory_candidate_key")
    for column_name in (
        "last_supported_at",
        "promotion_score",
        "human_approved",
        "agent_verifier_count",
        "rag_evidence_count",
        "conflict_count",
        "negative_count",
        "support_count",
        "canonical_claim",
        "candidate_key",
    ):
        _drop_column_if_exists("memory_items", column_name)
