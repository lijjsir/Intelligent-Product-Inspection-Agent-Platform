from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.stability_repo import StabilityRepository
from app.repositories.result_repo import ResultRepository
from app.services.result_trace_utils import build_rag_summary_from_reasoning, extract_citation_items


class StabilityService:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id
        self._repo = StabilityRepository(session)

    async def get_by_task(self, task_id: str):
        report = await self._repo.get_by_task(self._org_id, task_id)
        if report is None:
            return None
        result = await ResultRepository(self._session).get_by_task(self._org_id, task_id)
        reasoning = dict(getattr(result, "reasoning_chain", None) or {})
        citations = extract_citation_items(getattr(result, "citations", None))
        verified_citations = [
            item for item in citations
            if str(item.get("kind") or "").lower() == "rag"
            and str(item.get("quote") or item.get("excerpt") or "").strip()
            and str(item.get("source") or item.get("id") or item.get("source_id") or "").strip()
        ]
        legacy_dimensions = not bool(report.dimension_detail)
        detail = dict(report.dimension_detail or {})
        detail.setdefault(
            "purpose",
            "评估单次检测结论是否有足够证据、规则依据和异常风险，用于决定能否自动放行或应转人工复核",
        )
        detail.setdefault("evidence", {"status": "measured", "citation_count": len(verified_citations)})
        detail.setdefault("consistency", {
            "status": "not_measured",
            "reason": "历史任务没有重复采样结果，不能计算前后一致性",
        })
        detail.setdefault("confidence", {
            "status": str(reasoning.get("score_status") or "not_calibrated"),
            "reason": "模型自评分未经业务样本校准，不作为概率展示",
        })
        detail.setdefault("traceability", {"status": "measured" if verified_citations else "missing"})
        detail.setdefault("rag", build_rag_summary_from_reasoning(reasoning, verified_citations))

        root_cause = str(report.root_cause or "").strip()
        if not root_cause:
            standard = dict(reasoning.get("standard_evaluation") or {})
            reasons: list[str] = []
            if not verified_citations:
                reasons.append("知识库没有命中可核验的标准原文，当前结论缺少外部标准引证")
            if str(getattr(result, "verdict", "")) == "manual_required":
                reasons.append(str(standard.get("summary") or "自动判定条件不足，需要人工复核"))
            if not reasons:
                reasons.append("未发现高风险项；本报告仅评估单次结果的可信风险，未执行重复采样，不能据此证明模型长期稳定")
            root_cause = "；".join(reasons)

        return {
            "id": report.id,
            "task_id": report.task_id,
            "result_id": report.result_id,
            "org_id": report.org_id,
            "evidence_score": (
                min(1.0, len(verified_citations) / 2)
                if legacy_dimensions else float(report.evidence_score or 0.0)
            ),
            "consistency_score": float(report.consistency_score or 0.0),
            "confidence_score": float(report.confidence_score or 0.0),
            "traceability_score": (
                (1.0 if verified_citations else 0.25 if reasoning else 0.0)
                if legacy_dimensions else float(report.traceability_score or 0.0)
            ),
            "anomaly_score": float(report.anomaly_score or 0.0),
            "risk_score": float(report.risk_score or 0.0),
            "risk_level": report.risk_level,
            "dimension_detail": detail,
            "sampling_results": report.sampling_results,
            "root_cause": root_cause,
            "handled_by": report.handled_by,
            "handled_at": report.handled_at,
            "handle_action": report.handle_action,
            "handle_note": report.handle_note,
            "created_at": report.created_at,
        }
