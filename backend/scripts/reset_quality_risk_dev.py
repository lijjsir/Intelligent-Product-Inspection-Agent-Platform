"""Reset quality-risk development data after an explicit target audit.

Usage:
    python scripts/reset_quality_risk_dev.py --confirm RESET-QUALITY-RISK
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import inspect, text

from app.core.config import settings
from infra.database.engine import create_engine_rw

FULL_TABLES = [
    "standard_execution_rules",
    "quality_public_opinion_reports",
    "quality_market_monitoring_reports",
    "physical_samples",
    "quality_risk_assessments",
    "quality_risk_cases",
    "quality_evidence_items",
    "quality_source_records",
    "quality_attachments",
    "quality_ingestion_jobs",
    "quality_data_sources",
    "enterprise_product_relations",
    "product_identifiers",
    "quality_products",
    "product_categories",
    "inspection_evidence_states",
    "inspection_decisions",
    "inspection_goals",
    "device_commands",
    "measurement_records",
    "measurement_batches",
    "business_reviews",
    "supervision_dependencies",
    "supervision_runs",
    "supervision_revisions",
    "supervision_records",
    "public_complaint_intakes",
    "product_batches",
    "product_skus",
    "product_lines",
]

TASK_CHILD_TABLES = [
    "inspection_result_evidence",
    "result_feedbacks",
    "stability_reports",
    "inspection_results",
    "task_execution_events",
    "agent_artifacts",
    "agent_task_events",
]

LEGACY_TEST_TASK_WHERE = """
product_category_id IS NULL
AND quality_product_id IS NULL
AND (
    product_sku_id IS NOT NULL
    OR batch_id IS NOT NULL
    OR spec_code LIKE 'EV-RANGE-QA-%'
)
""".strip()


async def main(confirm: str) -> None:
    if str(settings.app_env).lower() not in {"dev", "development", "test", "local"}:
        raise SystemExit("拒绝执行：PIAP_APP_ENV 不是开发或测试环境")
    engine = create_engine_rw()
    try:
        async with engine.begin() as connection:
            existing = set(await connection.run_sync(lambda sync: inspect(sync).get_table_names()))
            targets = [name for name in FULL_TABLES if name in existing]
            task_children = [name for name in TASK_CHILD_TABLES if name in existing]
            print(f"环境: {settings.app_env}")
            print(f"数据库: {engine.url.render_as_string(hide_password=True)}")
            task_count = 0
            task_child_counts: dict[str, int] = {}
            if "inspection_tasks" in existing:
                task_count = int(
                    (
                        await connection.execute(
                            text(f"SELECT COUNT(*) FROM inspection_tasks WHERE {LEGACY_TEST_TASK_WHERE}")
                        )
                    ).scalar()
                    or 0
                )
                print(f"旧产品测试任务（将连同任务域结果清理）: {task_count}")
                for table in task_children:
                    task_child_counts[table] = int(
                        (
                            await connection.execute(
                                text(
                                    f"SELECT COUNT(*) FROM `{table}` WHERE task_id IN "
                                    f"(SELECT id FROM inspection_tasks WHERE {LEGACY_TEST_TASK_WHERE})"
                                )
                            )
                        ).scalar()
                        or 0
                    )
                    print(f"  {table}: {task_child_counts[table]}")
            print("将清理以下质监与产品数据：")
            counts = {}
            for table in targets:
                counts[table] = int(
                    (await connection.execute(text(f"SELECT COUNT(*) FROM `{table}`"))).scalar() or 0
                )
                print(f"  {table}: {counts[table]}")
            if confirm != "RESET-QUALITY-RISK":
                print("仅完成审计，未修改数据库。传入 --confirm RESET-QUALITY-RISK 才会执行。")
                return
            for table in task_children:
                await connection.execute(
                    text(
                        f"DELETE FROM `{table}` WHERE task_id IN "
                        f"(SELECT id FROM inspection_tasks WHERE {LEGACY_TEST_TASK_WHERE})"
                    )
                )
            if "inspection_tasks" in existing:
                await connection.execute(
                    text(f"DELETE FROM inspection_tasks WHERE {LEGACY_TEST_TASK_WHERE}")
                )
            for table in targets:
                await connection.execute(text(f"DELETE FROM `{table}`"))
            total = task_count + sum(task_child_counts.values()) + sum(counts.values())
            print(f"已清理 {total} 条开发环境质监/产品记录。")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    asyncio.run(main(args.confirm))
