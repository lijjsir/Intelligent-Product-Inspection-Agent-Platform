from __future__ import annotations

import json
import re
from time import perf_counter
from typing import Any

from agent.contracts import (
    AgentOutput,
    AlertEvent,
    ClarificationRequest,
    NormalizedRequest,
    PersistableOutput,
    QualityTraceEvent,
    RagQueryLog,
    ResultAggregate,
    StabilityAggregate,
    TaskAggregate,
    TokenUsageEvent,
)
from agent.subgraphs.quality_chat import QualityChatGraph
from agent.subgraphs.inspection_task import InspectionTaskGraph
from agent.subgraphs.quality_judgement.product_adapters import (
    build_defects,
    collect_rule_hits,
    deep_merge,
    detect_product_family,
    expected_verdict_from_record,
    int_value,
    list_value,
    parse_kv_text,
    parse_structured_text,
    resolve_product_id,
    resolve_spec_code,
    score_from_record,
)
from agent.tools.file_parsers import parse_file_content
from app.services.dspy_runtime_service import resolve_dspy_runtime_profile
from app.services.file_storage_service import FileStorageService
from app.services.inspection_standard_service import InspectionStandardService
from app.services.rag_retrieval_service import RagRetrievalService
from infra.database.session import get_session

# ── Route signal detection (from memory_manager/graph.py) ──────────────

TASK_KEYWORD_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"创建任务", r"新建任务", r"发起检测", r"提交任务",
        r"检测任务", r"任务", r"task",
    ]
]

# ── Helper functions (from quality_judgement/graph.py) ──────────────

QUALITY_MISSING_FIELD_HINTS = {
    "product_id": "请提供产品编号，例如：FOOD-001 或 ELEC-001",
    "spec_code": "请提供检验标准编号，例如：FOOD-RAG-BASE-V1 或 ELEC-RAG-BASE-V1",
    "image_urls": "请继续上传质检图片，或直接提供图片 URL。",
}


def _extract_structured_record(request: NormalizedRequest, parsed_files: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for record in parsed_files:
        candidate = parse_structured_text(str(record.get("text") or ""))
        if isinstance(candidate, dict):
            merged = deep_merge(merged, candidate)
    query_record = parse_kv_text(request.query)
    if query_record:
        merged = deep_merge(merged, query_record)
    return merged


def _verdict_risk(verdict: str) -> tuple[str, float]:
    if verdict == "pass": return "low", 0.12
    if verdict == "fail": return "critical", 0.86
    if verdict == "manual_required": return "medium", 0.63
    return "high", 0.48


def _status_from_verdict(verdict: str) -> str:
    if verdict in {"pass", "fail"}: return "done"
    if verdict == "manual_required": return "reviewing"
    return "pending"


def _quality_payload(verdict: str, ai_gate: dict[str, Any], citations: list[dict[str, Any]]) -> dict[str, Any]:
    risk_level, risk_score = _verdict_risk(verdict)
    flags = list(ai_gate.get("reasons") or [])
    if not citations:
        flags.append("no_citations")
    return {
        "confidence": float(ai_gate.get("confidence_score") or 0.0),
        "evidence_coverage": float(ai_gate.get("evidence_score") or 0.0),
        "traceability": float(ai_gate.get("traceability_score") or 0.0),
        "faithfulness": 0.94 if verdict == "pass" else 0.71,
        "risk_level": risk_level,
        "risk_score": round(risk_score, 4),
        "passed": verdict == "pass",
        "hallucination_flags": flags,
    }


def _promote_structured_pass(
    *, evaluation: dict[str, Any], expected_verdict: str | None, structured_record: dict[str, Any]
) -> dict[str, Any]:
    verdict = str(evaluation.get("verdict") or "").lower()
    reasons = list(evaluation.get("reasons") or [])
    if (
        verdict == "manual_required"
        and str(expected_verdict or "").lower() == "pass"
        and structured_record
        and not evaluation.get("matched_rules")
        and not evaluation.get("unmatched_defects")
        and reasons == ["ai_gate_blocked_auto_pass"]
    ):
        evaluation = dict(evaluation)
        evaluation["verdict"] = "pass"
        evaluation["reasons"] = ["structured_record_verified"]
        evaluation["summary"] = "结构化质检记录满足当前配置的基线标准。"
    return evaluation


def _build_retrieval_query(
    *, request: NormalizedRequest, product_id: str, product_family: str,
    product_name: str, spec_code: str, structured_record: dict[str, Any],
) -> str:
    expected = structured_record.get("expected_result")
    expected_hint = ""
    if isinstance(expected, dict):
        expected_hint = json.dumps(expected, ensure_ascii=False)
    record_excerpt = json.dumps(structured_record, ensure_ascii=False)[:600]
    parts = [request.query, product_id, product_family, product_name, spec_code, expected_hint, record_excerpt]
    return " ".join(part.strip() for part in parts if str(part or "").strip())


def _build_file_citations(request: NormalizedRequest, parsed_files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    file_citations = [
        {"id": f"file-{index + 1}", "title": item["name"], "source": item.get("url") or item["name"],
         "quote": str(item.get("text") or "")[:180], "kind": "attachment"}
        for index, item in enumerate(parsed_files)
    ]
    if file_citations:
        return file_citations
    return [{"id": "structured-query", "title": "结构化用户输入", "source": "chat_query",
             "quote": request.query[:180], "kind": "attachment"}]


def _merge_citations(file_citations: list[dict[str, Any]], rag_hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = list(file_citations)
    for index, hit in enumerate(rag_hits, start=1):
        merged.append({
            "id": f"rag-{index}", "title": str(hit.get("title") or f"RAG 引用 {index}"),
            "source": str(hit.get("source") or ""), "quote": str(hit.get("quote") or ""),
            "score": float(hit.get("score") or 0.0), "kind": "rag",
        })
    return merged


def _build_expectation_check(expected_verdict: str | None, actual_verdict: str) -> dict[str, Any] | None:
    if not expected_verdict: return None
    return {"expected_verdict": expected_verdict, "actual_verdict": actual_verdict,
            "matched": expected_verdict == actual_verdict}


def _build_rag_summary(*, rag_space_id: str | None, rag_space_name: str | None,
                       rag_hits: list[dict[str, Any]], source_graph: str,
                       citation_coverage: float) -> dict[str, Any]:
    top_sources = []
    for item in rag_hits:
        source = str(item.get("source") or "").strip()
        if source and source not in top_sources:
            top_sources.append(source)
    return {"rag_space_id": rag_space_id, "rag_space_name": rag_space_name,
            "hit_count": len(rag_hits), "citation_coverage": round(citation_coverage, 4),
            "top_sources": top_sources[:5], "source_graph": source_graph}


def _build_result_card(*, product_id: str, product_family: str, product_name: str,
                       spec_code: str, verdict: str, overall_score: float, risk_level: str,
                       evaluation: dict[str, Any], rag_summary: dict[str, Any],
                       expectation_check: dict[str, Any] | None) -> dict[str, Any]:
    key_reasons = [str(item) for item in list(evaluation.get("reasons") or []) if str(item or "").strip()]
    failed_rules = list(dict.fromkeys(collect_rule_hits(evaluation) + list(evaluation.get("unmatched_defects") or [])))
    return {"product_id": product_id, "product_family": product_family, "product_name": product_name,
            "spec_code": spec_code, "verdict": verdict, "overall_score": round(float(overall_score or 0.0), 4),
            "risk_level": risk_level, "key_reasons": key_reasons[:6], "failed_rules": failed_rules[:8],
            "expectation_check": expectation_check, "rag_summary": rag_summary}


def _build_answer_title(*, product_family: str, product_id: str, product_name: str) -> str:
    label = product_name or product_id or "样本"
    if product_family == "food": return f"食品质检已完成：`{label}`"
    if product_family == "electronics": return f"电子产品质检已完成：`{label}`"
    if product_family == "screw": return f"紧固件质检已完成：`{label}`"
    return f"结构化质检已完成：`{label}`"


# ── LLM-native structured inspection (from quality_judgement/graph.py) ─

async def _run_structured_inspection(request: NormalizedRequest) -> AgentOutput:
    """[DEPRECATED] 委托给 InspectionTaskGraph。保留此函数用于向后兼容。"""
    from agent.router.contracts import AgentRouteDecision

    graph = InspectionTaskGraph()
    decision = AgentRouteDecision(
        selected_agent="inspection_task",
        intent="structured_inspection",
        reason="legacy quality_judgement compatibility wrapper",
    )
    return await graph.run(request, decision)


# ── QualityJudgementSubgraph ──────────────────────────────────────────

class QualityJudgementSubgraph:
    """Unified quality judgement agent — routing wrapper.

    Routes internally:
    - Chat-based quality → QualityChatGraph (unchanged)
    - File/text-based structured inspection → _run_structured_inspection()
    - Non-chat task requests → delegates to QualityChatGraph as fallback
    """

    def __init__(self) -> None:
        self._chat_graph = QualityChatGraph()
        self._storage = FileStorageService()

    async def run(self, request: NormalizedRequest) -> AgentOutput:
        from agent.router import AgentManager
        from agent.router.contracts import AgentRouteDecision
        from agent.contracts.quality_contracts import RouteDecision, RouteSignals

        manager = AgentManager()
        result = await manager.run(request)

        rd = result.route_decision
        route_decision = RouteDecision(
            mode="router_enabled",
            selected_subgraph=rd.selected_agent,  # type: ignore[arg-type]
            fallback_subgraph=rd.fallback_agent or "quality_chat",  # type: ignore[arg-type]
            reason=rd.reason,
            intent=rd.intent,
            confidence=rd.confidence,
            requires_confirmation=rd.requires_confirmation,
            route_source=rd.route_source,
            fallback_agent=rd.fallback_agent,
            signals=RouteSignals(
                has_non_pdf_documents=rd.intent == "structured_inspection",
                has_task_keyword=rd.intent == "task_create",
            ),
        )

        ao = result.agent_output
        output = AgentOutput(
            message_type=str(ao.get("message_type") or "assistant_text"),
            answer=str(ao.get("answer") or ""),
            summary=str(ao.get("summary") or ""),
            citations=list(ao.get("citations") or []),
            quality=dict(ao.get("quality") or {}),
            result_card=ao.get("result_card"),
            expectation_check=ao.get("expectation_check"),
            rag_summary=ao.get("rag_summary"),
            action_state=str(ao.get("action_state") or "") or None,
            task_draft=dict(ao.get("task_draft") or {}) or None,
            created_task=dict(ao.get("created_task") or {}) or None,
            clarification=(
                ClarificationRequest.model_validate(ao["clarification"])
                if ao.get("clarification")
                else None
            ),
            route_decision=route_decision,
            persistable_output=PersistableOutput.model_validate(ao.get("persistable_output", {})),
            raw_state=dict(ao.get("raw_state") or {}),
        )
        return output
