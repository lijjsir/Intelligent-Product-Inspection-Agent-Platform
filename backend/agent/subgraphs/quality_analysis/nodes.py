from __future__ import annotations

import json
from typing import Any

from agent.router.errors import AgentRuntimeError, make_agent_error


def _compact_json(value: Any, *, max_chars: int = 4000) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        text = str(value)
    return text if len(text) <= max_chars else f"{text[:max_chars]}...（已截断）"


def _build_quality_context(state: dict[str, Any]) -> str:
    request = state.get("request") if isinstance(state.get("request"), dict) else {}
    ext = request.get("ext") if isinstance(request.get("ext"), dict) else {}
    metadata = request.get("metadata") if isinstance(request.get("metadata"), dict) else {}
    return _compact_json(
        {
            "task": {
                "task_id": state.get("task_id") or ext.get("task_id") or metadata.get("task_id"),
                "product_id": state.get("product_id") or ext.get("product_id") or metadata.get("product_id") or request.get("product_id"),
                "spec_code": state.get("spec_code") or ext.get("spec_code") or metadata.get("spec_code") or request.get("spec_code"),
                "image_urls": state.get("image_urls") or ext.get("image_urls") or metadata.get("image_urls") or request.get("image_urls"),
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
                "summary": "缺少证据包，无法执行正式质检。",
            }

        if ext.get("evidence_packet_required"):
            source_count = int(evidence.get("source_count") or 0)
            if source_count <= 0:
                return {
                    "needs_user_input": True,
                    "status": "blocked",
                    "summary": "证据包为空，无法执行正式质检。请检查 RAG / 记忆 / 知识图谱配置。",
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
        prompt = f"请用中文回答用户问题：\n{query}"
    elif response_mode == "quality_qa":
        evidence_context = ""
        if state.get("evidence_packet"):
            evidence_context += f"\n证据包：{state['evidence_packet']}"
        if state.get("visual_inspection_result"):
            evidence_context += f"\n视觉检查结果：{state['visual_inspection_result']}"
        if state.get("lab_detection_result"):
            evidence_context += f"\n实验室检测结果：{state['lab_detection_result']}"
        prompt = (
            "请基于以下真实证据进行质量分析并回答用户问题。\n"
            "要求：只能引用输入中已经存在的数据；不得编造实测值、检测时间、检测人或不存在的标准条款。"
            "如果证据不足或证据与任务产品不一致，必须明确说明限制并建议人工复核。\n"
            f"用户问题：{query}{evidence_context}"
        )
    else:
        prompt = (
            "执行正式质检任务，但必须严格遵守真实数据约束。\n"
            "禁止编造任何实测值、尺寸、硬度、扭矩、材质成分、检测时间、检测人或合格结论。\n"
            "如果输入中没有真实检测值，或图片内容与任务产品/检测标准不一致，"
            "结论必须是需人工复核，并列出：已知事实、缺失数据、风险原因、下一步建议。\n"
            f"用户任务：{query}\n"
            f"真实上下文：{_build_quality_context(state)}"
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


async def standard_gate(state: dict[str, Any]) -> dict[str, Any]:
    response_mode = state.get("response_mode", "general_answer")
    if response_mode == "general_answer":
        return {"standard_evaluation": {"passed": True, "gate": "bypass"}}

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
    consumed_artifact_ids = list(state.get("consumed_artifact_ids") or [])

    source_count = int(evidence_packet.get("source_count") or 0)
    confidence = 0.5
    if source_count > 0:
        confidence += 0.2
    if visual_result:
        confidence += 0.15
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
    assessment = {
        "final_verdict": "manual_required" if response_mode == "inspection_execute" else "uncertain",
        "overall_score": round(confidence, 4),
        "risk_level": "medium" if response_mode == "inspection_execute" else "low",
        "risk_score": round(1.0 - confidence, 4),
        "evidence_used": consumed_artifact_ids,
        "consumed_artifact_ids": consumed_artifact_ids,
        "conflicts": list(evidence_packet.get("conflicts") or []),
        "limitations": [],
        "recommended_action": ["建议人工复核"] if response_mode == "inspection_execute" else [],
        "answer": answer,
        "confidence": confidence,
        "traceability_score": min(1.0, source_count / 3) if source_count else 0.0,
        "faithfulness_score": confidence,
        "physical_hallucination_score": 0.0 if source_count or visual_result or lab_result else 0.5,
        "candidate_extractable": candidate_extractable,
        "candidate_type": "inspection_pattern",
        "candidate_summary": (
            f"质量分析结论：{answer[:300]}"
            if candidate_extractable and answer
            else ""
        ),
        "candidate_reason": (
            "多个任务产物共同支持该质量判断，可供后续 Agent 复用"
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


async def maybe_persist_task_result(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("surface") != "quality_task":
        return {}

    try:
        from app.services.quality_result_materialization_service import QualityResultMaterializationService

        db_session = state.get("db_session")
        if db_session is None:
            raise make_agent_error(
                "INSPECTION_TASK_FAILED",
                message="正式质检任务缺少数据库会话，无法构建持久化输出。",
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
            message="正式质检持久化输出构建失败。",
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
            "summary": "需要用户补充信息",
            "answer": "缺少必要信息，请补充后再试。",
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
