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

TABLES = [
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


async def main(confirm: str) -> None:
    if str(settings.app_env).lower() not in {"dev", "development", "test", "local"}:
        raise SystemExit("拒绝执行：PIAP_APP_ENV 不是开发或测试环境")
    engine = create_engine_rw()
    try:
        async with engine.begin() as connection:
            existing = set(await connection.run_sync(lambda sync: inspect(sync).get_table_names()))
            targets = [name for name in TABLES if name in existing]
            print(f"环境: {settings.app_env}")
            print(f"数据库: {engine.url.render_as_string(hide_password=True)}")
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
            for table in targets:
                await connection.execute(text(f"DELETE FROM `{table}`"))
            print(f"已清理 {sum(counts.values())} 条开发环境质监/产品记录。")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    asyncio.run(main(args.confirm))
