"""seed canonical demo snapshot data for admin and user orgs

Revision ID: 0021_seed_demo_snapshot
Revises: 0020_dspy_optimization
Create Date: 2026-04-05
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op


revision = "0021_seed_demo_snapshot"
down_revision = "0020_dspy_optimization"
branch_labels = None
depends_on = None

TABLE_ORDER = [
    "organizations",
    "users",
    "inspection_specs",
    "inspection_spec_items",
    "rag_spaces",
    "rag_space_files",
    "prompt_versions",
    "prompt_dspy_configs",
    "dspy_optimization_configs",
    "dspy_optimization_runs",
    "agent_definitions",
    "agent_runtime_instances",
    "intent_routes",
    "chat_sessions",
    "chat_messages",
    "inspection_tasks",
    "inspection_results",
    "stability_reports",
    "token_usage_ledger",
    "user_token_usage_summary",
    "rag_query_logs",
]
SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / "data" / "0021_seed_demo_snapshot.json"


def _load_snapshot() -> dict:
    if not SNAPSHOT_PATH.exists():
        return {}
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


def _deserialize_value(column: sa.Column, value):
    if value is None:
        return None
    column_type = column.type
    if isinstance(column_type, sa.BINARY) and getattr(column_type, "length", None) == 16 and isinstance(value, str):
        return uuid.UUID(value).bytes
    if isinstance(column_type, (mysql.DATETIME, sa.DateTime)) and isinstance(value, str):
        return datetime.fromisoformat(value)
    if isinstance(column_type, sa.Numeric) and isinstance(value, str):
        return Decimal(value)
    return value


def _prepare_rows(table: sa.Table, rows: list[dict]) -> list[dict]:
    prepared: list[dict] = []
    for row in rows:
        prepared.append(
            {
                column_name: _deserialize_value(table.c[column_name], value)
                for column_name, value in row.items()
                if column_name in table.c
            }
        )
    return prepared


def _chunks(rows: list[dict], size: int = 100):
    for index in range(0, len(rows), size):
        yield rows[index:index + size]


def _upsert_rows(bind, table_name: str, rows: list[dict]) -> None:
    if not rows:
        return
    metadata = sa.MetaData()
    table = sa.Table(table_name, metadata, autoload_with=bind)
    prepared_rows = _prepare_rows(table, rows)
    for batch in _chunks(prepared_rows):
        insert_stmt = mysql.insert(table).values(batch)
        update_values = {
            column.name: getattr(insert_stmt.inserted, column.name)
            for column in table.columns
            if not column.primary_key
        }
        bind.execute(insert_stmt.on_duplicate_key_update(**update_values))


def upgrade() -> None:
    snapshot = _load_snapshot()
    table_rows = dict(snapshot.get("tables") or {})
    table_order = list(snapshot.get("table_order") or TABLE_ORDER)
    bind = op.get_bind()
    for table_name in table_order:
        _upsert_rows(bind, table_name, table_rows.get(table_name, []))


def downgrade() -> None:
    # This migration seeds canonical demo data from a snapshot of the current database.
    # Downgrading it safely without deleting legitimate user data is not possible, so
    # downgrade intentionally leaves seeded rows in place.
    return None
