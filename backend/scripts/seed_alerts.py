"""
Seed test alert rules and alert events into the database.

Usage:
  docker compose exec backend python scripts/seed_alerts.py
  # or locally:
  python scripts/seed_alerts.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from app.models.alert_rule import AlertRule
from app.models.alert import AlertEvent

DB_URL = os.getenv(
    "PIAP_DB_URL",
    "mysql+aiomysql://piap:piap@127.0.0.1:13306/piap_main",
)


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow():
    return datetime.now(timezone.utc)


from app.services.alert_rule_service import AlertRuleService


# Re-export for backward-compatible usage in seed().
TEST_RULES = AlertRuleService.DEFAULT_ALERT_RULES


TEST_ALERTS: list[dict] = [
    # -- stability_risk alerts --
    {
        "id": new_id(),
        "alert_type": "stability_risk",
        "severity": "critical",
        "title": "任务 t-001 触发稳定性风险告警 (规则: 极高风险评分告警)",
        "detail": {"risk_level": "critical", "risk_score": 97, "message": "risk_score_100 达到 97，多维度出现严重漂移"},
        "status": "open",
        "channels": {"in_app": True, "email": True, "wecom": True},
    },
    {
        "id": new_id(),
        "alert_type": "stability_risk",
        "severity": "error",
        "title": "任务 t-002 触发稳定性风险告警 (规则: 综合稳定性异常)",
        "detail": {"risk_level": "high", "risk_score": 72, "message": "confidence=0.32 且 anomaly=0.68，模型可能发生漂移"},
        "status": "open",
        "channels": {"in_app": True, "email": True},
    },
    {
        "id": new_id(),
        "alert_type": "stability_risk",
        "severity": "warning",
        "title": "任务 t-003 触发稳定性风险告警 (规则: 证据分偏低告警)",
        "detail": {"risk_level": "medium", "risk_score": 45, "message": "evidence_score=0.22，证据链覆盖不足"},
        "status": "acknowledged",
        "channels": {"in_app": True},
    },
    {
        "id": new_id(),
        "alert_type": "stability_risk",
        "severity": "warning",
        "title": "任务 t-004 触发稳定性风险告警 (规则: 一致性/可追溯性联合检查)",
        "detail": {"risk_level": "medium", "risk_score": 52, "message": "consistency=0.41 且 traceability=0.38，自洽性和可追溯性不足"},
        "status": "suppressed",
        "channels": {"in_app": True},
    },
    {
        "id": new_id(),
        "alert_type": "stability_risk",
        "severity": "critical",
        "title": "任务 t-005 触发稳定性风险告警 (规则: 多维度严重劣化)",
        "detail": {"risk_level": "critical", "risk_score": 91, "message": "confidence=0.22, evidence=0.18, consistency=0.25 — 三个核心维度同时严重劣化"},
        "status": "open",
        "channels": {"in_app": True, "email": True, "wecom": True},
    },
    # -- quality_review alerts --
    {
        "id": new_id(),
        "alert_type": "quality_review",
        "severity": "critical",
        "title": "SPEC-01 严重幻觉告警 (规则: 严重幻觉告警)",
        "detail": {"message": "physical_hallucination_score=0.62，检测到严重物理幻觉，需立即处理", "task_id": "t-101", "result_id": "r-101"},
        "status": "open",
        "channels": {"in_app": True, "email": True, "wecom": True},
    },
    {
        "id": new_id(),
        "alert_type": "quality_review",
        "severity": "error",
        "title": "SPEC-02 忠实度下降告警 (规则: 忠实度下降告警)",
        "detail": {"message": "faithfulness_score=0.31，模型输出与源材料偏离较大", "task_id": "t-102", "result_id": "r-102"},
        "status": "open",
        "channels": {"in_app": True},
    },
    {
        "id": new_id(),
        "alert_type": "quality_review",
        "severity": "warning",
        "title": "SPEC-03 综合质量预警 (规则: 综合质量预警)",
        "detail": {"message": "risk_score=42 且 faithfulness=0.58，质量和风险同时出现预警信号", "task_id": "t-103", "result_id": "r-103"},
        "status": "acknowledged",
        "channels": {"in_app": True},
    },
    {
        "id": new_id(),
        "alert_type": "quality_review",
        "severity": "critical",
        "title": "SPEC-04 忠实度严重不足 (规则: 忠实度严重不足)",
        "detail": {"message": "faithfulness_score=0.12，模型输出与源材料严重偏离", "task_id": "t-104", "result_id": "r-104"},
        "status": "open",
        "channels": {"in_app": True, "email": True},
    },
    {
        "id": new_id(),
        "alert_type": "quality_review",
        "severity": "error",
        "title": "SPEC-05 幻觉与忠实度联合告警 (规则: 幻觉与忠实度联合告警)",
        "detail": {"message": "physical_hallucination=0.28 且 faithfulness=0.41，幻觉和忠实度同时出现问题", "task_id": "t-105", "result_id": "r-105"},
        "status": "suppressed",
        "channels": {"in_app": True},
    },
    {
        "id": new_id(),
        "alert_type": "quality_review",
        "severity": "warning",
        "title": "SPEC-06 忠实度轻微下降 (规则: 忠实度轻微下降)",
        "detail": {"message": "faithfulness_score=0.52，忠实度出现轻微下降趋势", "task_id": "t-106", "result_id": "r-106"},
        "status": "resolved",
        "channels": {"in_app": True},
    },
    {
        "id": new_id(),
        "alert_type": "stability_risk",
        "severity": "error",
        "title": "任务 t-006 触发稳定性风险告警 (规则: 异常分飙升告警)",
        "detail": {"risk_level": "high", "risk_score": 68, "message": "anomaly_score=0.82，单次检测异常分显著偏高"},
        "status": "open",
        "channels": {"in_app": True},
    },
    {
        "id": new_id(),
        "alert_type": "stability_risk",
        "severity": "info",
        "title": "任务 t-007 触发稳定性风险告警，等级 low",
        "detail": {"risk_level": "low", "risk_score": 28, "message": "各维度指标正常，仅供参考"},
        "status": "resolved",
        "channels": {"in_app": True},
    },
]


async def seed():
    engine = create_async_engine(DB_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # 1. Get all org_ids from the database
        result = await session.execute(text("SELECT id, name FROM organizations"))
        orgs = [(row[0], row[1]) for row in result.fetchall()]
        if not orgs:
            print("ERROR: No organization found. Please seed the database first.")
            await engine.dispose()
            return

        print(f"Found {len(orgs)} organization(s)")

        for org_id_raw, org_name in orgs:
            org_id = str(uuid.UUID(bytes=org_id_raw))
            print(f"\n--- Organization: {org_name} (id={org_id}) ---")

            # 2. Seed alert rules
            existing_rules = await session.execute(
                text("SELECT COUNT(id) FROM alert_rules WHERE org_id = :org_id"),
                {"org_id": org_id_raw},
            )
            count = existing_rules.scalar_one()
            print(f"  Existing alert rules: {count}")

            if count == 0:
                for rule_data in TEST_RULES:
                    rule_data_copy = dict(rule_data)
                    rule_data_copy["id"] = new_id()
                    rule_data_copy["org_id"] = org_id
                    rule = AlertRule(**rule_data_copy)
                    session.add(rule)
                    print(f"    + Created rule: {rule_data_copy['name']}")
                print(f"  Seeded {len(TEST_RULES)} alert rules.")

            # 3. Seed alert events
            existing_alerts = await session.execute(
                text("SELECT COUNT(id) FROM alert_events WHERE org_id = :org_id"),
                {"org_id": org_id_raw},
            )
            alert_count = existing_alerts.scalar_one()
            print(f"  Existing alert events: {alert_count}")

            if alert_count == 0:
                for alert_data in TEST_ALERTS:
                    alert_data_copy = dict(alert_data)
                    alert_data_copy["id"] = new_id()
                    alert_data_copy["org_id"] = org_id
                    alert_data_copy["created_at"] = utcnow()
                    alert_data_copy["updated_at"] = utcnow()
                    if alert_data_copy["status"] == "acknowledged":
                        alert_data_copy["ack_at"] = utcnow()
                    elif alert_data_copy["status"] == "suppressed":
                        alert_data_copy["suppressed_at"] = utcnow()
                        alert_data_copy["action_note"] = "测试压制"
                    elif alert_data_copy["status"] == "resolved":
                        alert_data_copy["resolved_at"] = utcnow()
                    if alert_data_copy["alert_type"] == "quality_review":
                        alert_data_copy["stability_id"] = None
                    alert = AlertEvent(**alert_data_copy)
                    session.add(alert)
                    print(f"    + Created alert: {alert_data_copy['title'][:60]}...")
                print(f"  Seeded {len(TEST_ALERTS)} alert events.")

            await session.commit()

        print("\nDone! Refresh the alert management page to see the data.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
