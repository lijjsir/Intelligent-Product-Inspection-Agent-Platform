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
        raw_reasoning_chain = getattr(inspection_result, "reasoning_chain", {}) if inspection_result else {}
        raw_defects = getattr(inspection_result, "defects", []) if inspection_result else []
        reasoning_chain = raw_reasoning_chain if isinstance(raw_reasoning_chain, dict) else {}
        defects = ChatContextService._defect_items(raw_defects)
        failed_rules = ChatContextService._failed_rules(raw_defects, reasoning_chain)
        failure_reasons = ChatContextService._failure_reasons(reasoning_chain, defects, stability)
        verdict = None if inspection_result is None else str(inspection_result.verdict)
        return {
            "task_id": str(task.id),
            "product_id": str(task.product_id),
            "spec_code": str(task.spec_code),
            "status": str(task.status),
            "priority": int(task.priority or 0),
            "created_at": ChatContextService._iso(task.created_at),
            "finished_at": ChatContextService._iso(task.finished_at),
            "verdict": verdict,
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
            "defects": defects,
            "defect_summary": ChatContextService._defect_summary(defects),
            "failure_reasons": failure_reasons,
            "reasoning_summary": ChatContextService._reasoning_summary(reasoning_chain, failure_reasons),
            "manual_review": ChatContextService._manual_review_payload(inspection_result, verdict),
        }

    @staticmethod
    def _defect_items(raw_defects: Any, *, limit: int = 5) -> list[dict[str, Any]]:
        if isinstance(raw_defects, list):
            candidates = raw_defects
        elif isinstance(raw_defects, dict):
            nested = raw_defects.get("defects") or raw_defects.get("items") or raw_defects.get("detections")
            candidates = nested if isinstance(nested, list) else []
        else:
            candidates = []

        items: list[dict[str, Any]] = []
        for raw in candidates:
            if not isinstance(raw, dict):
                continue
            defect_type = str(raw.get("type") or raw.get("defect_type") or raw.get("label") or "unknown").strip()
            if not defect_type:
                defect_type = "unknown"
            confidence = ChatContextService._float(raw.get("confidence") or raw.get("score") or raw.get("probability"))
            bbox_raw = raw.get("bbox") or raw.get("box")
            bbox = [ChatContextService._float(item) for item in bbox_raw[:4]] if isinstance(bbox_raw, list) else None
            bbox = [item for item in bbox if item is not None] if bbox else None
            items.append(
                {
                    "type": defect_type[:80],
                    "confidence": confidence,
                    "bbox": bbox if bbox and len(bbox) == 4 else None,
                    "description": str(raw.get("description") or raw.get("desc") or "").strip()[:240] or None,
                    "image_index": raw.get("image_index"),
                }
            )
        return sorted(items, key=lambda item: float(item.get("confidence") or 0), reverse=True)[:limit]

    @staticmethod
    def _defect_summary(defects: list[dict[str, Any]], *, limit: int = 3) -> str | None:
        parts: list[str] = []
        for item in defects[:limit]:
            defect_type = str(item.get("type") or "unknown")
            confidence = item.get("confidence")
            if isinstance(confidence, (int, float)):
                percent = confidence * 100 if confidence <= 1 else confidence
                label = f"{defect_type} {percent:.1f}%"
            else:
                label = defect_type
            description = str(item.get("description") or "").strip()
            parts.append(f"{label}: {description}" if description else label)
        return "；".join(parts) or None

    @staticmethod
    def _failed_rules(raw_defects: Any, reasoning_chain: dict[str, Any]) -> list[str]:
        values: list[str] = []
        if isinstance(raw_defects, dict) and isinstance(raw_defects.get("failed_rules"), list):
            values.extend(str(item) for item in raw_defects.get("failed_rules") or [])
        standard = reasoning_chain.get("standard_evaluation")
        if isinstance(standard, dict):
            for item in list(standard.get("matched_rules") or []):
                if isinstance(item, dict):
                    label = item.get("rule_code") or item.get("code") or item.get("defect_type") or item.get("description")
                    if label:
                        values.append(str(label))
                elif item:
                    values.append(str(item))
            values.extend(str(item) for item in list(standard.get("reasons") or []) if item)
        return ChatContextService._dedupe_text(values, limit=8)

    @staticmethod
    def _failure_reasons(
        reasoning_chain: dict[str, Any],
        defects: list[dict[str, Any]],
        stability: StabilityReport | None,
    ) -> list[str]:
        reasons: list[str] = []
        standard = reasoning_chain.get("standard_evaluation")
        if isinstance(standard, dict):
            summary = str(standard.get("summary") or "").strip()
            if summary:
                reasons.append(summary)
            standard_reasons = [str(item) for item in list(standard.get("reasons") or []) if item]
            if standard_reasons:
                reasons.append(f"标准判定原因: {', '.join(standard_reasons[:4])}")
            unmatched = [str(item) for item in list(standard.get("unmatched_defects") or []) if item]
            if unmatched:
                reasons.append(f"未映射缺陷: {', '.join(unmatched[:4])}")
            matched_rules = []
            for item in list(standard.get("matched_rules") or []):
                if isinstance(item, dict):
                    matched_rules.append(
                        str(item.get("description") or item.get("defect_type") or item.get("rule_code") or "").strip()
                    )
                elif item:
                    matched_rules.append(str(item))
            if matched_rules:
                reasons.append(f"命中规则: {', '.join([item for item in matched_rules if item][:4])}")
            ai_gate = standard.get("ai_gate")
            if isinstance(ai_gate, dict):
                gate_reasons = [str(item) for item in list(ai_gate.get("reasons") or []) if item]
                if gate_reasons:
                    reasons.append(f"AI 门禁: {', '.join(gate_reasons[:4])}")
        defect_summary = ChatContextService._defect_summary(defects)
        if defect_summary:
            reasons.append(f"检出缺陷: {defect_summary}")
        if stability is not None and str(getattr(stability, "root_cause", "") or "").strip():
            reasons.append(f"稳定性根因: {str(stability.root_cause).strip()}")
        trust = reasoning_chain.get("trust_scoring")
        if isinstance(trust, dict):
            risk_bits: list[str] = []
            for key, label in (
                ("hallucination_risk", "幻觉风险"),
                ("overconfidence", "过度肯定风险"),
            ):
                value = ChatContextService._float(trust.get(key))
                if value is not None and value >= 0.3:
                    risk_bits.append(f"{label} {value:.2f}")
            if risk_bits:
                reasons.append("文本可信度风险: " + "，".join(risk_bits))
        return [item[:300] for item in ChatContextService._dedupe_text(reasons, limit=8)]

    @staticmethod
    def _reasoning_summary(reasoning_chain: dict[str, Any], failure_reasons: list[str]) -> str | None:
        for key in ("summary", "llm_reason", "conclusion"):
            value = str(reasoning_chain.get(key) or "").strip()
            if value:
                return value[:500]
        return failure_reasons[0] if failure_reasons else None

    @staticmethod
    def _manual_review_payload(inspection_result: InspectionResult | None, verdict: str | None) -> dict[str, Any] | None:
        if inspection_result is None:
            return None
        reviewed_by = getattr(inspection_result, "reviewed_by", None)
        reviewed_at = getattr(inspection_result, "reviewed_at", None)
        review_note = str(getattr(inspection_result, "review_note", "") or "").strip()
        required = str(verdict or "").lower() == "manual_required"
        if not any([required, reviewed_by, reviewed_at, review_note]):
            return None
        return {
            "required": required,
            "reviewed_by": str(reviewed_by) if reviewed_by else None,
            "reviewed_at": ChatContextService._iso(reviewed_at),
            "review_note": review_note[:500] or None,
        }

    @staticmethod
    def _dedupe_text(values: list[str], *, limit: int) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for raw in values:
            value = str(raw or "").strip()
            if not value:
                continue
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(value)
            if len(result) >= limit:
                break
        return result

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
