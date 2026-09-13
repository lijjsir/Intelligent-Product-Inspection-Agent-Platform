"""unify memory governance provenance evidence scope and review state

Revision ID: 0095_unify_memory_governance
Revises: 0094_memory_share_approval_workflow
Create Date: 2026-08-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql


revision = "0095_unify_memory_governance"
down_revision = "0094_memory_share_approval_workflow"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def _has_column(table: str, name: str) -> bool:
    return any(column["name"] == name for column in _inspector().get_columns(table))


def _has_index(table: str, name: str) -> bool:
    return any(index["name"] == name for index in _inspector().get_indexes(table))


def _add_columns(table: str, columns: tuple[sa.Column, ...]) -> None:
    for column in columns:
        if not _has_column(table, str(column.name)):
            op.add_column(table, column)


def upgrade() -> None:
    _add_columns(
        "memory_items",
        (
            sa.Column("applicability_json", mysql.JSON(), nullable=True),
            sa.Column("origin_evidence_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("independent_support_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("human_confirmation_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("opposition_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_evidence_at", sa.DateTime(), nullable=True),
            sa.Column("review_status", sa.String(32), nullable=False, server_default="candidate"),
            sa.Column("governance_target_scope_type", sa.String(32), nullable=True),
            sa.Column("governance_target_scope_id", sa.String(128), nullable=True),
            sa.Column("readiness_status", sa.String(32), nullable=False, server_default="collecting"),
            sa.Column("readiness_blockers", mysql.JSON(), nullable=True),
            sa.Column("migration_review_required", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("migration_review_reason", sa.Text(), nullable=True),
        ),
    )
    _add_columns(
        "memory_scope_bindings",
        (
            sa.Column("binding_kind", sa.String(32), nullable=False, server_default="home"),
            sa.Column("binding_status", sa.String(32), nullable=False, server_default="active"),
            sa.Column("approved_by", sa.BINARY(16), nullable=True),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
            sa.Column("source_transfer_id", sa.BINARY(16), nullable=True),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
        ),
    )

    if not _has_table("memory_origins"):
        op.create_table(
            "memory_origins",
            sa.Column("id", sa.BINARY(16), primary_key=True),
            sa.Column("org_id", sa.BINARY(16), nullable=False),
            sa.Column("memory_id", sa.String(64), nullable=False),
            sa.Column("origin_kind", sa.String(64), nullable=False),
            sa.Column("source_type", sa.String(64), nullable=False),
            sa.Column("source_id", sa.String(128), nullable=False),
            sa.Column("trace_id", sa.String(128), nullable=True),
            sa.Column("dedupe_key", sa.String(256), nullable=False),
            sa.Column("source_span", mysql.JSON(), nullable=True),
            sa.Column("metadata_json", mysql.JSON(), nullable=True),
            sa.Column("occurred_at", sa.DateTime(), nullable=True),
            sa.Column(
                "created_at",
                mysql.DATETIME(fsp=3),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP(3)"),
            ),
            sa.UniqueConstraint("org_id", "memory_id", "dedupe_key", name="uq_memory_origins_dedupe"),
        )
        op.create_index("idx_memory_origins_memory", "memory_origins", ["org_id", "memory_id"])
        op.create_index(
            "idx_memory_origins_source",
            "memory_origins",
            ["org_id", "origin_kind", "source_type", "source_id"],
        )

    if not _has_table("memory_evidence"):
        op.create_table(
            "memory_evidence",
            sa.Column("id", sa.BINARY(16), primary_key=True),
            sa.Column("org_id", sa.BINARY(16), nullable=False),
            sa.Column("memory_id", sa.String(64), nullable=False),
            sa.Column("evidence_role", sa.String(32), nullable=False),
            sa.Column("source_kind", sa.String(64), nullable=False),
            sa.Column("source_type", sa.String(64), nullable=False),
            sa.Column("source_id", sa.String(128), nullable=False),
            sa.Column("independence_key", sa.String(256), nullable=False),
            sa.Column("trace_id", sa.String(128), nullable=True),
            sa.Column("task_id", sa.String(128), nullable=True),
            sa.Column("rag_space_id", sa.String(64), nullable=True),
            sa.Column("document_id", sa.String(64), nullable=True),
            sa.Column("chunk_id", sa.String(128), nullable=True),
            sa.Column("evidence_pointer", mysql.JSON(), nullable=True),
            sa.Column("confidence", sa.DECIMAL(5, 4), nullable=True),
            sa.Column("weight", sa.DECIMAL(5, 4), nullable=True),
            sa.Column("occurred_at", sa.DateTime(), nullable=True),
            sa.Column(
                "created_at",
                mysql.DATETIME(fsp=3),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP(3)"),
            ),
            sa.UniqueConstraint(
                "org_id",
                "memory_id",
                "evidence_role",
                "independence_key",
                name="uq_memory_evidence_independence",
            ),
        )
        op.create_index(
            "idx_memory_evidence_memory",
            "memory_evidence",
            ["org_id", "memory_id", "evidence_role"],
        )
        op.create_index(
            "idx_memory_evidence_source",
            "memory_evidence",
            ["org_id", "source_kind", "source_type", "source_id"],
        )

    if not _has_index("memory_items", "idx_memory_items_org_review"):
        op.create_index("idx_memory_items_org_review", "memory_items", ["org_id", "review_status", "updated_at"])
    if not _has_index("memory_items", "idx_memory_items_governance_target"):
        op.create_index(
            "idx_memory_items_governance_target",
            "memory_items",
            ["org_id", "governance_target_scope_type", "readiness_status"],
        )
    if not _has_index("memory_scope_bindings", "idx_memory_scope_bindings_status"):
        op.create_index(
            "idx_memory_scope_bindings_status",
            "memory_scope_bindings",
            ["org_id", "scope_type", "scope_id", "binding_status"],
        )
    # Keep ORM index=True fields in sync even when 0094 was already applied.
    for table, name, columns in (
        (
            "memory_scope_bindings",
            "ix_memory_scope_bindings_approved_by",
            ["approved_by"],
        ),
        (
            "memory_scope_bindings",
            "ix_memory_scope_bindings_source_transfer_id",
            ["source_transfer_id"],
        ),
        (
            "memory_transfer_logs",
            "ix_memory_transfer_logs_requested_by",
            ["requested_by"],
        ),
        (
            "memory_transfer_logs",
            "ix_memory_transfer_logs_decided_by",
            ["decided_by"],
        ),
    ):
        if _has_table(table) and not _has_index(table, name):
            op.create_index(name, table, columns)

    if op.get_bind().dialect.name == "mysql":
        op.execute(
            "UPDATE memory_items SET review_status = CASE "
            "WHEN status = 'candidate' THEN 'candidate' "
            "WHEN status IN ('confirmed', 'active') THEN 'approved' "
            "WHEN status IN ('disputed', 'contested') THEN 'disputed' "
            "WHEN status IN ('rejected', 'disabled') THEN 'rejected' "
            "WHEN status = 'isolated' THEN 'isolated' "
            "WHEN status = 'superseded' THEN 'superseded' "
            "ELSE 'candidate' END, "
            "migration_review_required = CASE "
            "WHEN status IN ('candidate','confirmed','active','disputed','contested','rejected','disabled','isolated','superseded') "
            "THEN migration_review_required ELSE 1 END, "
            "migration_review_reason = CASE "
            "WHEN status IN ('candidate','confirmed','active','disputed','contested','rejected','disabled','isolated','superseded') "
            "THEN migration_review_reason ELSE CONCAT('unmapped legacy status: ', status) END"
        )
        op.execute(
            "UPDATE memory_items SET memory_type = COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(content_json, '$.memory_type')), ''), memory_type)"
        )
        op.execute(
            "UPDATE memory_items SET applicability_json = JSON_OBJECT("
            "'task_id', task_id, 'product_line', product_line, 'rag_space_id', rag_space_id, "
            "'standard_code', standard_code, 'standard_version', standard_version, "
            "'target_market', target_market, 'product_category', product_category, "
            "'business_context', JSON_EXTRACT(scope_json, '$.business_context'), "
            "'task_ids', JSON_EXTRACT(scope_json, '$.task_ids'), "
            "'product_ids', JSON_EXTRACT(scope_json, '$.product_ids'), "
            "'batch_nos', JSON_EXTRACT(scope_json, '$.batch_nos'), "
            "'standard_ids', JSON_EXTRACT(scope_json, '$.standard_ids')) "
            "WHERE applicability_json IS NULL"
        )
        op.execute(
            "UPDATE memory_items SET governance_target_scope_type = 'org_space', "
            "governance_target_scope_id = BIN_TO_UUID(org_id) "
            "WHERE governance_target_scope_type IS NULL "
            "AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(content_json, '$.source_type')), '') <> 'meeting' "
            "AND (task_id IS NOT NULL OR rag_space_id IS NOT NULL OR created_by_type = 'agent')"
        )
        op.execute(
            "UPDATE memory_scope_bindings b JOIN memory_items i "
            "ON i.org_id = b.org_id AND i.memory_id = b.memory_id "
            "SET b.binding_kind = CASE "
            "WHEN b.scope_type = COALESCE(JSON_UNQUOTE(JSON_EXTRACT(i.scope_json, '$.scope_type')), '') "
            "AND b.scope_id = COALESCE(JSON_UNQUOTE(JSON_EXTRACT(i.scope_json, '$.scope_id')), '') "
            "THEN 'home' ELSE 'shared' END, "
            "b.binding_status = 'active', b.approved_by = COALESCE(b.approved_by, b.created_by), "
            "b.approved_at = COALESCE(b.approved_at, b.created_at) "
            "WHERE b.deleted_at IS NULL"
        )
        op.execute(
            "UPDATE memory_transfer_logs SET deleted_at = COALESCE(deleted_at, updated_at), "
            "decision_note = COALESCE(decision_note, 'legacy same-scope audit; retained as soft-deleted history') "
            "WHERE deleted_at IS NULL AND from_scope_type = to_scope_type AND from_scope_id = to_scope_id"
        )
        op.execute(
            "UPDATE memory_transfer_logs SET status = CASE "
            "WHEN status IN ('executed','confirmed') THEN 'approved' "
            "WHEN status = 'candidate' THEN 'pending_approval' "
            "ELSE status END WHERE deleted_at IS NULL"
        )


def downgrade() -> None:
    if _has_index("memory_scope_bindings", "idx_memory_scope_bindings_status"):
        op.drop_index("idx_memory_scope_bindings_status", table_name="memory_scope_bindings")
    if _has_index("memory_items", "idx_memory_items_governance_target"):
        op.drop_index("idx_memory_items_governance_target", table_name="memory_items")
    if _has_index("memory_items", "idx_memory_items_org_review"):
        op.drop_index("idx_memory_items_org_review", table_name="memory_items")
    if _has_table("memory_evidence"):
        op.drop_table("memory_evidence")
    if _has_table("memory_origins"):
        op.drop_table("memory_origins")
    for name in ("revoked_at", "source_transfer_id", "approved_at", "approved_by", "binding_status", "binding_kind"):
        if _has_column("memory_scope_bindings", name):
            op.drop_column("memory_scope_bindings", name)
    for name in (
        "migration_review_reason",
        "migration_review_required",
        "readiness_blockers",
        "readiness_status",
        "governance_target_scope_id",
        "governance_target_scope_type",
        "review_status",
        "last_evidence_at",
        "opposition_count",
        "human_confirmation_count",
        "independent_support_count",
        "origin_evidence_count",
        "applicability_json",
    ):
        if _has_column("memory_items", name):
            op.drop_column("memory_items", name)
