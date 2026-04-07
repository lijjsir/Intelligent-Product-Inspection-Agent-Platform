"""add dspy optimization workbench tables

Revision ID: 0020_dspy_optimization
Revises: 0019_prompt_dspy_fallback
Create Date: 2026-04-05
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op


revision = "0020_dspy_optimization"
down_revision = "0019_prompt_dspy_fallback"
branch_labels = None
depends_on = None

TS_DEFAULT = sa.text("CURRENT_TIMESTAMP(3)")
TS_UPDATE_DEFAULT = sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return _inspector().has_table(table_name)


def _has_index(table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    if not _has_index(table_name, index_name):
        op.create_index(index_name, table_name, columns)


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    if _has_table(table_name) and _has_index(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def _drop_table_if_exists(table_name: str) -> None:
    if _has_table(table_name):
        op.drop_table(table_name)


def upgrade() -> None:
    if not _has_table("dspy_optimization_configs"):
        op.create_table(
            "dspy_optimization_configs",
            sa.Column("id", sa.BINARY(16), nullable=False),
            sa.Column("org_id", sa.BINARY(16), nullable=False),
            sa.Column("target_key", sa.String(160), nullable=False),
            sa.Column("subgraph_key", sa.String(64), nullable=False),
            sa.Column("node_id", sa.String(128), nullable=False),
            sa.Column("node_label", sa.String(128), nullable=False),
            sa.Column("module_name", sa.String(128), nullable=False),
            sa.Column("optimization_goal", sa.Text(), nullable=False),
            sa.Column("optimizer_strategy", sa.String(64), nullable=False, server_default="bootstrap-fewshot"),
            sa.Column("compiler_version", sa.String(64), nullable=True),
            sa.Column("metric_names", mysql.JSON, nullable=True),
            sa.Column("config_payload", mysql.JSON, nullable=True),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("is_active_target", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("supports_compile", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("current_artifact_version", sa.String(64), nullable=True),
            sa.Column("current_prompt_version_id", sa.BINARY(16), nullable=True),
            sa.Column("previous_artifact_version", sa.String(64), nullable=True),
            sa.Column("previous_prompt_version_id", sa.BINARY(16), nullable=True),
            sa.Column("latest_failed_artifact_version", sa.String(64), nullable=True),
            sa.Column("latest_error_message", sa.Text(), nullable=True),
            sa.Column("latest_metrics_snapshot", mysql.JSON, nullable=True),
            sa.Column("last_compiled_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.Column("last_evaluated_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.Column("updated_by", sa.BINARY(16), nullable=True),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
            sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
            comment="DSPy optimization config per discovered graph target",
        )
    _create_index_if_missing("idx_dspy_opt_target", "dspy_optimization_configs", ["org_id", "target_key"])
    _create_index_if_missing("idx_dspy_opt_subgraph", "dspy_optimization_configs", ["org_id", "subgraph_key"])

    if not _has_table("dspy_optimization_runs"):
        op.create_table(
            "dspy_optimization_runs",
            sa.Column("id", sa.BINARY(16), nullable=False),
            sa.Column("org_id", sa.BINARY(16), nullable=False),
            sa.Column("target_key", sa.String(160), nullable=False),
            sa.Column("run_type", sa.String(32), nullable=False, server_default="compile"),
            sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
            sa.Column("compiler_version", sa.String(64), nullable=True),
            sa.Column("artifact_version", sa.String(64), nullable=True),
            sa.Column("prompt_version_id", sa.BINARY(16), nullable=True),
            sa.Column("metrics_snapshot", mysql.JSON, nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("payload_json", mysql.JSON, nullable=True),
            sa.Column("started_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.Column("finished_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_DEFAULT),
            sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False, server_default=TS_UPDATE_DEFAULT),
            sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
            comment="Async compile/eval runs for DSPy optimization targets",
        )
    _create_index_if_missing("idx_dspy_run_target", "dspy_optimization_runs", ["org_id", "target_key"])
    _create_index_if_missing("idx_dspy_run_status", "dspy_optimization_runs", ["org_id", "status"])


def downgrade() -> None:
    _drop_index_if_exists("idx_dspy_run_status", "dspy_optimization_runs")
    _drop_index_if_exists("idx_dspy_run_target", "dspy_optimization_runs")
    _drop_table_if_exists("dspy_optimization_runs")

    _drop_index_if_exists("idx_dspy_opt_subgraph", "dspy_optimization_configs")
    _drop_index_if_exists("idx_dspy_opt_target", "dspy_optimization_configs")
    _drop_table_if_exists("dspy_optimization_configs")
