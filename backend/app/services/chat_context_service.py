from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import ROLE_USER
from app.models.result import InspectionResult
from app.models.stability import StabilityReport
from app.models.task import InspectionTask


class ChatContextService:
    """Builds lightweight inspection context for AI chat turns."""

    def __init__(self, session: AsyncSession, *, org_id: str, user_id: str, role: str):
        self._session = session
        self._org_id = org_id
        self._user_id = user_id
        self._role = role

    async def build_inspection_context(
        self,
        *,
        recent_limit: int = 6,
        summary_window: int = 12,
    ) -> dict[str, Any]:
        owner_user_id = self._owner_scope_user_id()
        stmt = (
            select(InspectionTask, InspectionResult, StabilityReport)
            .outerjoin(
                InspectionResult,
                (InspectionResult.task_id == InspectionTask.id)
                & (InspectionResult.org_id == InspectionTask.org_id),
            )
            .outerjoin(
                StabilityReport,
                (StabilityReport.task_id == InspectionTask.id)
                & (StabilityReport.org_id == InspectionTask.org_id)
                & (StabilityReport.deleted_at.is_(None)),
            )
            .where(
                InspectionTask.org_id == self._org_id,
                InspectionTask.deleted_at.is_(None),
                InspectionTask.product_id != "chat_quality",
                InspectionTask.spec_code != "CHAT-QUALITY-QA",
            )
            .order_by(InspectionTask.created_at.desc())
            .limit(max(recent_limit, summary_window))
        )
        if owner_user_id:
            stmt = stmt.where(InspectionTask.created_by == owner_user_id)

        result = await self._session.execute(stmt)
        rows = result.all()
        tasks = [self._serialize_row(task, inspection_result, stability) for task, inspection_result, stability in rows]

        if not tasks:
            return {
                "scope": "user_recent_tasks" if owner_user_id else "org_recent_tasks",
                "summary_window": 0,
                "stats": {},
                "recent_tasks": [],
                "recent_failures": [],
                "latest_task": None,
            }

        summary_items = tasks[:summary_window]
        recent_items = tasks[:recent_limit]
        return {
            "scope": "user_recent_tasks" if owner_user_id else "org_recent_tasks",
            "summary_window": len(summary_items),
            "stats": self._build_stats(summary_items),
            "recent_tasks": recent_items,
            "recent_failures": self._recent_failures(summary_items),
            "latest_task": recent_items[0] if recent_items else None,
        }

    def _owner_scope_user_id(self) -> str | None:
        if self._role == ROLE_USER:
            return self._user_id
        return None

    @staticmethod
    def _build_stats(items: list[dict[str, Any]]) -> dict[str, int]:
        status_counter: Counter[str] = Counter()
        verdict_counter: Counter[str] = Counter()
        risk_counter: Counter[str] = Counter()
        for item in items:
            status = str(item.get("status") or "").strip().lower()
            verdict = str(item.get("verdict") or "").strip().lower()
            risk_level = str(item.get("risk_level") or "").strip().lower()
            if status:
                status_counter[status] += 1
            if verdict:
                verdict_counter[verdict] += 1
            if risk_level:
                risk_counter[risk_level] += 1
        payload = {
            "total": len(items),
            **{f"status_{key}": value for key, value in status_counter.items()},
            **{f"verdict_{key}": value for key, value in verdict_counter.items()},
            **{f"risk_{key}": value for key, value in risk_counter.items()},
        }
        return payload

    @staticmethod
    def _recent_failures(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        risky = [
            item
            for item in items
            if str(item.get("verdict") or "").lower() in {"fail", "manual_required"}
            or str(item.get("status") or "").lower() in {"failed"}
            or str(item.get("risk_level") or "").lower() in {"high", "critical"}
        ]
        return risky[:3]

    @staticmethod
    def _serialize_row(
        task: InspectionTask,
        inspection_result: InspectionResult | None,
        stability: StabilityReport | None,
    ) -> dict[str, Any]:
        reasoning_chain = dict(getattr(inspection_result, "reasoning_chain", {}) or {})
        defects = dict(getattr(inspection_result, "defects", {}) or {})
        failed_rules = defects.get("failed_rules") if isinstance(defects.get("failed_rules"), list) else []
        return {
            "task_id": str(task.id),
            "product_id": str(task.product_id),
            "spec_code": str(task.spec_code),
            "status": str(task.status),
            "priority": int(task.priority or 0),
            "created_at": ChatContextService._iso(task.created_at),
            "finished_at": ChatContextService._iso(task.finished_at),
            "verdict": None if inspection_result is None else str(inspection_result.verdict),
            "overall_score": None
            if inspection_result is None
            else ChatContextService._float(inspection_result.overall_score),
            "risk_level": None if stability is None else str(stability.risk_level),
            "risk_score": None if stability is None else ChatContextService._float(stability.risk_score),
            "prompt_version": None if inspection_result is None else str(inspection_result.prompt_version),
            "model_key": None if inspection_result is None else str(inspection_result.llm_model),
            "trace_id": ChatContextService._trace_id(reasoning_chain),
            "failed_rules": [str(item) for item in failed_rules[:3]],
            "root_cause": None if stability is None else str(stability.root_cause or "") or None,
        }

    @staticmethod
    def _trace_id(reasoning_chain: dict[str, Any]) -> str | None:
        candidates = [
            reasoning_chain.get("trace_id"),
            (reasoning_chain.get("trace_meta") or {}).get("trace_id")
            if isinstance(reasoning_chain.get("trace_meta"), dict)
            else None,
            (reasoning_chain.get("llm_meta") or {}).get("langfuse", {}).get("trace_id")
            if isinstance(reasoning_chain.get("llm_meta"), dict)
            and isinstance((reasoning_chain.get("llm_meta") or {}).get("langfuse"), dict)
            else None,
        ]
        for item in candidates:
            value = str(item or "").strip()
            if value:
                return value
        return None

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        return None if value is None else value.isoformat()

    @staticmethod
    def _float(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return float(value)
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
