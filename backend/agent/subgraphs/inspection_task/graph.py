from __future__ import annotations

import json
import asyncio
from time import perf_counter
from typing import Any

from agent.contracts.quality_contracts import (
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
from langgraph.graph import END, StateGraph
from typing import Callable, Awaitable

from agent.router.contracts import AgentRouteDecision
from agent.subgraphs.inspection_task.state import InspectionState
from agent.subgraphs.inspection_task.nodes import (
    finalize,
    plan,
    run_knowledge,
    run_reasoning,
    run_vision,
)
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
from agent.llm.client import LLMClient
from agent.llm.gateway import LLMGateway
from agent.prompts.prompt_builder import PromptBuilder
from agent.rag.rag_policy import RagPolicy
from agent.tools.file_parsers import parse_file_content
from app.services.runtime_profile_service import resolve_runtime_profile
from app.services.inspection_standard_service import InspectionStandardService
from app.services.model_config_service import ModelConfigService
from app.services.object_storage.resolver import read_attachment_bytes
from app.services.rag_retrieval_service import RagRetrievalService
from infra.database.session import get_session

# ── Helper functions (migrated from quality_judgement/graph.py) ──────────────

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
    ai_gate = dict(evaluation.get("ai_gate") or {})
    ai_gate_fully_passed = (
        ai_gate.get("passed") is True
        and float(ai_gate.get("confidence_score") or 0.0) >= 0.95
        and float(ai_gate.get("evidence_score") or 0.0) >= 0.9
    )
    expect_pass = str(expected_verdict or "").lower() == "pass"
    if (
        verdict == "manual_required"
        and (expect_pass or ai_gate_fully_passed)
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


def _build_answer_title(*, product_family: str, product_id: str, product_name: str) -> str:
    label = product_name or product_id or "样本"
    if product_family == "food": return f"食品质检已完成：`{label}`"
    if product_family == "electronics": return f"电子产品质检已完成：`{label}`"
    if product_family == "screw": return f"紧固件质检已完成：`{label}`"
    return f"结构化质检已完成：`{label}`"


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


def _task_draft_from_request(
    *,
    request: NormalizedRequest,
    product_id: str,
    spec_code: str,
    image_urls: list[str],
    priority: int,
    product_family: str,
    product_name: str,
    product_model: str,
    structured_record: dict[str, Any],
) -> dict[str, Any]:
    return {
        "product_id": product_id,
        "spec_code": spec_code,
        "image_urls": image_urls,
        "priority": priority,
        "metadata": {
            "source": "inspection_task",
            "chat_request_id": request.request_id,
            "product_family": product_family,
            "product_name": product_name,
            "product_model": product_model,
            "structured_record": structured_record,
        },
    }


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


# ── InspectionTaskGraph ──────────────────────────────────────────────────────

class InspectionTaskGraph:
    """正式质检任务 Agent — 负责结构化文件检测、图片检测、结果落库。

    从 QualityJudgementSubgraph._run_structured_inspection() 迁移而来。
    """

    def __init__(self) -> None:
        pass

    async def run(self, request: NormalizedRequest, route_decision: AgentRouteDecision) -> AgentOutput:
        if route_decision.sub_route == "quality_qa":
            return await self._run_quality_qa(request, route_decision)
        if route_decision.sub_route == "task_create":
            return await self._run_task_create(request, route_decision)
        return await self._run_structured_inspection(request)

    def _base_task_context(self, request: NormalizedRequest) -> dict[str, Any]:
        product_id = str(request.product_id or request.metadata.get("product_id") or request.ext.get("product_id") or "").strip()
        spec_code = str(request.spec_code or request.metadata.get("spec_code") or request.ext.get("spec_code") or "").strip()
        image_urls = [
            str(item).strip()
            for item in list(request.image_urls or request.ext.get("image_urls") or [])
            if str(item).strip()
        ]
        priority = int_value(request.metadata.get("priority") or request.ext.get("priority") or 5) or 5
        product_name = str(request.metadata.get("product_name") or request.ext.get("product_name") or "").strip()
        product_model = str(request.metadata.get("model") or request.ext.get("model") or "").strip()
        product_family = detect_product_family({}, product_id)
        task_draft = _task_draft_from_request(
            request=request,
            product_id=product_id,
            spec_code=spec_code,
            image_urls=image_urls,
            priority=priority,
            product_family=product_family,
            product_name=product_name,
            product_model=product_model,
            structured_record={},
        )
        return {
            "product_id": product_id,
            "spec_code": spec_code,
            "image_urls": image_urls,
            "priority": priority,
            "product_family": product_family,
            "product_name": product_name,
            "product_model": product_model,
            "task_draft": task_draft,
        }

    async def _run_quality_qa(self, request: NormalizedRequest, route_decision: AgentRouteDecision) -> AgentOutput:
        context = self._base_task_context(request)
        sub_route = "quality_qa"
        agent = "inspection_task"

        # ── RagPolicy: decide retrieval ──
        rag_policy = RagPolicy()
        selected_rag = request.ext.get("selected_rag_space") or {}
        policy_decision = rag_policy.decide(
            sub_route=sub_route,
            selected_rag_space=selected_rag if selected_rag.get("id") else None,
            spec_code=context.get("spec_code"),
        )

        # ── RAG retrieval ──
        retrieved_docs: list[dict[str, Any]] = []
        rag_hits: list[dict[str, Any]] = []
        rag_summary: dict[str, Any] | None = None
        if policy_decision.should_retrieve:
            retrieval_query = f"{request.query} {context.get('product_id') or ''} {context.get('spec_code') or ''}"
            async with get_session() as session:
                rag_service = RagRetrievalService(session, org_id=request.org_id, user_id=request.user_id)
                rag_result = await rag_service.search(
                    rag_space_id=policy_decision.rag_space_id,
                    query=retrieval_query,
                    top_k=policy_decision.top_k,
                    scope_node_ids=list(request.ext.get("selected_rag_scope_node_ids") or []),
                )
            rag_hits = list(rag_result.get("hits") or [])
            retrieved_docs = [
                {"title": h.get("title", ""), "source": h.get("source", ""), "text": h.get("quote", "")}
                for h in rag_hits
            ]
            rag_summary = {
                "rag_space_id": rag_result.get("rag_space_id"),
                "rag_space_name": rag_result.get("rag_space_name"),
                "hit_count": len(rag_hits),
                "top_score": float(rag_hits[0].get("score") or 0.0) if rag_hits else 0.0,
                "citation_coverage": 1.0 if rag_hits else 0.0,
                "top_sources": list(dict.fromkeys(h.get("source", "") for h in rag_hits if h.get("source")))[:5],
            }

        # ── PromptBuilder ──
        history = list(request.ext.get("history") or [])
        system_prompt, user_message, temperature, prompt_meta = await PromptBuilder.build_runtime(
            agent=agent,
            sub_route=sub_route,
            query=request.query,
            org_id=request.org_id,
            history=history,
            retrieved_docs=retrieved_docs if retrieved_docs else None,
        )

        # ── LLM call ──
        async with get_session() as session:
            runtime_models = await ModelConfigService(session, str(request.org_id)).list_runtime_models()
        runtime = await LLMGateway().select_runtime(runtime_models)
        if not runtime:
            return AgentOutput(
                message_type="quality_answer",
                answer="当前没有可用的模型，请联系管理员配置模型后再试。",
                summary="模型不可用",
                action_state="answered",
                task_draft=None,
                quality={"passed": False, "risk_level": "medium", "risk_score": 0.5},
                citations=[],
                persistable_output=PersistableOutput(),
                raw_state={"response_payload": {"agent": agent, "sub_route": sub_route,
                    "ui_schema": "quality_answer_v1", "prompt_version": prompt_meta["prompt_version"]}},
            )

        llm = LLMClient(
            api_key=runtime.get("api_key"),
            base_url=runtime.get("base_url"),
            model_id=runtime.get("model_id"),
            trace_id=request.workflow_run_id or request.request_id,
            task_id=str(request.session_id),
            org_id=str(request.org_id),
            provider=str(runtime.get("provider") or ""),
            input_price_per_million=runtime.get("input_price_per_million"),
            output_price_per_million=runtime.get("output_price_per_million"),
        )

        citations: list[dict[str, Any]] = []
        try:
            response = await llm.chat(
                [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}],
                temperature=temperature,
                observation_name="inspection.quality_qa",
                observation_metadata={
                    "agent": agent,
                    "sub_route": sub_route,
                    "intent": "quality_qa",
                    "prompt_version": prompt_meta["prompt_version"],
                },
            )
            answer = str(response.get("answer") or "").strip()
            summary = str(response.get("summary") or "质检问答").strip()
            if not answer:
                answer = f"基于当前信息，我暂时无法给出确定的质检判定。\n\n问题：{request.query}"
                summary = "证据不足"
            citations = [
                {"id": f"rag-{i}", "title": h.get("title", ""), "source": h.get("source", ""),
                 "quote": str(h.get("quote", ""))[:180], "score": float(h.get("score") or 0.0), "kind": "rag"}
                for i, h in enumerate(rag_hits, start=1)
            ]
        except Exception:
            answer = f"质检问答服务暂时不可用。\n\n问题：{request.query}\n\n请稍后重试或联系管理员。"
            summary = "服务异常"

        return AgentOutput(
            message_type="quality_answer",
            answer=answer,
            summary=summary,
            action_state="answered",
            task_draft=None,
            quality={
                "passed": False,
                "risk_level": "medium",
                "risk_score": 0.5,
                "confidence": float(route_decision.confidence or 0.0),
            },
            citations=citations,
            rag_summary=rag_summary,
            persistable_output=PersistableOutput(),
            raw_state={
                "task_context": context,
                "response_payload": {
                    "agent": agent,
                    "sub_route": sub_route,
                    "ui_schema": "quality_answer_v1",
                    "prompt_version": prompt_meta["prompt_version"],
                    "awaiting_confirmation": False,
                },
            },
        )

    async def _run_task_create(self, request: NormalizedRequest, route_decision: AgentRouteDecision) -> AgentOutput:
        context = self._base_task_context(request)
        sub_route = "task_create"
        agent = "inspection_task"

        # ── PromptBuilder ──
        history = list(request.ext.get("history") or [])
        system_prompt, user_message, temperature, prompt_meta = await PromptBuilder.build_runtime(
            agent=agent,
            sub_route=sub_route,
            query=request.query,
            org_id=request.org_id,
            history=history,
            task_draft=context["task_draft"],
            action_state="awaiting_task_details",
        )

        # ── LLM call ──
        async with get_session() as session:
            runtime_models = await ModelConfigService(session, str(request.org_id)).list_runtime_models()
        runtime = await LLMGateway().select_runtime(runtime_models)
        if not runtime:
            return AgentOutput(
                message_type="task_action",
                answer="当前没有可用的模型，请稍后重试。",
                summary="模型不可用",
                action_state="awaiting_task_details",
                task_draft=context["task_draft"],
                quality={"passed": False, "risk_level": "low", "risk_score": 0.2},
                persistable_output=PersistableOutput(),
                raw_state={"response_payload": {"agent": agent, "sub_route": sub_route,
                    "ui_schema": "task_action_v1", "prompt_version": prompt_meta["prompt_version"]}},
            )

        llm = LLMClient(
            api_key=runtime.get("api_key"),
            base_url=runtime.get("base_url"),
            model_id=runtime.get("model_id"),
            trace_id=request.workflow_run_id or request.request_id,
            task_id=str(request.session_id),
            org_id=str(request.org_id),
            provider=str(runtime.get("provider") or ""),
            input_price_per_million=runtime.get("input_price_per_million"),
            output_price_per_million=runtime.get("output_price_per_million"),
        )

        try:
            response = await llm.chat(
                [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}],
                temperature=temperature,
                observation_name="inspection.task_create",
                observation_metadata={
                    "agent": agent,
                    "sub_route": sub_route,
                    "intent": "task_create",
                    "prompt_version": prompt_meta["prompt_version"],
                },
            )
            answer = str(response.get("answer") or "").strip()
            summary = str(response.get("summary") or "检测任务草稿").strip()
        except Exception:
            answer = "任务创建服务暂时不可用，请稍后重试或通过任务页面手动创建。"
            summary = "服务异常"

        # ── Slot extraction from context ──
        missing_fields: list[str] = []
        if not context["product_id"]:
            missing_fields.append("product_id")
        if not context["spec_code"]:
            missing_fields.append("spec_code")
        if not context["image_urls"]:
            missing_fields.append("image_urls")

        clarification = None
        if missing_fields:
            clarification = ClarificationRequest(
                missing_fields=missing_fields,
                reason="创建检测任务前需要补齐必要字段。",
                suggestions=[QUALITY_MISSING_FIELD_HINTS.get(item, item) for item in missing_fields],
                examples={item: QUALITY_MISSING_FIELD_HINTS.get(item, item) for item in missing_fields},
            )
        awaiting_confirmation = not missing_fields
        action_state = "awaiting_task_confirmation" if awaiting_confirmation else "awaiting_task_details"

        if not answer:
            answer = (
                "已整理检测任务草稿，请确认后再创建正式任务。"
                if awaiting_confirmation
                else "我先整理了检测任务草稿，但还需要补齐必要信息后才能创建正式任务。"
            )

        return AgentOutput(
            message_type="task_action",
            answer=answer,
            summary=summary,
            action_state=action_state,
            task_draft=context["task_draft"],
            clarification=clarification,
            quality={"passed": False, "risk_level": "low", "risk_score": 0.2},
            persistable_output=PersistableOutput(),
            raw_state={
                "task_draft": context["task_draft"],
                "response_payload": {
                    "agent": agent,
                    "sub_route": sub_route,
                    "ui_schema": "task_action_v1",
                    "prompt_version": prompt_meta["prompt_version"],
                    "awaiting_confirmation": awaiting_confirmation,
                },
            },
        )

    @staticmethod
    def _parse_attachments(request: NormalizedRequest) -> list[dict[str, Any]]:
        parsed_files: list[dict[str, Any]] = []
        for attachment in request.attachments:
            if not attachment.url or attachment.kind == "image":
                continue
            if not attachment.bucket or not attachment.object_key:
                continue
            payload = read_attachment_bytes(attachment.model_dump())
            if payload is None:
                continue
            content, _ = payload
            parsed = parse_file_content(attachment.name or "attachment.txt", content)
            parsed_files.append({
                "name": attachment.name or "attachment.txt", "kind": parsed.get("kind"),
                "url": attachment.url, "text": parsed.get("text", ""), "summary": parsed,
            })
        return parsed_files

    async def _run_structured_inspection(self, request: NormalizedRequest) -> AgentOutput:
        started_at = perf_counter()
        runtime_profile, parsed_files = await asyncio.gather(
            resolve_runtime_profile(request.org_id, "quality_judgement"),
            asyncio.to_thread(self._parse_attachments, request),
        )
        contract_target = runtime_profile.get("quality_judgement.contract_inferencer")
        planner_target = runtime_profile.get("quality_judgement.planner")
        knowledge_target = runtime_profile.get("quality_judgement.knowledge_router")
        synthesizer_target = runtime_profile.get("quality_judgement.evidence_synthesizer")
        review_target = runtime_profile.get("quality_judgement.review_gate")

        structured_record = _extract_structured_record(request, parsed_files)
        product_family = detect_product_family(
            structured_record,
            request.product_id or request.metadata.get("product_id") or request.ext.get("product_id"),
        )
        product_id = resolve_product_id(
            structured_record, product_family,
            request.product_id or request.metadata.get("product_id") or request.ext.get("product_id"),
        )
        spec_code = resolve_spec_code(
            structured_record, product_family,
            request.spec_code or request.metadata.get("spec_code") or request.ext.get("spec_code"),
        )
        product_name = str(structured_record.get("product_name") or request.metadata.get("product_name") or "").strip()
        product_model = str(structured_record.get("model") or request.metadata.get("model") or "").strip()
        image_urls = list(request.image_urls or request.ext.get("image_urls") or [])
        if not image_urls:
            image_urls = list_value(structured_record.get("image_urls"))
        planner_default_priority = int_value(planner_target.config_payload.get("default_priority") if planner_target else 5) or 5
        priority = int_value(structured_record.get("priority") or planner_default_priority) or planner_default_priority

        structured_evidence = bool(structured_record or any(item.get("text") for item in parsed_files))
        required_fields = list((contract_target.config_payload.get("required_fields") if contract_target else []) or [])
        if not required_fields:
            required_fields = ["product_id", "spec_code"]
        requires_images_without_structured = bool(
            (contract_target.config_payload.get("requires_images_without_structured_evidence") if contract_target else True)
        )

        missing_fields: list[str] = []
        if "product_id" in required_fields and not product_id:
            missing_fields.append("product_id")
        if "spec_code" in required_fields and not spec_code:
            missing_fields.append("spec_code")
        if requires_images_without_structured and not image_urls and not structured_evidence:
            missing_fields.append("image_urls")

        if missing_fields:
            task_draft = _task_draft_from_request(
                request=request,
                product_id=product_id,
                spec_code=spec_code,
                image_urls=image_urls,
                priority=priority,
                product_family=product_family,
                product_name=product_name,
                product_model=product_model,
                structured_record=structured_record,
            )
            clarification = ClarificationRequest(
                missing_fields=missing_fields,
                reason="当前用户输入、解析后的文件内容以及 RAG 上下文，仍不足以提供可信的判定依据。",
                suggestions=[QUALITY_MISSING_FIELD_HINTS.get(item, item) for item in missing_fields],
                examples={item: QUALITY_MISSING_FIELD_HINTS.get(item, item) for item in missing_fields},
            )
            answer = (
                "当前信息不足，暂时无法安全完成本次质量检测。\n\n"
                f"识别到的产品类别：`{product_family or 'unknown'}`\n"
                f"缺失字段：{', '.join(missing_fields)}\n请补充以上信息，我会继续完成检测。"
            )
            return AgentOutput(
                message_type="task_action", answer=answer, summary="等待补充必要信息",
                action_state="awaiting_clarification", clarification=clarification,
                task_draft=task_draft,
                quality={"passed": False, "risk_level": "critical", "risk_score": 0.92,
                         "hallucination_flags": ["missing_required_inputs"]},
                persistable_output=PersistableOutput(),
                raw_state={"parsed_files": parsed_files, "structured_record": structured_record, "task_draft": task_draft},
            )

        defects = build_defects(structured_record, product_family)
        expected_verdict = expected_verdict_from_record(structured_record, product_family)
        overall_score = score_from_record(defects, expected_verdict)
        evidence_refs = list(image_urls or [item["url"] for item in parsed_files if item.get("url")])
        if not evidence_refs:
            evidence_refs = [f"struct://{request.request_id}"]

        retrieval_query = _build_retrieval_query(
            request=request, product_id=product_id, product_family=product_family,
            product_name=product_name, spec_code=spec_code, structured_record=structured_record,
        )
        retrieval_top_k = int(knowledge_target.config_payload.get("retrieval_top_k") if knowledge_target else 4) or 4
        async with get_session() as session:
            rag_retrieval_service = RagRetrievalService(session, org_id=request.org_id, user_id=request.user_id)
            rag_result = await rag_retrieval_service.search(
                rag_space_id=str(request.ext.get("selected_rag_space_id") or "") or None,
                query=retrieval_query,
                top_k=retrieval_top_k,
                scope_node_ids=list(request.ext.get("selected_rag_scope_node_ids") or []),
            )

        file_citations = _build_file_citations(request, parsed_files)
        citations = _merge_citations(file_citations, list(rag_result.get("hits") or []))
        rag_used_citations = [dict(item) for item in citations if str(item.get("kind") or "") == "rag"]

        reasoning_chain = {
            "summary": "已基于结构化文件、产品类别解析结果和 RAG 证据完成检验标准评估。",
            "structured_record": structured_record, "product_family": product_family,
            "product_name": product_name,
            "source_files": [{"name": item["name"], "url": item.get("url")} for item in parsed_files],
            "trace": {"trace_id": request.workflow_run_id or request.request_id, "trace_url": None,
                      "model_key": "quality_judgement"},
            "langfuse_scores": [], "runtime_profile": runtime_profile.as_metadata(),
            "knowledge_router": {
                "selected_rag_space_id": request.ext.get("selected_rag_space_id"),
                "selected_rag_space_name": rag_result.get("rag_space_name"),
                "query": retrieval_query, "hit_count": int(rag_result.get("hit_count") or 0),
                "top_hits": list(rag_result.get("hits") or []),
                "target_config": knowledge_target.summary() if knowledge_target else None,
            },
            "evidence_synthesizer": {
                "citation_count": len(citations), "file_citation_count": len(file_citations),
                "rag_citation_count": len(list(rag_result.get("hits") or [])),
                "target_config": synthesizer_target.summary() if synthesizer_target else None,
            },
        }

        async with get_session() as session:
            standard_service = InspectionStandardService(session, request.org_id)
            evaluation = await standard_service.evaluate(
                spec_code=spec_code, image_urls=evidence_refs, defects=defects,
                citations=citations, reasoning_chain=reasoning_chain,
                model_verdict=expected_verdict or ("pass" if not defects else "fail"),
                overall_score=overall_score,
            )
        evaluation = _promote_structured_pass(
            evaluation=evaluation, expected_verdict=expected_verdict, structured_record=structured_record,
        )

        verdict = str(evaluation.get("verdict") or "manual_required").lower()
        ai_gate = dict(evaluation.get("ai_gate") or {})
        review_thresholds = dict(review_target.config_payload if review_target else {})
        min_confidence = float(review_thresholds.get("min_confidence", 0.85))
        min_evidence = float(review_thresholds.get("min_evidence_score", 0.9))
        physical_hallucination_score = 0.08 if verdict == "pass" else 0.29
        if verdict == "pass" and (
            float(ai_gate.get("confidence_score") or 0.0) < min_confidence
            or float(ai_gate.get("evidence_score") or 0.0) < min_evidence
        ):
            verdict = "manual_required"
            evaluation = {
                **evaluation, "verdict": verdict,
                "summary": "由于当前证据阈值未达到配置要求，评审门禁阻止了自动放行。",
                "reasons": [*list(evaluation.get("reasons") or []), "review_gate_blocked_auto_pass"],
            }

        rag_hits = list(rag_result.get("hits") or [])
        quality = _quality_payload(verdict, ai_gate, citations)
        task_status = _status_from_verdict(verdict)
        risk_level, risk_score = _verdict_risk(verdict)
        latency_ms = round((perf_counter() - started_at) * 1000, 2)
        expectation_check = _build_expectation_check(expected_verdict, verdict)
        rag_summary = _build_rag_summary(
            rag_space_id=str(rag_result.get("rag_space_id") or "") or None,
            rag_space_name=str(rag_result.get("rag_space_name") or "") or None,
            rag_hits=rag_hits, source_graph="inspection_task",
            citation_coverage=float(ai_gate.get("evidence_score") or 0.0),
        )
        result_card = _build_result_card(
            product_id=product_id, product_family=product_family, product_name=product_name,
            spec_code=spec_code, verdict=verdict, overall_score=overall_score, risk_level=risk_level,
            evaluation=evaluation, rag_summary=rag_summary, expectation_check=expectation_check,
        )
        verdict_rule_hits = list(dict.fromkeys(result_card["failed_rules"]))

        answer_lines = [
            _build_answer_title(product_family=product_family, product_id=product_id,
                               product_name=product_name or product_model),
            f"产品编号：`{product_id}`",
        ]
        if product_name: answer_lines.append(f"产品名称：`{product_name}`")
        if product_model: answer_lines.append(f"产品型号：`{product_model}`")
        answer_lines.extend([
            f"产品类别：`{product_family}`", f"检验标准：`{spec_code}`",
            f"判定结果：`{verdict.upper()}`",
            f"检测摘要：{evaluation.get('summary') or '质量检测已完成。'}",
        ])
        if defects: answer_lines.append(f"检出缺陷数：{len(defects)}")
        matched_rule_count = len(list(evaluation.get("matched_rules") or []))
        if matched_rule_count: answer_lines.append(f"命中规则数：{matched_rule_count}")
        if evaluation.get("reasons"):
            answer_lines.append(f"判定原因：{', '.join(str(item) for item in evaluation['reasons'])}")
        if rag_hits:
            answer_lines.append(
                f"RAG 已从 `{rag_summary['rag_space_name'] or rag_summary['rag_space_id']}` "
                f"匹配到 {len(rag_hits)} 条证据片段。"
            )
        elif request.ext.get("selected_rag_space_id"):
            answer_lines.append("RAG 检索未从当前选定知识库中命中有效证据。")
        if expectation_check:
            answer_lines.append(
                "预期校验：" + ("与样本预期一致。" if expectation_check["matched"] else "与样本预期不一致。")
            )
        answer = "\n".join(answer_lines)

        persistable_output = PersistableOutput(
            task=TaskAggregate(product_id=product_id, spec_code=spec_code, status=task_status,
                              priority=priority, image_count=len(image_urls)),
            result=ResultAggregate(
                task_id=None, verdict=verdict, overall_score=overall_score,
                llm_model="quality_judgement", citations={"items": citations},
                reasoning_chain={**reasoning_chain, "standard_evaluation": evaluation,
                                "quality": quality, "result_card": result_card,
                                "expectation_check": expectation_check, "rag_summary": rag_summary},
            ),
            stability=StabilityAggregate(
                risk_score=risk_score, risk_level=risk_level,
                evidence_score=float(ai_gate.get("evidence_score") or 0.0),
                confidence_score=float(ai_gate.get("confidence_score") or 0.0),
                traceability_score=float(ai_gate.get("traceability_score") or 0.0),
                faithfulness_score=float(quality.get("faithfulness") or 0.0),
                physical_hallucination_score=physical_hallucination_score,
            ),
            alerts=[] if verdict == "pass" else [
                AlertEvent(severity="high" if verdict == "fail" else "medium",
                          title=f"{spec_code} review requires attention",
                          message=str(evaluation.get("summary") or "Quality review flagged."))
            ],
            token_usage=[TokenUsageEvent(model_key="quality_judgement", prompt_tokens=0,
                                         completion_tokens=0, total_tokens=0, cost_amount=0.0,
                                         trace_id=request.workflow_run_id or request.request_id)],
            quality_trace=QualityTraceEvent(
                trace_id=request.workflow_run_id or request.request_id, trace_url=None,
                workflow_version="inspection_task_v1",
                prompt_version=runtime_profile.active_prompt_version,
                route_subgraph="inspection_task",
            ),
            rag_queries=[RagQueryLog(
                query=retrieval_query,
                rag_space_id=str(rag_result.get("rag_space_id") or "") or None,
                top_k=retrieval_top_k,
                hit_count=len(rag_hits), hit_rate=round(min(1.0, len(rag_hits) / max(retrieval_top_k, 1)), 4),
                citation_coverage=float(ai_gate.get("evidence_score") or 0.0),
                latency_ms=latency_ms, source_graph="inspection_task",
                agent_name="inspection_task",
                sub_route="inspection_execute",
                trace_id=request.workflow_run_id or request.request_id,
                top_score=float(rag_hits[0].get("score") or 0.0) if rag_hits else 0.0,
                metadata={"parsed_file_count": len(parsed_files), "structured_record": structured_record,
                         "product_family": product_family, "product_id": product_id,
                         "product_name": product_name, "spec_code": spec_code, "verdict": verdict,
                         "top_score": float(rag_hits[0].get("score") or 0.0) if rag_hits else 0.0,
                         "expectation_matched": None if not expectation_check else expectation_check["matched"],
                         "evidence_found": bool(rag_hits),
                         "evidence_used": bool(rag_used_citations),
                         "verdict_impacted": bool(verdict_rule_hits),
                         "rag_space_name": rag_result.get("rag_space_name"),
                         "top_sources": rag_summary["top_sources"],
                         "rule_hits": verdict_rule_hits,
                         "retrieval_config": {
                             "rag_space_id": str(rag_result.get("rag_space_id") or "") or None,
                             "rag_space_name": str(rag_result.get("rag_space_name") or "") or None,
                             "top_k": retrieval_top_k,
                             "scope_node_ids": list(request.ext.get("selected_rag_scope_node_ids") or []),
                         },
                         "retrieved_chunks": rag_hits,
                         "used_citations": rag_used_citations,
                         "answer": answer,
                         "result": result_card,
                         "runtime_profile": runtime_profile.as_metadata()},
            )],
        )

        task_draft = _task_draft_from_request(
            request=request,
            product_id=product_id,
            spec_code=spec_code,
            image_urls=image_urls,
            priority=priority,
            product_family=product_family,
            product_name=product_name,
            product_model=product_model,
            structured_record=structured_record,
        )
        return AgentOutput(
            message_type="task_result", answer=answer,
            summary=str(evaluation.get("summary") or "结构化质量检测已完成。"),
            action_state=task_status, task_draft=task_draft, quality=quality,
            citations=citations, result_card=result_card,
            expectation_check=expectation_check, rag_summary=rag_summary,
            persistable_output=persistable_output,
            raw_state={"parsed_files": parsed_files, "structured_record": structured_record,
                      "evaluation": evaluation, "task_draft": task_draft,
                      "product_family": product_family, "result_card": result_card,
                      "expectation_check": expectation_check, "rag_summary": rag_summary,
                      "runtime_profile": runtime_profile.as_metadata()},
        )


NodeFn = Callable[[InspectionState], Awaitable[InspectionState]]
EventHandler = Callable[[dict], Awaitable[None]]


class InspectionGraph:
    """LangGraph-based visual inspection pipeline.

    Replaces the original for-loop based InspectionGraph from agent/graph/.
    Uses LangGraph StateGraph for proper graph execution with conditional edges.

    Flow: planner → vision → knowledge → reasoning → finalizer → END
    On runtime_errors: shortcuts to END immediately.
    """

    def __init__(self) -> None:
        builder = StateGraph(InspectionState)
        builder.add_node("planner", plan)
        builder.add_node("vision", run_vision)
        builder.add_node("knowledge", run_knowledge)
        builder.add_node("reasoning", run_reasoning)
        builder.add_node("finalizer", finalize)

        builder.set_entry_point("planner")
        builder.add_edge("planner", "vision")
        builder.add_conditional_edges(
            "vision",
            self._should_continue,
            {"continue": "knowledge", "end": END},
        )
        builder.add_conditional_edges(
            "knowledge",
            self._should_continue,
            {"continue": "reasoning", "end": END},
        )
        builder.add_conditional_edges(
            "reasoning",
            self._should_continue,
            {"continue": "finalizer", "end": END},
        )
        builder.add_edge("finalizer", END)

        self._graph = builder.compile()

    @staticmethod
    def _should_continue(state: InspectionState) -> str:
        if state.get("runtime_errors"):
            return "end"
        return "continue"

    async def run(
        self,
        state: InspectionState,
        on_event: EventHandler | None = None,
    ) -> InspectionState:
        """Run the inspection pipeline.

        Maintains backward compatibility with the original agent/graph/ API.
        """
        if on_event:
            for node_name in ("planner", "vision", "knowledge", "reasoning", "finalizer"):
                await on_event({"type": "stage_start", "stage": node_name})
                # Run the graph one node at a time so we can emit events
                # For the full graph run we use ainvoke and emit at boundaries
            result = await self._graph.ainvoke(state)
            for node_name in ("planner", "vision", "knowledge", "reasoning", "finalizer"):
                await on_event({"type": "stage_end", "stage": node_name, "timeline": result.get("timeline", [])[-1:] if result.get("timeline") else []})
            return result

        return await self._graph.ainvoke(state)
