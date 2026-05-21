"""Rule evaluation engine for alert_rules -> alert_events linking."""

from __future__ import annotations

import logging
import operator
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert_rule import AlertRule
from app.repositories.alert_rule_repo import AlertRuleRepository
from app.repositories.alert_repo import AlertRepository

logger = logging.getLogger(__name__)

_OPERATOR_MAP: dict[str, Callable[[Any, Any], bool]] = {
    "gt": operator.gt,
    "lt": operator.lt,
    "gte": operator.ge,
    "lte": operator.le,
    "eq": operator.eq,
}


class RuleEngineService:
    """Evaluates alert_rules against observed metrics and determines
    which rules should fire. Also enforces cooldown windows."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._rule_repo = AlertRuleRepository(session)
        self._alert_repo = AlertRepository(session)

    async def evaluate_and_get_matches(
        self,
        *,
        org_id: str,
        alert_type: str,
        metrics: dict[str, float],
    ) -> list[AlertRule]:
        """Return the list of enabled rules whose condition_config
        evaluates to True against `metrics`.

        `metrics` is a flat dict keyed by metric name, e.g.:
          {"risk_score_100": 82.5, "evidence_score": 0.42, ...}
        """
        candidates = await self._rule_repo.find_enabled_by_type(org_id, alert_type)
        if not candidates:
            return []

        matches: list[AlertRule] = []
        for rule in candidates:
            if self._evaluate_condition(rule.condition_config, metrics):
                matches.append(rule)
        return matches

    async def is_in_cooldown(self, rule: AlertRule, org_id: str) -> bool:
        """Return True if this rule has fired an alert within
        `rule.cooldown_seconds`."""
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=rule.cooldown_seconds)
        latest = await self._alert_repo.get_latest_by_rule(org_id, str(rule.id), cutoff)
        return latest is not None

    @classmethod
    def _evaluate_condition(
        cls, config: dict | None, metrics: dict[str, float]
    ) -> bool:
        """Evaluate a condition_config dict against the given metrics."""
        if not config:
            return True

        op_type = str(config.get("operator", "")).lower()

        if op_type in ("and", "or"):
            sub_conditions: list[dict] = config.get("conditions", [])
            if not sub_conditions:
                return True
            results = [
                cls._evaluate_single_cond(cond, metrics) for cond in sub_conditions
            ]
            return all(results) if op_type == "and" else any(results)

        return cls._evaluate_single_cond(config, metrics)

    @classmethod
    def _evaluate_single_cond(
        cls, config: dict, metrics: dict[str, float]
    ) -> bool:
        metric_name: str = str(config.get("metric", ""))
        op_str: str = str(config.get("operator", "gt")).lower()
        threshold: float = float(config.get("threshold", 0))

        observed = metrics.get(metric_name)
        if observed is None:
            return False

        op_func = _OPERATOR_MAP.get(op_str)
        if op_func is None:
            logger.warning("Unknown operator %r in condition_config", op_str)
            return False

        try:
            return op_func(float(observed), threshold)
        except (TypeError, ValueError):
            return False
