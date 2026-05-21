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


TEST_RULES = [
    # -- stability_risk rules (match inspection_pipeline_service metrics) --
    {
        "id": new_id(),
        "name": "风险评分 ≥ 80 严重告警",
        "description": "risk_score_100 达到 80 以上时触发 critical 告警",
        "alert_type": "stability_risk",
        "severity": "critical",
        "enabled": True,
        "condition_config": {"metric": "risk_score_100", "operator": "gte", "threshold": 80},
        "notification_channels": {"in_app": True},
        "cooldown_seconds": 600,
    },
    {
        "id": new_id(),
        "name": "证据分过低告警",
        "description": "evidence_score 低于 0.3 时触发，说明证据链不足",
        "alert_type": "stability_risk",
        "severity": "warning",
        "enabled": True,
        "condition_config": {"metric": "evidence_score", "operator": "lt", "threshold": 0.3},
        "notification_channels": {"in_app": True},
        "cooldown_seconds": 1200,
    },
    {
        "id": new_id(),
        "name": "综合稳定性异常",
        "description": "confidence<0.4 且 anomaly>0.5 时触发",
        "alert_type": "stability_risk",
        "severity": "error",
        "enabled": True,
        "condition_config": {
            "operator": "and",
            "conditions": [
                {"metric": "confidence_score", "operator": "lt", "threshold": 0.4},
                {"metric": "anomaly_score", "operator": "gt", "threshold": 0.5},
            ],
        },
        "notification_channels": {"in_app": True},
        "cooldown_seconds": 900,
    },
    {
        "id": new_id(),
        "name": "一致性/可追溯性联合检查",
        "description": "consistency<0.5 或 traceability<0.5 时触发",
        "alert_type": "stability_risk",
        "severity": "warning",
        "enabled": True,
        "condition_config": {
            "operator": "or",
            "conditions": [
                {"metric": "consistency_score", "operator": "lt", "threshold": 0.5},
                {"metric": "traceability_score", "operator": "lt", "threshold": 0.5},
            ],
        },
        "notification_channels": {"in_app": True},
        "cooldown_seconds": 1800,
    },
    # -- quality_review rules (match quality_agent_orchestrator_service metrics) --
    {
        "id": new_id(),
        "name": "幻觉分过高告警",
        "description": "physical_hallucination_score > 0.3 时触发 critical",
        "alert_type": "quality_review",
        "severity": "critical",
        "enabled": True,
        "condition_config": {"metric": "physical_hallucination_score", "operator": "gt", "threshold": 0.3},
        "notification_channels": {"in_app": True},
        "cooldown_seconds": 300,
    },
    {
        "id": new_id(),
        "name": "忠实度下降告警",
        "description": "faithfulness_score 低于 0.4 时触发",
        "alert_type": "quality_review",
        "severity": "error",
        "enabled": True,
        "condition_config": {"metric": "faithfulness_score", "operator": "lt", "threshold": 0.4},
        "notification_channels": {"in_app": True},
        "cooldown_seconds": 600,
    },
    {
        "id": new_id(),
        "name": "质检风险评分告警",
        "description": "risk_score > 50 时触发质检告警",
        "alert_type": "quality_review",
        "severity": "warning",
        "enabled": True,
        "condition_config": {"metric": "risk_score", "operator": "gt", "threshold": 50},
        "notification_channels": {"in_app": True},
        "cooldown_seconds": 1200,
    },
    {
        "id": new_id(),
        "name": "证据覆盖度不足（已停用）",
        "description": "evidence_score < 0.2，已停用",
        "alert_type": "quality_review",
        "severity": "warning",
        "enabled": False,
        "condition_config": {"metric": "evidence_score", "operator": "lt", "threshold": 0.2},
        "notification_channels": {"in_app": True},
        "cooldown_seconds": 600,
    },
]


TEST_ALERTS = [
    {
        "id": new_id(),
        "alert_type": "stability_risk",
        "severity": "critical",
        "title": "任务 t-001 触发稳定性风险告警，等级 critical",
        "detail": {"risk_level": "critical", "risk_score": 92, "message": "evidence_score 低于阈值，多个维度出现漂移"},
        "status": "open",
        "channels": {"in_app": True},
    },
    {
        "id": new_id(),
        "alert_type": "quality_review",
        "severity": "error",
        "title": "SPEC-01 质检审核需要关注",
        "detail": {"message": "质检评分低于标准，存在事实性错误", "task_id": "t-002", "result_id": "r-002"},
        "status": "open",
        "channels": {"ui": True},
    },
    {
        "id": new_id(),
        "alert_type": "stability_risk",
        "severity": "warning",
        "title": "任务 t-003 触发稳定性风险告警，等级 high",
        "detail": {"risk_level": "high", "risk_score": 68, "message": "consistency_score 偏低"},
        "status": "acknowledged",
        "channels": {"in_app": True},
    },
    {
        "id": new_id(),
        "alert_type": "quality_review",
        "severity": "warning",
        "title": "SPEC-03 质检审核需要人工确认",
        "detail": {"message": "答案完整性不足，建议人工复核", "task_id": "t-004", "result_id": "r-004"},
        "status": "suppressed",
        "channels": {"ui": True},
    },
    {
        "id": new_id(),
        "alert_type": "stability_risk",
        "severity": "info",
        "title": "任务 t-005 触发稳定性风险告警，等级 medium",
        "detail": {"risk_level": "medium", "risk_score": 45, "message": "traceability_score 轻微下降"},
        "status": "resolved",
        "channels": {"in_app": True},
    },
    {
        "id": new_id(),
        "alert_type": "quality_review",
        "severity": "critical",
        "title": "SPEC-02 严重质检问题 - 幻觉检测",
        "detail": {"message": "检测到物理幻觉，需要立即处理", "task_id": "t-006", "result_id": "r-006"},
        "status": "open",
        "channels": {"ui": True},
    },
    {
        "id": new_id(),
        "alert_type": "stability_risk",
        "severity": "error",
        "title": "任务 t-007 批量漂移告警",
        "detail": {"risk_level": "critical", "risk_score": 95, "message": "批量采样中多个答案出现证据不一致"},
        "status": "open",
        "channels": {"in_app": True},
    },
    {
        "id": new_id(),
        "alert_type": "quality_review",
        "severity": "warning",
        "title": "SPEC-04 RAG 引用质量下降",
        "detail": {"message": "检索文档相关性下降超过 20%", "task_id": "t-008", "result_id": "r-008"},
        "status": "acknowledged",
        "channels": {"ui": True},
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
