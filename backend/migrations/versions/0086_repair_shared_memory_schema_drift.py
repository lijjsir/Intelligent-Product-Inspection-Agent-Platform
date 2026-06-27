"""repair shared memory schema drift

Revision ID: 0086_repair_shared_memory_schema_drift
Revises: 0085_merge_standard_library_rag_schema
Create Date: 2026-06-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0086_repair_shared_memory_schema_drift"
down_revision = "0085_merge_standard_library_rag_schema"
branch_labels = None
depends_on = None

TS_DEFAULT = sa.text("CURRENT_TIMESTAMP(3)")
TS_UPDATE_DEFAULT = sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if _has_table(table_name) and not _has_column(table_name, column.name):
        op.add_column(table_name, column)


def _create_index_if_missing(table_name: str, index_name: str, columns: list[str], *, unique: bool = False) -> None:
    if _has_table(table_name) and not _has_index(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    for column in (
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("source_trace_id", sa.String(128), nullable=True),
        sa.Column("source_message_id", sa.String(128), nullable=True),
        sa.Column("source_task_id", sa.String(128), nullable=True),
        sa.Column("task_id", sa.String(128), nullable=True),
        sa.Column("product_line", sa.String(128), nullable=True),
        sa.Column("rag_space_id", sa.String(64), nullable=True),
        sa.Column("standard_code", sa.String(128), nullable=True),
        sa.Column("standard_version", sa.String(64), nullable=True),
        sa.Column("production_date", sa.Date(), nullable=True),
        sa.Column("target_market", sa.String(64), nullable=True),
        sa.Column("product_category", sa.String(128), nullable=True),
        sa.Column("index_status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("index_error", sa.Text(), nullable=True),
        sa.Column("vector_status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("graph_status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("last_vector_sync_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("last_graph_sync_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("vector_error", sa.Text(), nullable=True),
        sa.Column("graph_error", sa.Text(), nullable=True),
        sa.Column("policy_key", sa.String(128), nullable=True),
        sa.Column("policy_version", sa.String(32), nullable=True),
        sa.Column("candidate_key", sa.String(256), nullable=True),
        sa.Column("canonical_claim", mysql.JSON(), nullable=True),
        sa.Column("support_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("negative_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("conflict_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("rag_evidence_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("agent_verifier_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("human_approved", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("promotion_score", sa.DECIMAL(6, 4), nullable=True),
        sa.Column("last_supported_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("last_indexed_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("last_accessed_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("access_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
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

    for column_name in (
        "index_status",
        "vector_status",
        "graph_status",
        "support_count",
        "negative_count",
        "conflict_count",
        "rag_evidence_count",
        "agent_verifier_count",
        "human_approved",
        "access_count",
    ):
        if _has_column("memory_items", column_name):
            op.alter_column("memory_items", column_name, server_default=None)

    for index_name, columns, unique in (
        ("uk_memory_org_memory_id", ["org_id", "memory_id"], True),
        ("uq_memory_items_org_idempotency_key", ["org_id", "idempotency_key"], True),
        ("idx_memory_items_org_index_status", ["org_id", "index_status", "updated_at"], False),
        ("idx_memory_items_source_trace", ["org_id", "source_trace_id"], False),
        ("idx_memory_candidate_key", ["org_id", "memory_type", "status", "candidate_key"], False),
        ("idx_memory_status_updated", ["org_id", "status", "updated_at"], False),
        ("idx_memory_scope_status", ["org_id", "memory_type", "status", "user_id"], False),
        ("idx_memory_org_status_type", ["org_id", "status", "memory_type"], False),
        ("idx_memory_org_user_status", ["org_id", "user_id", "status"], False),
        ("idx_memory_trace", ["org_id", "trace_id"], False),
        ("idx_memory_candidate_status", ["org_id", "candidate_key", "status"], False),
        ("idx_memory_expires", ["org_id", "status", "expires_at"], False),
        ("idx_memory_retrieval_global", ["org_id", "status", "memory_type", "vector_status", "updated_at"], False),
        ("idx_memory_retrieval_user", ["org_id", "user_id", "status", "memory_type", "vector_status", "updated_at"], False),
        ("idx_memory_product_line", ["org_id", "status", "memory_type", "product_line", "updated_at"], False),
        ("idx_memory_rag_space", ["org_id", "status", "memory_type", "rag_space_id", "updated_at"], False),
        ("idx_memory_task", ["org_id", "status", "task_id", "updated_at"], False),
        ("idx_memory_graph_status", ["org_id", "graph_status", "updated_at"], False),
    ):
        _create_index_if_missing("memory_items", index_name, columns, unique=unique)

    _add_column_if_missing("memory_rollbacks", sa.Column("execution_status", sa.String(32), nullable=False, server_default="planned"))
    _add_column_if_missing("memory_rollbacks", sa.Column("execution_error", sa.Text(), nullable=True))
    if _has_column("memory_rollbacks", "execution_status"):
        op.alter_column("memory_rollbacks", "execution_status", server_default=None)

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
        )
    _create_index_if_missing("memory_candidate_supports", "idx_memory_support_candidate", ["org_id", "candidate_memory_id", "created_at"])
    _create_index_if_missing("memory_candidate_supports", "idx_memory_support_trace", ["org_id", "trace_id"])

    if not _has_table("memory_sync_outbox"):
        op.create_table(
            "memory_sync_outbox",
            sa.Column("id", sa.String(64), nullable=False),
            sa.Column("org_id", sa.BINARY(16), nullable=False),
            sa.Column("memory_id", sa.String(64), nullable=False),
            sa.Column("action", sa.String(64), nullable=False),
            sa.Column("target_backend", sa.String(32), nullable=False),
            sa.Column("payload_json", mysql.JSON(), nullable=False),
            sa.Column("idempotency_key", sa.String(256), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
            sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("trace_id", sa.String(128), nullable=True),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
            sa.PrimaryKeyConstraint("id"),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
        )
    else:
        _add_column_if_missing("memory_sync_outbox", sa.Column("idempotency_key", sa.String(256), nullable=True))

    _create_index_if_missing("memory_sync_outbox", "idx_memory_sync_claim", ["org_id", "status", "retry_count", "created_at"])
    _create_index_if_missing("memory_sync_outbox", "idx_memory_sync_memory", ["org_id", "memory_id", "target_backend"])
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
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("org_id", "conflict_id", name="uk_memory_conflict_org_conflict"),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
        )
    _create_index_if_missing("memory_conflict_cases", "idx_memory_conflict_case_status", ["org_id", "status", "created_at"])


def downgrade() -> None:
    pass
