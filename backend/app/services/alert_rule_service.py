from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.repositories.alert_rule_repo import AlertRuleRepository


# Canonical default alert rules, shared by org-init and seed script.
DEFAULT_ALERT_RULES: list[dict[str, Any]] = [
    # =========================================================================
    # stability_risk
    # =========================================================================
    {
        "name": "极高风险评分告警",
        "description": "risk_score_100 ≥ 95，模型输出存在严重稳定性风险，需立即介入",
        "alert_type": "stability_risk",
        "severity": "critical",
        "enabled": True,
        "condition_config": {"metric": "risk_score_100", "operator": "gte", "threshold": 95},
        "notification_channels": {"in_app": True, "email": True, "wecom": True},
        "cooldown_seconds": 300,
    },
    {
        "name": "高风险评分告警",
        "description": "risk_score_100 ≥ 80，稳定性风险较高，需关注处理",
        "alert_type": "stability_risk",
        "severity": "critical",
        "enabled": True,
        "condition_config": {"metric": "risk_score_100", "operator": "gte", "threshold": 80},
        "notification_channels": {"in_app": True, "email": True},
        "cooldown_seconds": 600,
    },
    {
        "name": "多维度严重劣化",
        "description": "confidence<0.3 且 evidence<0.3 且 consistency<0.3，三个核心维度同时严重劣化",
        "alert_type": "stability_risk",
        "severity": "critical",
        "enabled": True,
        "condition_config": {
            "operator": "and",
            "conditions": [
                {"metric": "confidence_score", "operator": "lt", "threshold": 0.3},
                {"metric": "evidence_score", "operator": "lt", "threshold": 0.3},
                {"metric": "consistency_score", "operator": "lt", "threshold": 0.3},
            ],
        },
        "notification_channels": {"in_app": True, "email": True, "wecom": True},
        "cooldown_seconds": 600,
    },
    {
        "name": "综合稳定性异常",
        "description": "置信度不足且异常分偏高（confidence<0.4 且 anomaly>0.5），模型可能发生漂移",
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
        "notification_channels": {"in_app": True, "email": True},
        "cooldown_seconds": 900,
    },
    {
        "name": "证据与置信度双低",
        "description": "evidence<0.4 且 confidence<0.4，证据链和模型置信度同时不足",
        "alert_type": "stability_risk",
        "severity": "error",
        "enabled": True,
        "condition_config": {
            "operator": "and",
            "conditions": [
                {"metric": "evidence_score", "operator": "lt", "threshold": 0.4},
                {"metric": "confidence_score", "operator": "lt", "threshold": 0.4},
            ],
        },
        "notification_channels": {"in_app": True},
        "cooldown_seconds": 900,
    },
    {
        "name": "异常分飙升告警",
        "description": "anomaly_score > 0.7，单次检测异常分显著偏高",
        "alert_type": "stability_risk",
        "severity": "error",
        "enabled": True,
        "condition_config": {"metric": "anomaly_score", "operator": "gt", "threshold": 0.7},
        "notification_channels": {"in_app": True},
        "cooldown_seconds": 600,
    },
    {
        "name": "证据分偏低告警",
        "description": "evidence_score < 0.3，证据链覆盖不足，需关注",
        "alert_type": "stability_risk",
        "severity": "warning",
        "enabled": True,
        "condition_config": {"metric": "evidence_score", "operator": "lt", "threshold": 0.3},
        "notification_channels": {"in_app": True},
        "cooldown_seconds": 1200,
    },
    {
        "name": "置信度偏低告警",
        "description": "confidence_score < 0.5，模型对输出结果信心不足",
        "alert_type": "stability_risk",
        "severity": "warning",
        "enabled": True,
        "condition_config": {"metric": "confidence_score", "operator": "lt", "threshold": 0.5},
        "notification_channels": {"in_app": True},
        "cooldown_seconds": 1800,
    },
    {
        "name": "一致性/可追溯性联合检查",
        "description": "consistency<0.5 或 traceability<0.5，答案自洽性或来源可追溯性不足",
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
    {
        "name": "可追溯性不足告警",
        "description": "traceability_score < 0.4，答案来源难以追溯，可能影响审计合规",
        "alert_type": "stability_risk",
        "severity": "warning",
        "enabled": True,
        "condition_config": {"metric": "traceability_score", "operator": "lt", "threshold": 0.4},
        "notification_channels": {"in_app": True},
        "cooldown_seconds": 1800,
    },
    # =========================================================================
    # quality_review
    # =========================================================================
    {
        "name": "严重幻觉告警",
        "description": "physical_hallucination_score > 0.5，检测到严重物理幻觉，需立即处理",
        "alert_type": "quality_review",
        "severity": "critical",
        "enabled": True,
        "condition_config": {"metric": "physical_hallucination_score", "operator": "gt", "threshold": 0.5},
        "notification_channels": {"in_app": True, "email": True, "wecom": True},
        "cooldown_seconds": 300,
    },
    {
        "name": "幻觉分过高告警",
        "description": "physical_hallucination_score > 0.3，检测到明显幻觉内容",
        "alert_type": "quality_review",
        "severity": "critical",
        "enabled": True,
        "condition_config": {"metric": "physical_hallucination_score", "operator": "gt", "threshold": 0.3},
        "notification_channels": {"in_app": True, "email": True},
        "cooldown_seconds": 300,
    },
    {
        "name": "忠实度严重不足",
        "description": "faithfulness_score < 0.2，模型输出与源材料严重偏离",
        "alert_type": "quality_review",
        "severity": "critical",
        "enabled": True,
        "condition_config": {"metric": "faithfulness_score", "operator": "lt", "threshold": 0.2},
        "notification_channels": {"in_app": True, "email": True},
        "cooldown_seconds": 600,
    },
    {
        "name": "忠实度下降告警",
        "description": "faithfulness_score < 0.4，模型输出忠实度不足",
        "alert_type": "quality_review",
        "severity": "error",
        "enabled": True,
        "condition_config": {"metric": "faithfulness_score", "operator": "lt", "threshold": 0.4},
        "notification_channels": {"in_app": True},
        "cooldown_seconds": 600,
    },
    {
        "name": "幻觉与忠实度联合告警",
        "description": "physical_hallucination>0.2 且 faithfulness<0.5，幻觉和忠实度同时出现问题",
        "alert_type": "quality_review",
        "severity": "error",
        "enabled": True,
        "condition_config": {
            "operator": "and",
            "conditions": [
                {"metric": "physical_hallucination_score", "operator": "gt", "threshold": 0.2},
                {"metric": "faithfulness_score", "operator": "lt", "threshold": 0.5},
            ],
        },
        "notification_channels": {"in_app": True},
        "cooldown_seconds": 900,
    },
    {
        "name": "证据覆盖度严重不足",
        "description": "evidence_score < 0.2，质检证据覆盖度极低，审查结论缺乏支撑",
        "alert_type": "quality_review",
        "severity": "error",
        "enabled": True,
        "condition_config": {"metric": "evidence_score", "operator": "lt", "threshold": 0.2},
        "notification_channels": {"in_app": True},
        "cooldown_seconds": 900,
    },
    {
        "name": "质检风险评分告警",
        "description": "risk_score > 50，质检综合风险评分偏高",
        "alert_type": "quality_review",
        "severity": "warning",
        "enabled": True,
        "condition_config": {"metric": "risk_score", "operator": "gt", "threshold": 50},
        "notification_channels": {"in_app": True},
        "cooldown_seconds": 1200,
    },
    {
        "name": "忠实度轻微下降",
        "description": "faithfulness_score < 0.6，忠实度出现轻微下降趋势，提前预警",
        "alert_type": "quality_review",
        "severity": "warning",
        "enabled": True,
        "condition_config": {"metric": "faithfulness_score", "operator": "lt", "threshold": 0.6},
        "notification_channels": {"in_app": True},
        "cooldown_seconds": 1800,
    },
    {
        "name": "幻觉轻微检测告警",
        "description": "physical_hallucination_score > 0.1，检测到轻微幻觉迹象，需持续关注",
        "alert_type": "quality_review",
        "severity": "warning",
        "enabled": True,
        "condition_config": {"metric": "physical_hallucination_score", "operator": "gt", "threshold": 0.1},
        "notification_channels": {"in_app": True},
        "cooldown_seconds": 1800,
    },
    {
        "name": "综合质量预警",
        "description": "risk_score>30 且 faithfulness<0.7，质量和风险同时出现预警信号",
        "alert_type": "quality_review",
        "severity": "warning",
        "enabled": True,
        "condition_config": {
            "operator": "and",
            "conditions": [
                {"metric": "risk_score", "operator": "gt", "threshold": 30},
                {"metric": "faithfulness_score", "operator": "lt", "threshold": 0.7},
            ],
        },
        "notification_channels": {"in_app": True},
        "cooldown_seconds": 1800,
    },
    {
        "name": "一致性评分偏低（按需启用）",
        "description": "consistency_score < 0.3，答案自洽性严重不足，通常伴随其他问题出现，默认关闭避免重复告警",
        "alert_type": "stability_risk",
        "severity": "warning",
        "enabled": False,
        "condition_config": {"metric": "consistency_score", "operator": "lt", "threshold": 0.3},
        "notification_channels": {"in_app": True},
        "cooldown_seconds": 600,
    },
]


class AlertRuleService:
    def __init__(self, session: AsyncSession, org_id: str | None):
        self._session = session
        self._org_id = org_id
        self._repo = AlertRuleRepository(session)

    async def get(self, rule_id: str):
        return await self._repo.get(self._org_id, rule_id)

    async def list_rules(self, skip: int = 0, limit: int = 20, severity: str | None = None, enabled: bool | None = None):
        return await self._repo.list_rules(self._org_id, skip, limit, severity, enabled)

    async def create_rule(self, payload: dict) -> dict:
        payload = dict(payload)
        payload.setdefault("id", str(uuid.uuid4()))
        rule = await self._repo.create(payload)
        await self._session.commit()
        return rule

    async def update_rule(self, rule_id: str, payload: dict):
        existing = await self._repo.get(self._org_id, rule_id)
        if not existing:
            raise NotFoundError("Alert rule not found")
        payload.pop("org_id", None)
        await self._repo.update(self._org_id, rule_id, payload)
        await self._session.commit()
        return await self._repo.get(self._org_id, rule_id)

    async def delete_rule(self, rule_id: str):
        existing = await self._repo.get(self._org_id, rule_id)
        if not existing:
            raise NotFoundError("Alert rule not found")
        from app.repositories.alert_repo import AlertRepository
        alert_repo = AlertRepository(self._session)
        await alert_repo.nullify_rule_id(self._org_id, rule_id)
        deleted = await self._repo.delete(self._org_id, rule_id)
        await self._session.commit()
        return deleted

    @classmethod
    async def seed_default_rules(cls, session: AsyncSession, org_id: str) -> int:
        """Create default alert rules for a newly created organization.

        Returns the number of rules created.
        """
        repo = AlertRuleRepository(session)
        created = 0
        for template in DEFAULT_ALERT_RULES:
            payload = dict(template)
            payload["id"] = str(uuid.uuid4())
            payload["org_id"] = org_id
            await repo.create(payload)
            created += 1
        await session.commit()
        return created
