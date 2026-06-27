from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

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
        selected_task_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        owner_user_id = self._owner_scope_user_id()
        stmt = self._base_context_stmt(owner_user_id)
        result = await self._session.execute(
            stmt.order_by(InspectionTask.created_at.desc()).limit(max(recent_limit, summary_window))
        )
        rows = result.all()
        tasks = [self._serialize_row(task, inspection_result, stability) for task, inspection_result, stability in rows]

        selected_tasks = await self._load_selected_tasks(owner_user_id, selected_task_ids or [])

        if not tasks and not selected_tasks:
            return {
                "scope": "user_recent_tasks" if owner_user_id else "org_recent_tasks",
                "summary_window": 0,
                "stats": {},
                "quality_insights": {},
                "recent_tasks": [],
                "recent_failures": [],
                "latest_task": None,
                "selected_tasks": [],
            }

        summary_items = tasks[:summary_window]
        recent_items = tasks[:recent_limit]
        return {
            "scope": "user_recent_tasks" if owner_user_id else "org_recent_tasks",
            "summary_window": len(summary_items),
            "stats": self._build_stats(summary_items),
            "quality_insights": self._build_quality_insights([*selected_tasks, *summary_items]),
            "recent_tasks": recent_items,
            "recent_failures": self._recent_failures(summary_items),
            "latest_task": recent_items[0] if recent_items else None,
            "selected_tasks": selected_tasks,
        }

    def _base_context_stmt(self, owner_user_id: str | None):
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
        )
        if owner_user_id:
            stmt = stmt.where(InspectionTask.created_by == owner_user_id)
        return stmt

    async def _load_selected_tasks(
        self,
        owner_user_id: str | None,
        task_ids: list[str],
    ) -> list[dict[str, Any]]:
        normalized_ids = self._valid_uuid_ids(task_ids)[:8]
        if not normalized_ids:
            return []
        result = await self._session.execute(
            self._base_context_stmt(owner_user_id)
            .where(InspectionTask.id.in_(normalized_ids))
            .order_by(InspectionTask.created_at.desc())
        )
        rows = result.all()
        return [self._serialize_row(task, inspection_result, stability) for task, inspection_result, stability in rows]

    @staticmethod
    def _valid_uuid_ids(values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for item in values:
            try:
                value = str(UUID(str(item).strip()))
            except (TypeError, ValueError):
                continue
            if value not in seen:
                seen.add(value)
                result.append(value)
        return result

    def _owner_scope_user_id(self) -> str | None:
        if self._role == ROLE_USER:
            return self._user_id
        return None

    @staticmethod
    def _build_stats(items: list[dict[str, Any]]) -> dict[str, Any]:
        status_counter: Counter[str] = Counter()
        verdict_counter: Counter[str] = Counter()
        risk_counter: Counter[str] = Counter()
        scores: list[float] = []
        for item in items:
            status = str(item.get("status") or "").strip().lower()
            verdict = str(item.get("verdict") or "").strip().lower()
            risk_level = str(item.get("risk_level") or "").strip().lower()
            score = ChatContextService._float(item.get("overall_score"))
            if status:
                status_counter[status] += 1
            if verdict:
                verdict_counter[verdict] += 1
            if risk_level:
                risk_counter[risk_level] += 1
            if score is not None:
                scores.append(score)
        payload = {
            "total": len(items),
            **{f"status_{key}": value for key, value in status_counter.items()},
            **{f"verdict_{key}": value for key, value in verdict_counter.items()},
            **{f"risk_{key}": value for key, value in risk_counter.items()},
        }
        if scores:
            payload["avg_overall_score"] = round(sum(scores) / len(scores), 4)
        return payload

    @staticmethod
    def _build_quality_insights(items: list[dict[str, Any]]) -> dict[str, Any]:
        if not items:
            return {}
        failed_or_risky = [
            item
            for item in items
            if str(item.get("verdict") or "").lower() in {"fail", "failed", "manual_required", "reject"}
            or str(item.get("status") or "").lower() == "failed"
            or str(item.get("risk_level") or "").lower() in {"high", "critical"}
        ]
        product_failures: Counter[str] = Counter()
        spec_failures: Counter[str] = Counter()
        failed_rules: Counter[str] = Counter()
        defect_types: Counter[str] = Counter()
        root_causes: list[str] = []
        risk_warnings: list[str] = []
        for item in failed_or_risky:
            product_id = str(item.get("product_id") or "").strip()
            spec_code = str(item.get("spec_code") or "").strip()
            if product_id:
                product_failures[product_id] += 1
            if spec_code:
                spec_failures[spec_code] += 1
            for rule in list(item.get("failed_rules") or []):
                text = str(rule or "").strip()
                if text:
                    failed_rules[text] += 1
            for defect in list(item.get("defects") or []):
                if isinstance(defect, dict):
                    defect_type = str(defect.get("type") or defect.get("name") or "").strip()
                else:
                    defect_type = str(defect or "").strip()
                if defect_type:
                    defect_types[defect_type] += 1
            root_cause = str(item.get("root_cause") or "").strip()
            if root_cause and root_cause not in root_causes:
                root_causes.append(root_cause[:300])
        for product_id, count in product_failures.most_common(5):
            risk_warnings.append(f"product {product_id} has {count} failed or risky recent task(s)")
        for rule, count in failed_rules.most_common(5):
            risk_warnings.append(f"failed rule appears {count} time(s): {rule}")
        for defect_type, count in defect_types.most_common(5):
            risk_warnings.append(f"defect type appears {count} time(s): {defect_type}")
        return {
            "failed_or_risky_count": len(failed_or_risky),
            "product_failure_counts": dict(product_failures.most_common(8)),
            "spec_failure_counts": dict(spec_failures.most_common(8)),
            "failed_rule_counts": dict(failed_rules.most_common(10)),
            "defect_type_counts": dict(defect_types.most_common(10)),
            "root_causes": root_causes[:5],
            "risk_warnings": risk_warnings[:8],
        }

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
        raw_reasoning_chain = getattr(inspection_result, "reasoning_chain", {}) if inspection_result else {}
        raw_defects = getattr(inspection_result, "defects", {}) if inspection_result else {}
        reasoning_chain = raw_reasoning_chain if isinstance(raw_reasoning_chain, dict) else {}
        standard_eval = (
            reasoning_chain.get("standard_evaluation")
            if isinstance(reasoning_chain.get("standard_evaluation"), dict)
            else {}
        )
        defect_items = ChatContextService._defect_items(raw_defects)
        failed_rules = ChatContextService._failed_rules(raw_defects, standard_eval)
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
            "tokens_used": None if inspection_result is None else getattr(inspection_result, "tokens_used", None),
            "latency_ms": None if inspection_result is None else getattr(inspection_result, "latency_ms", None),
            "trace_id": ChatContextService._trace_id(reasoning_chain),
            "failed_rules": [str(item) for item in failed_rules[:3]],
            "root_cause": None if stability is None else str(stability.root_cause or "") or None,
            "defects": defect_items[:5],
            "defect_summary": ChatContextService._defect_summary(defect_items),
            "failure_reasons": ChatContextService._failure_reasons(standard_eval, defect_items),
            "manual_review": ChatContextService._manual_review_payload(inspection_result, standard_eval),
            "reasoning_summary": ChatContextService._reasoning_summary(reasoning_chain),
        }

    @staticmethod
    def _defect_items(raw_defects: Any) -> list[dict[str, Any]]:
        if isinstance(raw_defects, list):
            return [dict(item) for item in raw_defects if isinstance(item, dict)]
        if not isinstance(raw_defects, dict):
            return []
        for key in ("items", "defects", "detected_defects", "possible_defects"):
            value = raw_defects.get(key)
            if isinstance(value, list):
                return [dict(item) for item in value if isinstance(item, dict)]
        return []

    @staticmethod
    def _failed_rules(raw_defects: Any, standard_eval: dict[str, Any]) -> list[str]:
        candidates: list[Any] = []
        if isinstance(raw_defects, dict):
            candidates.extend(list(raw_defects.get("failed_rules") or []))
        candidates.extend(list(standard_eval.get("failed_rules") or []))
        candidates.extend(list(standard_eval.get("reasons") or []))
        return [str(item) for item in candidates if str(item or "").strip()]

    @staticmethod
    def _defect_summary(defects: list[dict[str, Any]]) -> str | None:
        parts: list[str] = []
        for item in defects[:3]:
            defect_type = str(item.get("type") or item.get("name") or "defect").strip()
            confidence = ChatContextService._float(item.get("confidence"))
            description = str(item.get("description") or item.get("summary") or "").strip()
            label = defect_type
            if confidence is not None:
                label = f"{label} {confidence * 100:.1f}%"
            if description:
                label = f"{label}: {description}"
            parts.append(label)
        return "; ".join(parts) if parts else None

    @staticmethod
    def _failure_reasons(standard_eval: dict[str, Any], defects: list[dict[str, Any]]) -> list[str]:
        reasons: list[str] = []
        summary = str(standard_eval.get("summary") or "").strip()
        if summary:
            reasons.append(summary)
        for item in list(standard_eval.get("reasons") or [])[:4]:
            text = str(item or "").strip()
            if text and text not in reasons:
                reasons.append(text)
        for defect in list(standard_eval.get("unmatched_defects") or [])[:4]:
            text = str(defect or "").strip()
            if text:
                reasons.append(f"未映射缺陷: {text}")
        for defect in defects[:3]:
            description = str(defect.get("description") or "").strip()
            if description and description not in reasons:
                reasons.append(description)
        return reasons[:8]

    @staticmethod
    def _manual_review_payload(inspection_result: InspectionResult | None, standard_eval: dict[str, Any]) -> dict[str, Any]:
        if inspection_result is None:
            return {"required": False}
        verdict = str(getattr(inspection_result, "verdict", "") or "").lower()
        required = verdict in {"manual_required", "fail", "failed"} or bool(standard_eval.get("manual_review_required"))
        return {
            "required": required,
            "reviewed": bool(getattr(inspection_result, "reviewed_at", None) or getattr(inspection_result, "reviewed_by", None)),
            "review_note": getattr(inspection_result, "review_note", None),
        }

    @staticmethod
    def _reasoning_summary(reasoning_chain: dict[str, Any]) -> str | None:
        for key in ("summary", "reasoning_summary"):
            text = str(reasoning_chain.get(key) or "").strip()
            if text:
                return text[:500]
        standard_eval = reasoning_chain.get("standard_evaluation")
        if isinstance(standard_eval, dict):
            text = str(standard_eval.get("summary") or "").strip()
            if text:
                return text[:500]
        return None

    @staticmethod
    def _trace_id(reasoning_chain: dict[str, Any]) -> str | None:
        candidates = [
            reasoning_chain.get("trace_id"),
            (reasoning_chain.get("trace") or {}).get("trace_id")
            if isinstance(reasoning_chain.get("trace"), dict)
            else None,
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
