from __future__ import annotations

import json
from typing import Any

from agent.router.errors import AgentRuntimeError, make_agent_error
from agent.vision.heuristic_detector import extract_defects


def _compact_json(value: Any, *, max_chars: int = 4000) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        text = str(value)
    return text if len(text) <= max_chars else f"{text[:max_chars]}...(truncated)"


def _summarize_image_ref(value: Any) -> dict[str, Any]:
    url = str(value or "").strip()
    if not url:
        return {}
    if url.startswith("data:"):
        header = url.split(",", 1)[0]
        mime = header[5:].split(";", 1)[0] if header.startswith("data:") else ""
        return {"kind": "data_url", "mime": mime or None, "length": len(url), "redacted": True}
    return {"kind": "url", "url": url if len(url) <= 300 else f"{url[:300]}...", "length": len(url)}


def _collect_image_urls(state: dict[str, Any]) -> list[str]:
    request = state.get("request") if isinstance(state.get("request"), dict) else {}
    ext = request.get("ext") if isinstance(request.get("ext"), dict) else {}
    metadata = request.get("metadata") if isinstance(request.get("metadata"), dict) else {}
    raw = state.get("image_urls") or ext.get("image_urls") or metadata.get("image_urls") or request.get("image_urls") or []
    urls = [str(item).strip() for item in list(raw or []) if str(item or "").strip()]
    if urls:
        return urls
    attachments = state.get("attachments") or request.get("attachments") or ext.get("attachments") or metadata.get("attachments") or []
    for item in list(attachments or []):
        if not isinstance(item, dict):
            continue
        if str(item.get("kind") or "").lower() != "image":
            continue
        url = str(item.get("url") or "").strip()
        if url:
            urls.append(url)
    return urls


def _build_quality_context(state: dict[str, Any]) -> str:
    request = state.get("request") if isinstance(state.get("request"), dict) else {}
    ext = request.get("ext") if isinstance(request.get("ext"), dict) else {}
    metadata = request.get("metadata") if isinstance(request.get("metadata"), dict) else {}
    image_urls = _collect_image_urls(state)
    return _compact_json(
        {
            "task": {
                "task_id": state.get("task_id") or ext.get("task_id") or metadata.get("task_id"),
                "product_id": state.get("product_id") or ext.get("product_id") or metadata.get("product_id") or request.get("product_id"),
                "spec_code": state.get("spec_code") or ext.get("spec_code") or metadata.get("spec_code") or request.get("spec_code"),
                "image_count": len(image_urls),
                "image_refs": [_summarize_image_ref(item) for item in image_urls],
            },
            "evidence_packet": state.get("evidence_packet"),
            "visual_inspection_result": state.get("visual_inspection_result"),
            "lab_detection_result": state.get("lab_detection_result"),
            "file_results": state.get("file_results"),
        }
    )


async def context_assembler(state: dict[str, Any]) -> dict[str, Any]:
    manager_state = state.get("manager_state") or {}
    blackboard = (
        state.get("blackboard_snapshot")
        or manager_state.get("blackboard_snapshot")
        or state.get("blackboard_context")
        or manager_state.get("blackboard_context")
        or {}
    )

    local_artifacts = [
        item for item in (manager_state.get("artifacts") or state.get("artifacts") or [])
        if isinstance(item, dict)
    ]
    blackboard_artifacts = [
        item for item in (blackboard.get("artifacts") or [])
        if isinstance(item, dict)
    ]
    artifacts_by_id: dict[str, dict[str, Any]] = {}
    anonymous: list[dict[str, Any]] = []
    for art in [*blackboard_artifacts, *local_artifacts]:
        artifact_id = str(art.get("artifact_id") or "")
        if artifact_id:
            artifacts_by_id[artifact_id] = art
        elif art not in anonymous:
            anonymous.append(art)
    artifacts = [*artifacts_by_id.values(), *anonymous]
    evidence_packet = None
    visual_result = None
    lab_result = None
    file_results = []
    consumed_artifact_ids = []

    for art in artifacts:
        art_type = art.get("type") or art.get("artifact_type", "")
        content = art.get("content") or {}
        relevant = False
        if art_type == "evidence_packet":
            evidence_packet = content
            relevant = True
        elif art_type == "visual_inspection_result":
            visual_result = content
            relevant = True
        elif art_type == "lab_detection_result":
            lab_result = content
            relevant = True
        elif art_type in ("file_summary", "file_answer", "paper_format_report"):
            file_results.append(content)
            relevant = True
        artifact_id = str(art.get("artifact_id") or "")
        if relevant and artifact_id and artifact_id not in consumed_artifact_ids:
            consumed_artifact_ids.append(artifact_id)

    return {
        "artifacts": artifacts,
        "evidence_packet": evidence_packet,
        "visual_inspection_result": visual_result,
        "lab_detection_result": lab_result,
        "file_results": file_results,
        "consumed_artifact_ids": consumed_artifact_ids,
        "needs_user_input": False,
        "response_mode": "general_answer",
    }


async def validate_required_inputs(state: dict[str, Any]) -> dict[str, Any]:
    capability = state.get("capability", "quality.final_analyze")
    request = state.get("request") or {}
    ext = request.get("ext") or {}

    if capability == "quality.inspection.execute":
        evidence = state.get("evidence_packet")
        if evidence is None:
            return {
                "needs_user_input": True,
                "status": "blocked",
                "summary": "missing evidence packet for formal inspection",
            }

        if ext.get("evidence_packet_required"):
            source_count = int(evidence.get("source_count") or 0)
            if source_count <= 0:
                return {
                    "needs_user_input": True,
                    "status": "blocked",
                    "summary": "empty evidence packet for formal inspection",
                }

        if _collect_image_urls(state) and not state.get("visual_inspection_result"):
            return {
                "needs_user_input": True,
                "status": "blocked",
                "summary": "missing visual inspection result for image task",
            }

    return {}


async def choose_response_mode(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("needs_user_input"):
        return {"response_mode": "blocked"}

    capability = state.get("capability", "quality.final_analyze")
    if capability == "quality.inspection.execute":
        return {"response_mode": "inspection_execute"}

    has_evidence = bool(state.get("evidence_packet"))
    has_visual = bool(state.get("visual_inspection_result"))
    has_lab = bool(state.get("lab_detection_result"))

    if has_evidence or has_visual or has_lab:
        return {"response_mode": "quality_qa"}
    return {"response_mode": "general_answer"}


async def llm_quality_reasoning(state: dict[str, Any]) -> dict[str, Any]:
    response_mode = state.get("response_mode", "general_answer")
    query = state.get("query", "")

    if response_mode == "general_answer":
        prompt = f"请用中文回答用户。\n用户问题：\n{query}"
    elif response_mode == "quality_qa":
        evidence_context: list[str] = []
        if state.get("evidence_packet"):
            evidence_context.append(f"evidence_packet: {state['evidence_packet']}")
        if state.get("visual_inspection_result"):
            evidence_context.append(f"visual_inspection_result: {state['visual_inspection_result']}")
        if state.get("lab_detection_result"):
            evidence_context.append(f"lab_detection_result: {state['lab_detection_result']}")
        prompt = (
            "请只基于下列证据完成质量分析，全程只用中文输出，不要输出英文标题或英文段落。"
            "不得编造测量值、检测时间、检测员姓名或标准条款。"
            "如果证据不足、证据与产品/标准不一致，请明确说明局限，并建议进入人工复核。\n"
            f"用户问题：{query}\n"
            f"证据上下文：\n{chr(10).join(evidence_context)}"
        )
    else:
        prompt = (
            "请执行正式质量检测，并严格遵守证据约束。全程只用中文输出，不要输出英文标题或英文段落。"
            "不得编造测量值、尺寸、硬度、扭矩、材料成分、检测时间、检测员姓名或合格/不合格结论。"
            "如果真实证据不足，或图片、产品、标准之间不一致，请说明局限并建议人工复核。"
            "输出 Markdown 报告，必须包含这些中文章节："
            "# 正式质检报告、## 检测结论、## 证据依据、## 图像观察、## 标准校验、## 局限与建议。\n"
            f"任务：{query}\n"
            f"证据上下文：{_build_quality_context(state)}"
        )

    from agent.subgraphs.common.llm_runtime import run_llm_chat

    answer, llm_meta = await run_llm_chat(
        state=state,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        observation_name="quality_analysis.reasoning",
        source="quality_analysis.llm_quality_reasoning",
    )

    return {
        "llm_answer": answer,
        "llm_prompt": prompt,
        "llm_meta": llm_meta,
    }


def _evidence_citations(evidence_packet: Any) -> list[dict[str, Any]]:
    if not isinstance(evidence_packet, dict):
        return []
    citations: list[dict[str, Any]] = []
    direct = evidence_packet.get("citations")
    if isinstance(direct, list):
        citations.extend([dict(item) for item in direct if isinstance(item, dict)])
    sources = evidence_packet.get("sources")
    if isinstance(sources, dict):
        for source in sources.values():
            if not isinstance(source, dict):
                continue
            for key in ("items", "hits", "paths"):
                values = source.get(key)
                if isinstance(values, list):
                    citations.extend([dict(item) for item in values if isinstance(item, dict)])
    return citations


def _visual_confidence(visual_result: dict[str, Any], *, defects: list[dict[str, Any]]) -> float:
    try:
        confidence = float(visual_result.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence > 1:
        confidence = confidence / 100.0
    if confidence > 0:
        return round(max(0.05, min(confidence, 0.98)), 4)
    if defects:
        return round(max(float(item.get("confidence") or 0.0) for item in defects), 4)
    if visual_result:
        return 0.9
    return 0.5


def _visual_model_verdict(visual_result: dict[str, Any], *, defects: list[dict[str, Any]], has_images: bool) -> str:
    if not has_images:
        return "uncertain"
    if not visual_result:
        return "manual_required"
    if visual_result.get("product_match") is False:
        return "fail"
    if bool(visual_result.get("requires_recheck")):
        return "manual_required"
    risk = str(visual_result.get("risk") or "").strip().lower()
    if defects:
        return "fail" if risk in {"high", "critical", "fail", "failed"} else "manual_required"
    if visual_result.get("possible_defects") or (visual_result.get("model_result") or {}).get("possible_defects"):
        return "manual_required"
    status = str(visual_result.get("status") or "").strip().lower()
    if status in {"failed", "blocked"}:
        return "manual_required"
    return "pass"


async def standard_gate(state: dict[str, Any]) -> dict[str, Any]:
    response_mode = state.get("response_mode", "general_answer")
    if response_mode == "general_answer":
        return {"standard_evaluation": {"passed": True, "gate": "bypass"}}

    if response_mode == "inspection_execute":
        request = state.get("request") if isinstance(state.get("request"), dict) else {}
        ext = request.get("ext") if isinstance(request.get("ext"), dict) else {}
        metadata = request.get("metadata") if isinstance(request.get("metadata"), dict) else {}
        spec_code = str(
            state.get("spec_code")
            or ext.get("spec_code")
            or metadata.get("spec_code")
            or request.get("spec_code")
            or ""
        ).strip()
        image_urls = _collect_image_urls(state)
        image_count = len(image_urls)
        visual_result = state.get("visual_inspection_result") or {}
        defects = extract_defects(visual_result, image_count=image_count)
        confidence = _visual_confidence(visual_result, defects=defects)
        model_verdict = _visual_model_verdict(visual_result, defects=defects, has_images=bool(image_urls))
        reasoning_chain = {
            "visual_inspection_result": visual_result,
            "evidence_packet": state.get("evidence_packet"),
            "llm_answer": state.get("llm_answer"),
        }
        db_session = state.get("db_session")
        if db_session is not None and spec_code:
            try:
                from app.services.inspection_standard_service import InspectionStandardService

                evaluation = await InspectionStandardService(
                    db_session,
                    str(state.get("org_id") or ""),
                ).evaluate(
                    spec_code=spec_code,
                    image_urls=image_urls,
                    defects=defects,
                    citations=_evidence_citations(state.get("evidence_packet")),
                    reasoning_chain=reasoning_chain,
                    model_verdict=model_verdict,
                    overall_score=confidence,
                )
                return {"standard_evaluation": evaluation}
            except AgentRuntimeError:
                raise
            except Exception as exc:
                return {
                    "standard_evaluation": {
                        "passed": False,
                        "gate": "inspection_standard",
                        "verdict": "manual_required",
                        "summary": f"inspection standard evaluation failed: {exc}",
                        "reasons": ["standard_evaluation_failed"],
                        "ai_gate": {
                            "confidence_score": confidence,
                            "evidence_score": 0.0,
                            "traceability_score": 0.0,
                            "reasons": ["standard_evaluation_failed"],
                        },
                    }
                }
        return {
            "standard_evaluation": {
                "passed": model_verdict == "pass",
                "gate": "visual_fallback",
                "verdict": model_verdict,
                "summary": (
                    str(visual_result.get("product_mismatch_reason") or visual_result.get("summary") or "")
                    if visual_result.get("product_match") is False
                    else str(visual_result.get("summary") or "")
                ),
                "reasons": (
                    ["product_mismatch"]
                    if visual_result.get("product_match") is False
                    else ([] if model_verdict == "pass" else ["visual_result_requires_review"])
                ),
                "ai_gate": {
                    "confidence_score": confidence,
                    "evidence_score": 1.0 if not defects else 0.0,
                    "traceability_score": 0.6 if visual_result else 0.0,
                    "reasons": (
                        ["product_mismatch"]
                        if visual_result.get("product_match") is False
                        else ([] if model_verdict == "pass" else ["visual_result_requires_review"])
                    ),
                },
            }
        }

    answer = state.get("llm_answer", "")
    return {
        "standard_evaluation": {
            "passed": bool(answer),
            "gate": "llm_only",
            "has_answer": bool(answer),
        }
    }


async def build_report(state: dict[str, Any]) -> dict[str, Any]:
    response_mode = state.get("response_mode", "general_answer")
    answer = state.get("llm_answer", "")
    evaluation = state.get("standard_evaluation") or {}

    report_parts = [answer] if answer else []

    if response_mode == "quality_qa":
        if state.get("evidence_packet"):
            report_parts.append(f"\n\n---\n证据来源数：{state['evidence_packet'].get('source_count', 0)}")
    elif response_mode == "inspection_execute":
        report_parts.insert(0, "# 正式质检报告\n")

    return {"report": "\n".join(report_parts), "answer": answer}


async def build_final_assessment(state: dict[str, Any]) -> dict[str, Any]:
    """Generate final_assessment BEFORE persistence, not after."""
    response_mode = state.get("response_mode", "general_answer")
    answer = state.get("answer") or state.get("llm_answer") or ""

    evidence_packet = state.get("evidence_packet") or {}
    visual_result = state.get("visual_inspection_result") or {}
    lab_result = state.get("lab_detection_result") or {}
    standard_evaluation = state.get("standard_evaluation") or {}
    consumed_artifact_ids = list(state.get("consumed_artifact_ids") or [])

    source_count = int(evidence_packet.get("source_count") or 0)
    defects = extract_defects(visual_result, image_count=len(_collect_image_urls(state)))
    confidence = 0.5
    if source_count > 0:
        confidence += 0.2
    if visual_result:
        confidence = max(confidence + 0.15, _visual_confidence(visual_result, defects=defects))
    if lab_result:
        confidence += 0.15
    confidence = min(confidence, 0.95)

    candidate_extractable = (
        response_mode in {"quality_qa", "inspection_execute"}
        and len(consumed_artifact_ids) >= 2
        and confidence >= 0.70
    )
    request = state.get("request") or {}
    request_ext = request.get("ext") or {}
    request_metadata = request.get("metadata") or {}
    product_line = (
        request_ext.get("product_line")
        or request_metadata.get("product_line")
        or request.get("product_id")
    )
    final_verdict = "uncertain"
    if response_mode == "inspection_execute":
        final_verdict = str(
            standard_evaluation.get("verdict")
            or _visual_model_verdict(visual_result, defects=defects, has_images=bool(_collect_image_urls(state)))
        ).lower()
        if final_verdict not in {"pass", "fail", "uncertain", "manual_required"}:
            final_verdict = "manual_required"
    risk_score = _assessment_risk_score(
        final_verdict,
        confidence,
        defects=defects,
        standard_evaluation=standard_evaluation,
    )
    assessment = {
        "final_verdict": final_verdict,
        "overall_score": round(confidence, 4),
        "risk_level": _assessment_risk_level(final_verdict, risk_score),
        "risk_score": risk_score,
        "evidence_used": consumed_artifact_ids,
        "consumed_artifact_ids": consumed_artifact_ids,
        "conflicts": list(evidence_packet.get("conflicts") or []),
        "limitations": list(standard_evaluation.get("reasons") or []),
        "recommended_action": ["建议人工复核"] if final_verdict == "manual_required" else [],
        "answer": answer,
        "confidence": confidence,
        "traceability_score": float(
            (standard_evaluation.get("ai_gate") or {}).get("traceability_score")
            or (min(1.0, source_count / 3) if source_count else (0.6 if visual_result else 0.0))
        ),
        "faithfulness_score": confidence,
        "physical_hallucination_score": 0.0 if source_count or visual_result or lab_result else 0.5,
        "candidate_extractable": candidate_extractable,
        "candidate_type": "inspection_pattern",
        "candidate_summary": (
            f"quality analysis conclusion: {answer[:300]}"
            if candidate_extractable and answer
            else ""
        ),
        "candidate_reason": (
            "multiple task artifacts support this quality judgement for future agent reuse"
            if candidate_extractable
            else ""
        ),
        "share_value_score": round(confidence, 4) if candidate_extractable else 0.0,
        "target_agents": ["vision", "lab_detection", "quality_analysis"],
        "product_line": product_line,
    }
    return {
        "final_assessment": assessment,
        "candidate_extractable": candidate_extractable,
    }


def _assessment_risk_score(
    final_verdict: str,
    confidence: float,
    *,
    defects: list[dict[str, Any]],
    standard_evaluation: dict[str, Any],
) -> float:
    if final_verdict == "pass":
        return round(max(0.0, min(0.25, 1.0 - confidence)), 4)
    if final_verdict == "fail":
        defect_confidence = max([float(item.get("confidence") or 0.0) for item in defects] or [confidence])
        return round(max(0.75, min(1.0, defect_confidence)), 4)
    reasons = list(standard_evaluation.get("reasons") or [])
    gate_reasons = list((standard_evaluation.get("ai_gate") or {}).get("reasons") or [])
    if "standard_evaluation_failed" in reasons or gate_reasons:
        return 0.85
    return round(max(0.45, min(0.85, 1.0 - (confidence * 0.5))), 4)


def _assessment_risk_level(final_verdict: str, risk_score: float) -> str:
    if final_verdict == "pass":
        return "low"
    if final_verdict == "fail":
        return "critical" if risk_score >= 0.85 else "high"
    if risk_score >= 0.75:
        return "high"
    return "medium"


async def maybe_persist_task_result(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("surface") != "quality_task":
        return {}

    try:
        from app.services.quality_result_materialization_service import QualityResultMaterializationService

        db_session = state.get("db_session")
        if db_session is None:
            raise make_agent_error(
                "INSPECTION_TASK_FAILED",
                message="formal inspection task is missing db_session; cannot build persistable output",
                detail={
                    "stage": "maybe_persist_task_result",
                    "missing": ["db_session"],
                    "workflow_run_id": state.get("workflow_run_id"),
                },
                source="quality_analysis.persist_result",
                retryable=True,
            )

        service = QualityResultMaterializationService(db_session)
        persistable = await service.build_persistable_output(
            org_id=state.get("org_id", ""),
            workflow_run_id=state.get("workflow_run_id", ""),
            final_state=state,
            standard_evaluation=state.get("standard_evaluation") or {},
        )

        # Ensure PersistableOutput is serialized to dict
        if hasattr(persistable, "model_dump"):
            persistable = persistable.model_dump(mode="json")

        return {"persistable_output": persistable}
    except AgentRuntimeError:
        raise
    except Exception as exc:
        raise make_agent_error(
            "INSPECTION_TASK_FAILED",
            message="failed to build formal inspection persistable output",
            detail={
                "stage": "maybe_persist_task_result",
                "workflow_run_id": state.get("workflow_run_id"),
            },
            debug={"raw_error": str(exc), "error_type": exc.__class__.__name__},
            source="quality_analysis.persist_result",
            cause=exc,
        ) from exc


async def memory_candidate_hook(state: dict[str, Any]) -> dict[str, Any]:
    # Candidate extraction is orchestrator-owned and runs after the completed
    # artifact has been committed to the task blackboard.
    return {}


async def finalize_response(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("needs_user_input"):
        return {
            "status": "blocked",
            "summary": "user input required",
            "answer": "missing required information; please provide it and try again",
            "message_type": "error",
            "confidence": 0.0,
        }

    response_mode = state.get("response_mode", "general_answer")
    message_type = "quality_answer"
    if response_mode == "inspection_execute":
        message_type = "task_result"

    # Use already-built final_assessment from build_final_assessment node
    assessment = state.get("final_assessment") or {}

    return {
        "status": "success",
        "summary": state.get("summary") or "质量分析完成",
        "answer": state.get("answer", ""),
        "message_type": message_type,
        "confidence": assessment.get("confidence", 0.8),
        "final_assessment": assessment,
        "metadata": {"response_mode": response_mode},
    }
