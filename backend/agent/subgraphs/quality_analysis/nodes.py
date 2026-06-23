from __future__ import annotations

from typing import Any


async def context_assembler(state: dict[str, Any]) -> dict[str, Any]:
    manager_state = state.get("manager_state") or {}
    request = state.get("request") or {}

    artifacts = manager_state.get("artifacts") or state.get("artifacts") or []
    evidence_packet = None
    visual_result = None
    lab_result = None
    file_results = []

    for art in artifacts:
        art_type = art.get("type") or art.get("artifact_type", "")
        content = art.get("content") or {}
        if art_type == "evidence_packet":
            evidence_packet = content
        elif art_type == "visual_inspection_result":
            visual_result = content
        elif art_type == "lab_detection_result":
            lab_result = content
        elif art_type in ("file_summary", "file_answer", "paper_format_report"):
            file_results.append(content)

    return {
        "artifacts": artifacts,
        "evidence_packet": evidence_packet,
        "visual_inspection_result": visual_result,
        "lab_detection_result": lab_result,
        "file_results": file_results,
        "needs_user_input": False,
        "response_mode": "general_answer",
    }


async def validate_required_inputs(state: dict[str, Any]) -> dict[str, Any]:
    capability = state.get("capability", "quality.final_analyze")
    if capability == "quality.inspection.execute":
        evidence = state.get("evidence_packet")
        if evidence is None:
            return {"needs_user_input": True, "status": "blocked", "summary": "缺少证据包，无法执行正式质检。"}
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
        prompt = f"请基于以下证据进行质量分析并回答用户问题。\n用户问题：{query}{evidence_context}"
    else:
        prompt = f"执行正式质检任务：{query}"

    try:
        from agent.core.llm_client import LLMClient

        answer = await LLMClient.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        return {"llm_answer": answer or "", "llm_prompt": prompt, "status": "running"}
    except Exception as exc:
        return {"llm_answer": "", "llm_prompt": prompt, "status": "failed", "summary": str(exc)}


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


async def maybe_persist_task_result(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("surface") != "quality_task":
        return {}

    try:
        from app.services.quality_result_materialization_service import QualityResultMaterializationService

        db_session = state.get("db_session")
        if db_session is None:
            return {"persistable_output": None}

        service = QualityResultMaterializationService(db_session)
        persistable = await service.build_persistable_output(
            org_id=state.get("org_id", ""),
            workflow_run_id=state.get("workflow_run_id", ""),
            final_state=state,
            standard_evaluation=state.get("standard_evaluation") or {},
        )
        return {"persistable_output": persistable}
    except Exception:
        return {"persistable_output": None}


async def memory_candidate_hook(state: dict[str, Any]) -> dict[str, Any]:
    try:
        from agent.memory_governance.runtime import MemoryGovernanceRuntime

        db_session = state.get("db_session")
        if db_session is None:
            return {}

        assessment = state.get("final_assessment") or {}
        runtime = MemoryGovernanceRuntime(db_session)
        await runtime.submit_candidate_from_artifact(
            source_agent="quality_analysis",
            artifact=assessment,
            trace_id=state.get("workflow_run_id", ""),
        )
        return {}
    except Exception:
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

    assessment = {
        "final_verdict": "uncertain",
        "risk_level": "low",
        "evidence_used": [],
        "conflicts": [],
        "limitations": [],
        "recommended_action": [],
        "answer": state.get("answer", ""),
        "confidence": 0.8,
    }

    return {
        "status": state.get("status") or "success",
        "summary": state.get("summary") or "质量分析完成",
        "answer": state.get("answer", ""),
        "message_type": message_type,
        "confidence": 0.8,
        "final_assessment": assessment,
        "metadata": {"response_mode": response_mode},
    }
