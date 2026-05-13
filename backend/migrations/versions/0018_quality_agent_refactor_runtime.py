"""add quality agent refactor runtime metadata and governance tables

Revision ID: 0018_quality_agent_runtime
Revises: 0017_user_token_usage_summary
Create Date: 2026-04-04
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op


revision = "0018_quality_agent_runtime"
down_revision = "0017_user_token_usage_summary"
branch_labels = None
depends_on = None

TS_DEFAULT = sa.text("CURRENT_TIMESTAMP(3)")
TS_UPDATE_DEFAULT = sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return _inspector().has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if not _has_column(table_name, column.name):
        op.add_column(table_name, column)


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    if not _has_index(table_name, index_name):
        op.create_index(index_name, table_name, columns)


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    if _has_table(table_name) and _has_index(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def _drop_column_if_exists(table_name: str, column_name: str) -> None:
    if _has_table(table_name) and _has_column(table_name, column_name):
        op.drop_column(table_name, column_name)


def _drop_table_if_exists(table_name: str) -> None:
    if _has_table(table_name):
        op.drop_table(table_name)


def upgrade() -> None:
    _add_column_if_missing("inspection_specs", sa.Column("product_family", sa.String(length=128), nullable=True))
    _add_column_if_missing("inspection_specs", sa.Column("applicable_skus", mysql.JSON, nullable=True))
    _add_column_if_missing("inspection_specs", sa.Column("required_views", mysql.JSON, nullable=True))
    _add_column_if_missing("inspection_specs", sa.Column("effective_from", mysql.DATETIME(fsp=3), nullable=True))
    _add_column_if_missing("inspection_specs", sa.Column("effective_to", mysql.DATETIME(fsp=3), nullable=True))
    _add_column_if_missing("inspection_specs", sa.Column("aggregation_rules", mysql.JSON, nullable=True))
    _add_column_if_missing("inspection_specs", sa.Column("ai_gate_rules", mysql.JSON, nullable=True))
    _add_column_if_missing("inspection_specs", sa.Column("manual_review_policies", mysql.JSON, nullable=True))

    _add_column_if_missing(
        "agent_definitions",
        sa.Column("subgraph_key", sa.String(length=64), nullable=False, server_default="quality_judgement"),
    )
    _add_column_if_missing("agent_definitions", sa.Column("entry_graph", sa.String(length=128), nullable=True))
    _add_column_if_missing(
        "agent_definitions",
        sa.Column("supports_start_stop", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )
    _add_column_if_missing(
        "agent_definitions",
        sa.Column("graph_version", sa.String(length=32), nullable=False, server_default="v1"),
    )

    if not _has_table("defect_taxonomy"):
        op.create_table(
            "defect_taxonomy",
            sa.Column("id", sa.BINARY(16), nullable=False),
            sa.Column("org_id", sa.BINARY(16), nullable=True),
            sa.Column("defect_code", sa.String(64), nullable=False),
            sa.Column("category", sa.String(64), nullable=False),
            sa.Column("name", sa.String(128), nullable=False),
            sa.Column("default_severity", sa.String(16), nullable=False, server_default="major"),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
            sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
            comment="Reusable quality defect taxonomy",
        )
    _create_index_if_missing("idx_defect_taxonomy_org_code", "defect_taxonomy", ["org_id", "defect_code"])

    if not _has_table("product_zone_maps"):
        op.create_table(
            "product_zone_maps",
            sa.Column("id", sa.BINARY(16), nullable=False),
            sa.Column("spec_row_id", sa.BINARY(16), nullable=False),
            sa.Column("zone_code", sa.String(32), nullable=False),
            sa.Column("zone_name", sa.String(128), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("is_critical", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
            sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
            comment="Product zone map per inspection spec",
        )
    _create_index_if_missing("idx_product_zone_maps_spec", "product_zone_maps", ["spec_row_id", "zone_code"])

    if not _has_table("spec_aggregation_rules"):
        op.create_table(
            "spec_aggregation_rules",
            sa.Column("id", sa.BINARY(16), nullable=False),
            sa.Column("spec_row_id", sa.BINARY(16), nullable=False),
            sa.Column("rule_code", sa.String(64), nullable=False),
            sa.Column("rule_name", sa.String(128), nullable=False),
            sa.Column("rule_payload", mysql.JSON, nullable=True),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
            sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
            comment="Spec-level aggregation rules",
        )
    _create_index_if_missing("idx_spec_aggregation_rules_spec", "spec_aggregation_rules", ["spec_row_id", "rule_code"])

    if not _has_table("spec_change_logs"):
        op.create_table(
            "spec_change_logs",
            sa.Column("id", sa.BINARY(16), nullable=False),
            sa.Column("spec_row_id", sa.BINARY(16), nullable=False),
            sa.Column("changed_by", sa.BINARY(16), nullable=True),
            sa.Column("version", sa.String(32), nullable=False),
            sa.Column("change_summary", sa.Text(), nullable=False),
            sa.Column("snapshot", mysql.JSON, nullable=True),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
            sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
            comment="Spec version change logs",
        )
    _create_index_if_missing("idx_spec_change_logs_spec", "spec_change_logs", ["spec_row_id", "version"])

    if not _has_table("inspection_result_evidence"):
        op.create_table(
            "inspection_result_evidence",
            sa.Column("id", sa.BINARY(16), nullable=False),
            sa.Column("result_id", sa.BINARY(16), nullable=False),
            sa.Column("task_id", sa.BINARY(16), nullable=False),
            sa.Column("org_id", sa.BINARY(16), nullable=False),
            sa.Column("evidence_type", sa.String(32), nullable=False),
            sa.Column("uri", sa.Text(), nullable=False),
            sa.Column("source_ref", sa.String(255), nullable=True),
            sa.Column("content", mysql.JSON, nullable=True),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
            sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
            comment="Evidence links and payloads for inspection results",
        )
    _create_index_if_missing("idx_result_evidence_result", "inspection_result_evidence", ["result_id", "evidence_type"])
    _create_index_if_missing("idx_result_evidence_task", "inspection_result_evidence", ["task_id"])

    if not _has_table("prompt_dspy_configs"):
        op.create_table(
            "prompt_dspy_configs",
            sa.Column("id", sa.BINARY(16), nullable=False),
            sa.Column("org_id", sa.BINARY(16), nullable=False),
            sa.Column("prompt_version_id", sa.BINARY(16), nullable=False),
            sa.Column("module_name", sa.String(128), nullable=False),
            sa.Column("compiler_version", sa.String(64), nullable=True),
            sa.Column("metric_names", mysql.JSON, nullable=True),
            sa.Column("config_payload", mysql.JSON, nullable=True),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("updated_by", sa.BINARY(16), nullable=True),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
            sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
            comment="Lightweight DSPy config bound to prompt versions",
        )
    _create_index_if_missing("idx_prompt_dspy_prompt", "prompt_dspy_configs", ["org_id", "prompt_version_id"])

    if not _has_table("agent_runtime_instances"):
        op.create_table(
            "agent_runtime_instances",
            sa.Column("id", sa.BINARY(16), nullable=False),
            sa.Column("org_id", sa.BINARY(16), nullable=False),
            sa.Column("agent_id", sa.BINARY(16), nullable=False),
            sa.Column("runtime_key", sa.String(128), nullable=False),
            sa.Column("subgraph_key", sa.String(64), nullable=False, server_default="quality_judgement"),
            sa.Column("status", sa.String(32), nullable=False, server_default="stopped"),
            sa.Column("supports_start_stop", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("metadata_json", mysql.JSON, nullable=True),
            sa.Column("last_started_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.Column("last_stopped_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
            sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
            comment="Agent runtime registration and status",
        )
    _create_index_if_missing("idx_agent_runtime_key", "agent_runtime_instances", ["org_id", "runtime_key"])
    _create_index_if_missing("idx_agent_runtime_agent", "agent_runtime_instances", ["org_id", "agent_id"])

    if not _has_table("rag_query_logs"):
        op.create_table(
            "rag_query_logs",
            sa.Column("id", sa.BINARY(16), nullable=False),
            sa.Column("org_id", sa.BINARY(16), nullable=False),
            sa.Column("task_id", sa.BINARY(16), nullable=True),
            sa.Column("session_id", sa.BINARY(16), nullable=True),
            sa.Column("user_id", sa.BINARY(16), nullable=True),
            sa.Column("query", sa.Text(), nullable=False),
            sa.Column("rag_space_id", sa.BINARY(16), nullable=True),
            sa.Column("hit_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("hit_rate", sa.Numeric(5, 4), nullable=False, server_default="0.0000"),
            sa.Column("citation_coverage", sa.Numeric(5, 4), nullable=False, server_default="0.0000"),
            sa.Column("latency_ms", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("source_graph", sa.String(64), nullable=False, server_default="quality_judgement"),
            sa.Column("metadata_json", mysql.JSON, nullable=True),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
            sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
            comment="RAG query traces for governance analytics",
        )
    _create_index_if_missing("idx_rag_query_logs_org_created", "rag_query_logs", ["org_id", "created_at"])
    _create_index_if_missing("idx_rag_query_logs_session", "rag_query_logs", ["session_id"])
    _create_index_if_missing("idx_rag_query_logs_rag_space", "rag_query_logs", ["rag_space_id"])


def downgrade() -> None:
    _drop_index_if_exists("idx_rag_query_logs_rag_space", "rag_query_logs")
    _drop_index_if_exists("idx_rag_query_logs_session", "rag_query_logs")
    _drop_index_if_exists("idx_rag_query_logs_org_created", "rag_query_logs")
    _drop_table_if_exists("rag_query_logs")

    _drop_index_if_exists("idx_agent_runtime_agent", "agent_runtime_instances")
    _drop_index_if_exists("idx_agent_runtime_key", "agent_runtime_instances")
    _drop_table_if_exists("agent_runtime_instances")

    _drop_index_if_exists("idx_prompt_dspy_prompt", "prompt_dspy_configs")
    _drop_table_if_exists("prompt_dspy_configs")

    _drop_index_if_exists("idx_result_evidence_task", "inspection_result_evidence")
    _drop_index_if_exists("idx_result_evidence_result", "inspection_result_evidence")
    _drop_table_if_exists("inspection_result_evidence")

    _drop_index_if_exists("idx_spec_change_logs_spec", "spec_change_logs")
    _drop_table_if_exists("spec_change_logs")

    _drop_index_if_exists("idx_spec_aggregation_rules_spec", "spec_aggregation_rules")
    _drop_table_if_exists("spec_aggregation_rules")

    _drop_index_if_exists("idx_product_zone_maps_spec", "product_zone_maps")
    _drop_table_if_exists("product_zone_maps")

    _drop_index_if_exists("idx_defect_taxonomy_org_code", "defect_taxonomy")
    _drop_table_if_exists("defect_taxonomy")

    _drop_column_if_exists("agent_definitions", "graph_version")
    _drop_column_if_exists("agent_definitions", "supports_start_stop")
    _drop_column_if_exists("agent_definitions", "entry_graph")
    _drop_column_if_exists("agent_definitions", "subgraph_key")

    _drop_column_if_exists("inspection_specs", "manual_review_policies")
    _drop_column_if_exists("inspection_specs", "ai_gate_rules")
    _drop_column_if_exists("inspection_specs", "aggregation_rules")
    _drop_column_if_exists("inspection_specs", "effective_to")
    _drop_column_if_exists("inspection_specs", "effective_from")
    _drop_column_if_exists("inspection_specs", "required_views")
    _drop_column_if_exists("inspection_specs", "applicable_skus")
    _drop_column_if_exists("inspection_specs", "product_family")
