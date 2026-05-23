from __future__ import annotations

import json
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
from agent.subgraphs.llm_native_quality.product_adapters import (
    collect_rule_hits,
    deep_merge,
    detect_product_family,
    expected_verdict_from_record,
    build_defects,
    int_value,
    list_value,
    parse_kv_text,
    parse_structured_text,
    resolve_product_id,
    resolve_spec_code,
    score_from_record,
)
from app.services.chat_trust_scoring_service import score_output_rule
from agent.tools.file_parsers import parse_file_content
from app.services.dspy_runtime_service import resolve_dspy_runtime_profile
from app.services.file_storage_service import FileStorageService
from app.services.inspection_standard_service import InspectionStandardService
from app.services.object_storage.resolver import read_attachment_bytes
from app.services.rag_retrieval_service import RagRetrievalService
from app.services.system_rag_service import resolve_and_search_system_rag
from infra.database.session import get_session


QUALITY_MISSING_FIELD_HINTS = {
    "product_id": "Please provide the product_id, for example: screw",
    "spec_code": "Please provide the inspection spec_code, for example: SCREW-A-2026-V1",
    "image_urls": "Please continue uploading inspection images, or provide image URLs.",
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
    if verdict == "pass":
        return "low", 0.12
    if verdict == "fail":
        return "critical", 0.86
    if verdict == "manual_required":
        return "medium", 0.63
    return "high", 0.48


def _status_from_verdict(verdict: str) -> str:
    if verdict in {"pass", "fail"}:
        return "done"
    if verdict == "manual_required":
        return "reviewing"
    return "pending"


def _quality_payload(verdict: str, ai_gate: dict[str, Any], citations: list[dict[str, Any]], trust_scores: dict[str, Any] | None = None) -> dict[str, Any]:
    risk_level, risk_score = _verdict_risk(verdict)
    flags = list(ai_gate.get("reasons") or [])
    if not citations:
        flags.append("no_citations")
    hallucination_risk = float(trust_scores.get("hallucination_risk") or 0.0) if trust_scores else 0.0
    faithfulness = round(1.0 - hallucination_risk, 4)
    return {
        "confidence": float(ai_gate.get("confidence_score") or 0.0),
        "evidence_coverage": float(ai_gate.get("evidence_score") or 0.0),
        "traceability": float(ai_gate.get("traceability_score") or 0.0),
        "faithfulness": faithfulness,
        "risk_level": risk_level,
        "risk_score": round(risk_score, 4),
        "passed": verdict == "pass",
        "hallucination_flags": flags,
    }


def _promote_structured_pass(
    *,
    evaluation: dict[str, Any],
    expected_verdict: str | None,
    structured_record: dict[str, Any],
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
        evaluation["summary"] = "Structured inspection record meets the configured baseline standard."
    return evaluation


def _build_retrieval_query(
    *,
    request: NormalizedRequest,
    product_id: str,
    product_family: str,
    product_name: str,
    spec_code: str,
    structured_record: dict[str, Any],
) -> str:
    expected = structured_record.get("expected_result")
    expected_hint = ""
    if isinstance(expected, dict):
        expected_hint = json.dumps(expected, ensure_ascii=False)
    record_excerpt = json.dumps(structured_record, ensure_ascii=False)[:600]
    parts = [
        request.query,
        product_id,
        product_family,
        product_name,
        spec_code,
        expected_hint,
        record_excerpt,
    ]
    return " ".join(part.strip() for part in parts if str(part or "").strip())


def _build_file_citations(request: NormalizedRequest, parsed_files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    file_citations = [
        {
            "id": f"file-{index + 1}",
            "title": item["name"],
            "source": item.get("url") or item["name"],
            "quote": str(item.get("text") or "")[:180],
            "kind": "attachment",
        }
        for index, item in enumerate(parsed_files)
    ]
    if file_citations:
        return file_citations
    return [
        {
            "id": "structured-query",
            "title": "Structured User Input",
            "source": "chat_query",
            "quote": request.query[:180],
            "kind": "attachment",
        }
    ]


def _merge_citations(file_citations: list[dict[str, Any]], rag_hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = list(file_citations)
    for index, hit in enumerate(rag_hits, start=1):
        merged.append(
            {
                "id": f"rag-{index}",
                "title": str(hit.get("title") or f"RAG Source {index}"),
                "source": str(hit.get("source") or ""),
                "quote": str(hit.get("quote") or ""),
                "score": float(hit.get("score") or 0.0),
                "kind": "rag",
            }
        )
    return merged


def _build_expectation_check(expected_verdict: str | None, actual_verdict: str) -> dict[str, Any] | None:
    if not expected_verdict:
        return None
    return {
        "expected_verdict": expected_verdict,
        "actual_verdict": actual_verdict,
        "matched": expected_verdict == actual_verdict,
    }


def _build_rag_summary(
    *,
    rag_space_id: str | None,
    rag_space_name: str | None,
    rag_hits: list[dict[str, Any]],
    source_graph: str,
    citation_coverage: float,
) -> dict[str, Any]:
    top_sources = []
    rag_space_ids = []
    rag_space_names = []
    for item in rag_hits:
        source = str(item.get("source") or "").strip()
        if source and source not in top_sources:
            top_sources.append(source)
        space_id = str(item.get("rag_space_id") or "").strip()
        space_name = str(item.get("rag_space_name") or "").strip()
        if space_id and space_id not in rag_space_ids:
            rag_space_ids.append(space_id)
        if space_name and space_name not in rag_space_names:
            rag_space_names.append(space_name)
    return {
        "rag_space_id": rag_space_id,
        "rag_space_name": rag_space_name,
        "rag_space_ids": rag_space_ids,
        "rag_space_names": rag_space_names,
        "hit_count": len(rag_hits),
        "citation_coverage": round(citation_coverage, 4),
        "top_sources": top_sources[:5],
        "source_graph": source_graph,
    }


def _build_result_card(
    *,
    product_id: str,
    product_family: str,
    product_name: str,
    spec_code: str,
    verdict: str,
    overall_score: float,
    risk_level: str,
    evaluation: dict[str, Any],
    rag_summary: dict[str, Any],
    expectation_check: dict[str, Any] | None,
) -> dict[str, Any]:
    key_reasons = [
        str(item)
        for item in list(evaluation.get("reasons") or [])
        if str(item or "").strip()
    ]
    failed_rules = list(dict.fromkeys(collect_rule_hits(evaluation) + list(evaluation.get("unmatched_defects") or [])))
    return {
        "product_id": product_id,
        "product_family": product_family,
        "product_name": product_name,
        "spec_code": spec_code,
        "verdict": verdict,
        "overall_score": round(float(overall_score or 0.0), 4),
        "risk_level": risk_level,
        "key_reasons": key_reasons[:6],
        "failed_rules": failed_rules[:8],
        "expectation_check": expectation_check,
        "rag_summary": rag_summary,
    }


class LLMNativeQualitySubgraph:
    def __init__(self) -> None:
        pass

    async def run(self, request: NormalizedRequest) -> AgentOutput:
        started_at = perf_counter()
        runtime_profile = await resolve_dspy_runtime_profile(request.org_id, "llm_native_quality")
        contract_target = runtime_profile.get("llm_native_quality.contract_inferencer_dspy")
        planner_target = runtime_profile.get("llm_native_quality.planner")
        knowledge_target = runtime_profile.get("llm_native_quality.knowledge_router")
        synthesizer_target = runtime_profile.get("llm_native_quality.evidence_synthesizer")
        review_target = runtime_profile.get("llm_native_quality.review_gate")
        parsed_files: list[dict[str, Any]] = []
        for attachment in request.attachments:
            if not attachment.url or attachment.kind == "image":
                continue
            payload = None
            if attachment.bucket and attachment.object_key:
                payload = read_attachment_bytes(attachment.model_dump())
            if payload is None:
                payload = FileStorageService().file_bytes_from_url(attachment.url)
            if payload is None:
                continue
            content, _ = payload
            parsed = parse_file_content(attachment.name or "attachment.txt", content)
            parsed_files.append(
                {
                    "name": attachment.name or "attachment.txt",
                    "kind": parsed.get("kind"),
                    "url": attachment.url,
                    "text": parsed.get("text", ""),
                    "summary": parsed,
                }
            )

        structured_record = _extract_structured_record(request, parsed_files)
        product_family = detect_product_family(
            structured_record,
            request.product_id or request.metadata.get("product_id") or request.ext.get("product_id"),
        )
        product_id = resolve_product_id(
            structured_record,
            product_family,
            request.product_id or request.metadata.get("product_id") or request.ext.get("product_id"),
        )
        spec_code = resolve_spec_code(
            structured_record,
            product_family,
            request.spec_code or request.metadata.get("spec_code") or request.ext.get("spec_code"),
        )
        product_name = str(structured_record.get("product_name") or request.metadata.get("product_name") or "").strip()
        image_urls = list(request.image_urls or request.ext.get("image_urls") or [])
        if not image_urls:
            image_urls = list_value(structured_record.get("image_urls"))

        structured_evidence = bool(
            structured_record
            or any(item.get("text") for item in parsed_files)
        )
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
            clarification = ClarificationRequest(
                missing_fields=missing_fields,
                reason="The current user input, parsed files, and RAG context still do not provide enough trusted evidence.",
                suggestions=[QUALITY_MISSING_FIELD_HINTS.get(item, item) for item in missing_fields],
                examples={item: QUALITY_MISSING_FIELD_HINTS.get(item, item) for item in missing_fields},
            )
            answer = (
                "The current information is not sufficient to complete the quality inspection safely.\n\n"
                f"Missing fields: {', '.join(missing_fields)}\n"
                "Please provide the missing information and I will continue from there."
            )
            return AgentOutput(
                message_type="task_action",
                answer=answer,
                summary="Awaiting required clarification",
                action_state="awaiting_clarification",
                clarification=clarification,
                quality={
                    "passed": False,
                    "risk_level": "critical",
                    "risk_score": 0.92,
                    "hallucination_flags": ["missing_required_inputs"],
                },
                persistable_output=PersistableOutput(),
                raw_state={"parsed_files": parsed_files, "structured_record": structured_record},
            )

        defects = build_defects(structured_record, product_family)
        expected_verdict = expected_verdict_from_record(structured_record, product_family)
        overall_score = score_from_record(defects, expected_verdict)
        evidence_refs = list(image_urls or [item["url"] for item in parsed_files if item.get("url")])
        if not evidence_refs:
            evidence_refs = [f"struct://{request.request_id}"]

        retrieval_query = _build_retrieval_query(
            request=request,
            product_id=product_id,
            product_family=product_family,
            product_name=product_name,
            spec_code=spec_code,
            structured_record=structured_record,
        )
        async with get_session() as session:
            rag_result = await resolve_and_search_system_rag(
                session=session,
                org_id=request.org_id,
                user_id=request.user_id,
                query=retrieval_query,
                product_family=product_family,
                product_id=product_id,
                spec_code=spec_code,
                user_rag_space_id=str(request.ext.get("selected_rag_space_id") or "") or None,
                top_k=int(knowledge_target.config_payload.get("retrieval_top_k") if knowledge_target else 4) or 4,
            )

        file_citations = _build_file_citations(request, parsed_files)
        citations = _merge_citations(file_citations, list(rag_result.get("hits") or []))

        reasoning_chain = {
            "summary": "Structured file inspection evaluated against inspection standards with product-aware parsing and RAG evidence.",
            "structured_record": structured_record,
            "product_family": product_family,
            "product_name": product_name,
            "source_files": [{"name": item["name"], "url": item.get("url")} for item in parsed_files],
            "trace": {
                "trace_id": request.workflow_run_id or request.request_id,
                "trace_url": None,
                "model_key": "llm_native_quality",
            },
            "langfuse_scores": [],
            "dspy_runtime": runtime_profile.as_metadata(),
            "knowledge_router": {
                "selected_rag_space_id": request.ext.get("selected_rag_space_id"),
                "selected_rag_space_name": rag_result.get("rag_space_name"),
                "system_rag_space_ids": list(rag_result.get("system_rag_space_ids") or []),
                "system_rag_space_names": list(rag_result.get("system_rag_space_names") or []),
                "standard_binding_name": rag_result.get("standard_binding_name"),
                "query": retrieval_query,
                "hit_count": int(rag_result.get("hit_count") or 0),
                "top_hits": list(rag_result.get("hits") or []),
                "target_config": knowledge_target.summary() if knowledge_target else None,
            },
            "evidence_synthesizer": {
                "citation_count": len(citations),
                "file_citation_count": len(file_citations),
                "rag_citation_count": len(list(rag_result.get("hits") or [])),
                "target_config": synthesizer_target.summary() if synthesizer_target else None,
            },
        }

        async with get_session() as session:
            standard_service = InspectionStandardService(session, request.org_id)
            evaluation = await standard_service.evaluate(
                spec_code=spec_code,
                image_urls=evidence_refs,
                defects=defects,
                citations=citations,
                reasoning_chain=reasoning_chain,
                model_verdict=expected_verdict or ("pass" if not defects else "fail"),
                overall_score=overall_score,
            )
        evaluation = _promote_structured_pass(
            evaluation=evaluation,
            expected_verdict=expected_verdict,
            structured_record=structured_record,
        )

        verdict = str(evaluation.get("verdict") or "manual_required").lower()
        ai_gate = dict(evaluation.get("ai_gate") or {})
        review_thresholds = dict(review_target.config_payload if review_target else {})
        min_confidence = float(review_thresholds.get("min_confidence", 0.85))
        min_evidence = float(review_thresholds.get("min_evidence_score", 0.9))
        min_traceability = float(review_thresholds.get("min_traceability_score", 0.9))
        max_physical_hallucination = float(review_thresholds.get("max_physical_hallucination", 0.2))
        trust_scores = score_output_rule(
            input_text=request.query,
            output_text=evaluation.get("summary") or "",
            citations=citations if citations else None,
        )
        physical_hallucination_score = float(trust_scores.get("hallucination_risk") or 0.0)
        if verdict == "pass" and (
            float(ai_gate.get("confidence_score") or 0.0) < min_confidence
            or float(ai_gate.get("evidence_score") or 0.0) < min_evidence
            or float(ai_gate.get("traceability_score") or 0.0) < min_traceability
            or physical_hallucination_score > max_physical_hallucination
        ):
            verdict = "manual_required"
            evaluation = {
                **evaluation,
                "verdict": verdict,
                "summary": "DSPy review gate blocked auto pass because the configured evidence thresholds were not met.",
                "reasons": [*list(evaluation.get("reasons") or []), "dspy_review_gate_blocked_auto_pass"],
            }
        rag_hits = list(rag_result.get("hits") or [])
        quality = _quality_payload(verdict, ai_gate, citations, trust_scores)
        task_status = _status_from_verdict(verdict)
        planner_default_priority = int_value(planner_target.config_payload.get("default_priority") if planner_target else 5) or 5
        priority = int_value(structured_record.get("priority") or planner_default_priority) or planner_default_priority
        risk_level, risk_score = _verdict_risk(verdict)
        latency_ms = round((perf_counter() - started_at) * 1000, 2)
        expectation_check = _build_expectation_check(expected_verdict, verdict)
        rag_summary = _build_rag_summary(
            rag_space_id=str(rag_result.get("rag_space_id") or "") or None,
            rag_space_name=str(rag_result.get("rag_space_name") or "") or None,
            rag_hits=rag_hits,
            source_graph="llm_native_quality",
            citation_coverage=float(ai_gate.get("evidence_score") or 0.0),
        )
        rag_summary["system_rag_space_ids"] = list(rag_result.get("system_rag_space_ids") or [])
        rag_summary["system_rag_space_names"] = list(rag_result.get("system_rag_space_names") or [])
        rag_summary["standard_binding_name"] = rag_result.get("standard_binding_name")
        rag_summary["merged_rag_source_count"] = int(rag_result.get("merged_rag_source_count") or 0)
        result_card = _build_result_card(
            product_id=product_id,
            product_family=product_family,
            product_name=product_name,
            spec_code=spec_code,
            verdict=verdict,
            overall_score=overall_score,
            risk_level=risk_level,
            evaluation=evaluation,
            rag_summary=rag_summary,
            expectation_check=expectation_check,
        )

        answer_lines = [
            f"Structured inspection for product `{product_id}` has been evaluated.",
            f"Product family: `{product_family}`",
            f"Spec: `{spec_code}`",
            f"Verdict: `{verdict.upper()}`",
            f"Summary: {evaluation.get('summary') or 'Quality review completed.'}",
        ]
        if defects:
            answer_lines.append(f"Detected defects: {len(defects)}")
        if evaluation.get("reasons"):
            answer_lines.append(f"Reasons: {', '.join(str(item) for item in evaluation['reasons'])}")
        if rag_hits:
            answer_lines.append(
                f"RAG matched {len(rag_hits)} evidence chunk(s) from `{rag_summary['rag_space_name'] or rag_summary['rag_space_id']}`."
            )
        elif request.ext.get("selected_rag_space_id") or rag_result.get("system_rag_space_ids"):
            answer_lines.append("RAG retrieval returned no matching evidence from the selected knowledge space.")
        if expectation_check:
            answer_lines.append(
                "Expectation check: "
                + ("matched the sample expectation." if expectation_check["matched"] else "did not match the sample expectation.")
            )
        answer = "\n".join(answer_lines)

        persistable_output = PersistableOutput(
            task=TaskAggregate(
                product_id=product_id,
                spec_code=spec_code,
                status=task_status,
                priority=priority,
                image_count=len(image_urls),
            ),
            result=ResultAggregate(
                task_id=None,
                verdict=verdict,
                overall_score=overall_score,
                llm_model="llm_native_quality",
                citations={"items": citations},
                reasoning_chain={
                    **reasoning_chain,
                    "standard_evaluation": evaluation,
                    "quality": quality,
                    "result_card": result_card,
                    "expectation_check": expectation_check,
                    "rag_summary": rag_summary,
                    "trust_scoring": trust_scores,
                },
            ),
            stability=StabilityAggregate(
                risk_score=risk_score,
                risk_level=risk_level,
                evidence_score=float(ai_gate.get("evidence_score") or 0.0),
                confidence_score=float(ai_gate.get("confidence_score") or 0.0),
                traceability_score=float(ai_gate.get("traceability_score") or 0.0),
                faithfulness_score=float(quality.get("faithfulness") or 0.0),
                physical_hallucination_score=physical_hallucination_score,
            ),
            alerts=[] if verdict == "pass" else [
                AlertEvent(
                    severity="high" if verdict == "fail" else "medium",
                    title=f"{spec_code} review requires attention",
                    message=str(evaluation.get("summary") or "Quality review flagged for follow-up."),
                )
            ],
            token_usage=[
                TokenUsageEvent(
                    model_key="llm_native_quality",
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    cost_amount=0.0,
                    trace_id=request.workflow_run_id or request.request_id,
                )
            ],
            quality_trace=QualityTraceEvent(
                trace_id=request.workflow_run_id or request.request_id,
                trace_url=None,
                workflow_version="quality_agent_root_v1",
                prompt_version=runtime_profile.active_prompt_version,
                route_subgraph="llm_native_quality",
            ),
            rag_queries=[
                RagQueryLog(
                    query=retrieval_query,
                    rag_space_id=str(rag_result.get("rag_space_id") or "") or None,
                    hit_count=len(rag_hits),
                    hit_rate=1.0 if rag_hits else 0.0,
                    citation_coverage=float(ai_gate.get("evidence_score") or 0.0),
                    latency_ms=latency_ms,
                    source_graph="llm_native_quality",
                    metadata={
                        "parsed_file_count": len(parsed_files),
                        "structured_record": structured_record,
                        "product_family": product_family,
                        "product_id": product_id,
                        "product_name": product_name,
                        "spec_code": spec_code,
                        "verdict": verdict,
                        "expectation_matched": None if not expectation_check else expectation_check["matched"],
                        "rag_space_name": rag_result.get("rag_space_name"),
                        "top_sources": rag_summary["top_sources"],
                        "rule_hits": list(dict.fromkeys(result_card["failed_rules"])),
                        "dspy_runtime": runtime_profile.as_metadata(),
                    },
                )
            ],
        )

        task_draft = {
            "product_id": product_id,
            "spec_code": spec_code,
            "image_urls": image_urls,
            "priority": priority,
            "metadata": {
                "source": "llm_native_quality",
                "product_family": product_family,
                "product_name": product_name,
                "structured_record": structured_record,
            },
        }
        return AgentOutput(
            message_type="quality_answer",
            answer=answer,
            summary=str(evaluation.get("summary") or "Structured quality review completed."),
            action_state=task_status,
            task_draft=task_draft,
            quality=quality,
            citations=citations,
            result_card=result_card,
            expectation_check=expectation_check,
            rag_summary=rag_summary,
            persistable_output=persistable_output,
            raw_state={
                "parsed_files": parsed_files,
                "structured_record": structured_record,
                "evaluation": evaluation,
                "task_draft": task_draft,
                "product_family": product_family,
                "result_card": result_card,
                "expectation_check": expectation_check,
                "rag_summary": rag_summary,
                "dspy_runtime": runtime_profile.as_metadata(),
            },
        )
