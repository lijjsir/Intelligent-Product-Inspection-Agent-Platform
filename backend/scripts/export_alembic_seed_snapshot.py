from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import sqlalchemy as sa

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from infra.database.session import create_session


CANONICAL_ORG_SLUGS = ("admin", "user")
DEMO_TABLE_ORDER = [
    "organizations",
    "users",
    "inspection_specs",
    "inspection_spec_items",
    "rag_spaces",
    "rag_nodes",
    "rag_documents",
    "prompt_versions",
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
FULL_TABLE_ORDER = [
    "organizations",
    "users",
    "model_configs",
    "inspection_specs",
    "inspection_spec_items",
    "defect_taxonomy",
    "product_zone_maps",
    "spec_aggregation_rules",
    "spec_change_logs",
    "rag_spaces",
    "rag_nodes",
    "rag_documents",
    "prompt_versions",
    "agent_definitions",
    "agent_runtime_instances",
    "agent_execution_metrics",
    "agent_config_versions",
    "intent_routes",
    "tool_registry",
    "tool_executions",
    "chat_sessions",
    "chat_messages",
    "inspection_tasks",
    "inspection_results",
    "inspection_result_evidence",
    "stability_reports",
    "alert_events",
    "result_feedbacks",
    "token_usage_ledger",
    "user_token_usage_summary",
    "rag_query_logs",
    "audit_outbox",
]
OUTPUT_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "data"
    / "0021_seed_demo_snapshot.json"
)


def _serialize_value(value: Any) -> Any:
    if isinstance(value, bytes) and len(value) == 16:
        try:
            return str(uuid.UUID(bytes=value))
        except ValueError:
            return value.hex()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _serialize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    return value


def _serialize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: _serialize_value(value) for key, value in row.items()} for row in rows]


async def _reflect_tables(session, table_names: list[str]) -> dict[str, sa.Table]:
    conn = await session.connection()
    metadata = sa.MetaData()

    def _reflect(sync_conn):
        metadata.reflect(bind=sync_conn, only=table_names)

    await conn.run_sync(_reflect)
    return {name: metadata.tables[name] for name in table_names}


async def _fetch_rows(session, table: sa.Table, filters: list[Any]) -> list[dict[str, Any]]:
    stmt = sa.select(table)
    if filters:
        stmt = stmt.where(*filters)
    result = await session.execute(stmt)
    return [dict(row) for row in result.mappings().all()]


def _active_filters(table: sa.Table) -> list[Any]:
    if "deleted_at" in table.c:
        return [table.c.deleted_at.is_(None)]
    return []


async def _export_demo_snapshot(session, tables: dict[str, sa.Table]) -> dict[str, list[dict[str, Any]]]:
    data: dict[str, list[dict[str, Any]]] = {}

    organizations = await _fetch_rows(
        session,
        tables["organizations"],
        _active_filters(tables["organizations"]) + [tables["organizations"].c.slug.in_(CANONICAL_ORG_SLUGS)],
    )
    data["organizations"] = _serialize_rows(organizations)
    org_ids = {row["id"] for row in organizations}

    users = await _fetch_rows(
        session,
        tables["users"],
        _active_filters(tables["users"]) + [tables["users"].c.org_id.in_(org_ids)],
    )
    data["users"] = _serialize_rows(users)
    user_ids = {row["id"] for row in users}

    inspection_specs = await _fetch_rows(
        session,
        tables["inspection_specs"],
        _active_filters(tables["inspection_specs"]) + [
            sa.or_(
                tables["inspection_specs"].c.org_id.is_(None),
                tables["inspection_specs"].c.org_id.in_(org_ids),
            )
        ],
    )
    data["inspection_specs"] = _serialize_rows(inspection_specs)
    spec_ids = {row["id"] for row in inspection_specs}

    inspection_spec_items = await _fetch_rows(
        session,
        tables["inspection_spec_items"],
        _active_filters(tables["inspection_spec_items"]) + [tables["inspection_spec_items"].c.spec_row_id.in_(spec_ids)],
    )
    data["inspection_spec_items"] = _serialize_rows(inspection_spec_items)

    rag_spaces = await _fetch_rows(
        session,
        tables["rag_spaces"],
        _active_filters(tables["rag_spaces"]) + [tables["rag_spaces"].c.org_id.in_(org_ids)],
    )
    data["rag_spaces"] = _serialize_rows(rag_spaces)
    rag_space_ids = {row["id"] for row in rag_spaces}

    rag_nodes = await _fetch_rows(
        session,
        tables["rag_nodes"],
        _active_filters(tables["rag_nodes"]) + [tables["rag_nodes"].c.rag_space_id.in_(rag_space_ids)],
    )
    data["rag_nodes"] = _serialize_rows(rag_nodes)

    rag_documents = await _fetch_rows(
        session,
        tables["rag_documents"],
        _active_filters(tables["rag_documents"]) + [tables["rag_documents"].c.rag_space_id.in_(rag_space_ids)],
    )
    data["rag_documents"] = _serialize_rows(rag_documents)

    prompt_versions = await _fetch_rows(
        session,
        tables["prompt_versions"],
        _active_filters(tables["prompt_versions"]) + [tables["prompt_versions"].c.org_id.in_(org_ids)],
    )
    data["prompt_versions"] = _serialize_rows(prompt_versions)

    agent_definitions = await _fetch_rows(
        session,
        tables["agent_definitions"],
        _active_filters(tables["agent_definitions"]) + [tables["agent_definitions"].c.org_id.in_(org_ids)],
    )
    data["agent_definitions"] = _serialize_rows(agent_definitions)
    agent_ids = {row["id"] for row in agent_definitions}

    agent_runtime_instances = await _fetch_rows(
        session,
        tables["agent_runtime_instances"],
        _active_filters(tables["agent_runtime_instances"]) + [tables["agent_runtime_instances"].c.agent_id.in_(agent_ids)],
    )
    data["agent_runtime_instances"] = _serialize_rows(agent_runtime_instances)

    intent_routes = await _fetch_rows(
        session,
        tables["intent_routes"],
        _active_filters(tables["intent_routes"]) + [tables["intent_routes"].c.org_id.in_(org_ids)],
    )
    data["intent_routes"] = _serialize_rows(intent_routes)

    chat_sessions = await _fetch_rows(
        session,
        tables["chat_sessions"],
        _active_filters(tables["chat_sessions"]) + [tables["chat_sessions"].c.org_id.in_(org_ids)],
    )
    data["chat_sessions"] = _serialize_rows(chat_sessions)
    session_ids = {row["id"] for row in chat_sessions}

    chat_messages = await _fetch_rows(
        session,
        tables["chat_messages"],
        _active_filters(tables["chat_messages"]) + [tables["chat_messages"].c.session_id.in_(session_ids)],
    )
    data["chat_messages"] = _serialize_rows(chat_messages)

    inspection_tasks = await _fetch_rows(
        session,
        tables["inspection_tasks"],
        _active_filters(tables["inspection_tasks"]) + [tables["inspection_tasks"].c.org_id.in_(org_ids)],
    )
    data["inspection_tasks"] = _serialize_rows(inspection_tasks)
    task_ids = {row["id"] for row in inspection_tasks}

    inspection_results = await _fetch_rows(
        session,
        tables["inspection_results"],
        _active_filters(tables["inspection_results"]) + [tables["inspection_results"].c.task_id.in_(task_ids)],
    )
    data["inspection_results"] = _serialize_rows(inspection_results)
    result_ids = {row["id"] for row in inspection_results}

    stability_reports = await _fetch_rows(
        session,
        tables["stability_reports"],
        [tables["stability_reports"].c.task_id.in_(task_ids)],
    )
    data["stability_reports"] = _serialize_rows(stability_reports)

    token_usage_ledger = await _fetch_rows(
        session,
        tables["token_usage_ledger"],
        [
            tables["token_usage_ledger"].c.org_id.in_(org_ids),
            sa.or_(
                tables["token_usage_ledger"].c.task_id.is_(None),
                tables["token_usage_ledger"].c.task_id.in_(task_ids),
            ),
            sa.or_(
                tables["token_usage_ledger"].c.result_id.is_(None),
                tables["token_usage_ledger"].c.result_id.in_(result_ids),
            ),
            sa.or_(
                tables["token_usage_ledger"].c.user_id.is_(None),
                tables["token_usage_ledger"].c.user_id.in_(user_ids),
            ),
        ],
    )
    data["token_usage_ledger"] = _serialize_rows(token_usage_ledger)

    user_token_usage_summary = await _fetch_rows(
        session,
        tables["user_token_usage_summary"],
        [tables["user_token_usage_summary"].c.user_id.in_(user_ids)],
    )
    data["user_token_usage_summary"] = _serialize_rows(user_token_usage_summary)

    rag_query_logs = await _fetch_rows(
        session,
        tables["rag_query_logs"],
        _active_filters(tables["rag_query_logs"]) + [tables["rag_query_logs"].c.org_id.in_(org_ids)],
    )
    data["rag_query_logs"] = _serialize_rows(rag_query_logs)

    return data


async def _export_full_snapshot(session, tables: dict[str, sa.Table]) -> dict[str, list[dict[str, Any]]]:
    data: dict[str, list[dict[str, Any]]] = {}
    for table_name in FULL_TABLE_ORDER:
        rows = await _fetch_rows(session, tables[table_name], [])
        data[table_name] = _serialize_rows(rows)
    return data


async def main(mode: str) -> None:
    session = create_session()
    try:
        table_order = FULL_TABLE_ORDER if mode == "full" else DEMO_TABLE_ORDER
        tables = await _reflect_tables(session, table_order)
        data = (
            await _export_full_snapshot(session, tables)
            if mode == "full"
            else await _export_demo_snapshot(session, tables)
        )

        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(
            json.dumps(
                {
                    "snapshot_scope": "full_database" if mode == "full" else "canonical_demo",
                    "table_order": table_order,
                    "tables": data,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"Wrote snapshot to {OUTPUT_PATH}")
        for table_name in table_order:
            print(f"{table_name}: {len(data.get(table_name, []))}")
    finally:
        await session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export current DB snapshot for Alembic seed migration")
    parser.add_argument("--mode", choices=["demo", "full"], default="demo")
    args = parser.parse_args()
    asyncio.run(main(args.mode))
