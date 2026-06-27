from __future__ import annotations

from typing import Any

from langgraph.runtime import Runtime

from agent.router.errors import make_agent_error
from agent.subgraphs.vision_inspection.state import VisionInspectionContext
from agent.vision.heuristic_detector import extract_defects


async def input_adapter(state: dict[str, Any]) -> dict[str, Any]:
    """Validate input: ensure at least one image attachment exists."""
    attachments = list(state.get("attachments") or [])
    images = [item for item in attachments if str(item.get("kind") or "").lower() == "image"]

    if not images:
        raise make_agent_error(
            "VISION_INSPECTION_FAILED",
            message="视觉检验需要至少一张图片。",
            detail={"attachment_count": len(attachments)},
            source="vision.input_adapter",
            retryable=False,
        )

    return {
        **state,
        "image_attachments": images,
    }


async def legacy_vision_understanding_node(
    state: dict[str, Any],
    runtime: Runtime[VisionInspectionContext],
) -> dict[str, Any]:
    """Phase-1 compatibility node: wraps old VisionUnderstandingHandler as a formal graph node."""
    try:
        from agent.router.capabilities.vision_handler import VisionUnderstandingHandler
        from agent.router.contracts import AgentPlanStep, CapabilityContext
        from agent.router.manager_state import ManagerState
        from agent.contracts.quality_contracts import NormalizedRequest

        # Reconstruct objects from state dicts for the handler
        request_data = state.get("request") or {}
        manager_data = state.get("manager_state") or {}
        step_data = state.get("step") or {}

        request = NormalizedRequest(**request_data) if request_data else NormalizedRequest(
            request_kind="chat",
            query=state.get("query") or "",
            org_id=state.get("org_id") or "",
            user_id=state.get("user_id") or "",
            attachments=state.get("image_attachments") or [],
        )
        manager_state = ManagerState(**manager_data) if manager_data else ManagerState()

        step = AgentPlanStep(**step_data) if step_data else AgentPlanStep(
            capability="vision.inspect",
            owner_agent="vision",
        )
        # Use image.understanding sub-capability for the handler call
        vision_step = step.model_copy(update={"capability": "image.understanding", "operation": "understand"})

        handler = VisionUnderstandingHandler()
        result = await handler.run(
            CapabilityContext(
                step=vision_step,
                state=manager_state,
                request=request,
                db_session=runtime.context.db_session,
            )
        )
        # Keep graph state JSON-safe for checkpointing and transport.
        if isinstance(result, (tuple, list)) and len(result) >= 1:
            obs, artifacts = result[0], result[1] if len(result) > 1 else []
            if hasattr(obs, "model_dump"):
                obs_dict = obs.model_dump(mode="json", fallback=str)
            elif isinstance(obs, dict):
                obs_dict = dict(obs)
            else:
                obs_dict = {"status": "success", "summary": str(obs)}
            art_dicts = []
            for a in (artifacts if isinstance(artifacts, list) else [artifacts]):
                if hasattr(a, "model_dump"):
                    art_dicts.append(a.model_dump(mode="json", fallback=str))
                elif isinstance(a, dict):
                    art_dicts.append(a)
            result = [obs_dict, art_dicts]
        return {
            **state,
            "legacy_result": result,
        }
    except Exception as exc:
        raise make_agent_error(
            "VISION_INSPECTION_FAILED",
            message=f"视觉模型执行失败：{exc}",
            detail={"stage": "legacy_vision_understanding_node"},
            debug={
                "raw_error": str(exc),
                "error_type": exc.__class__.__name__,
            },
            source="vision.legacy_node",
            cause=exc,
        ) from exc


async def normalize_visual_result(state: dict[str, Any]) -> dict[str, Any]:
    """Normalize the legacy handler output into standard visual_inspection_result shape."""
    legacy_result = state.get("legacy_result")

    # VisionUnderstandingHandler.run() returns (observation, artifacts)
    if isinstance(legacy_result, (tuple, list)) and len(legacy_result) >= 1:
        obs = legacy_result[0]
        artifacts = legacy_result[1] if len(legacy_result) > 1 else []
        if hasattr(obs, "model_dump"):
            obs_dict = obs.model_dump(mode="json", fallback=str)
        elif isinstance(obs, dict):
            obs_dict = obs
        else:
            obs_dict = {"status": "success", "summary": str(obs)}
    elif isinstance(legacy_result, dict):
        obs_dict = legacy_result
        artifacts = []
    else:
        obs_dict = {"status": "success", "summary": str(legacy_result)}
        artifacts = []

    legacy_content = {}
    if artifacts:
        image_artifact = artifacts[0]
        if hasattr(image_artifact, "content"):
            legacy_content = dict(image_artifact.content or {})
        elif isinstance(image_artifact, dict):
            legacy_content = dict(image_artifact.get("content") or {})

    image_count = len(state.get("image_attachments") or [])
    model_result = dict(legacy_content.get("model_result") or {})
    model_summary = str(
        model_result.get("summary")
        or legacy_content.get("summary")
        or obs_dict.get("summary")
        or ""
    ).strip()
    defects = (
        extract_defects(legacy_content, image_count=image_count)
        or extract_defects(model_result, image_count=image_count)
    )

    visual_result = {
        "status": obs_dict.get("status", "success"),
        "summary": model_summary,
        "answer": str(legacy_content.get("answer") or model_summary),
        "image_count": int(legacy_content.get("image_count") or image_count),
        "defects": defects,
        "objects": model_result.get("objects") or legacy_content.get("objects") or [],
        "expected_product": (
            model_result.get("expected_product")
            or legacy_content.get("expected_product")
            or (state.get("request") or {}).get("product_id")
            or ((state.get("request") or {}).get("ext") or {}).get("product_id")
            or None
        ),
        "observed_product": model_result.get("observed_product") or legacy_content.get("observed_product") or None,
        "product_match": (
            model_result.get("product_match")
            if model_result.get("product_match") is not None
            else legacy_content.get("product_match")
        ),
        "product_mismatch_reason": (
            model_result.get("product_mismatch_reason")
            or legacy_content.get("product_mismatch_reason")
            or ""
        ),
        "possible_defects": (
            model_result.get("possible_defects")
            or legacy_content.get("possible_defects")
            or []
        ),
        "risk": model_result.get("risk") or legacy_content.get("risk"),
        "model_id": model_result.get("model_id"),
        "image_quality": (
            model_result.get("image_quality")
            or legacy_content.get("image_quality")
            or legacy_content.get("quality")
            or None
        ),
        "requires_recheck": bool(legacy_content.get("requires_recheck") or False),
        "confidence": (
            float(model_result.get("confidence"))
            if model_result.get("confidence") is not None
            else (
                float(legacy_content.get("confidence"))
                if legacy_content.get("confidence") is not None
                else None
            )
        ),
        "citations": legacy_content.get("citations") or [],
        "model_result": model_result,
        "raw": obs_dict,
    }

    # Remove legacy_result with raw Pydantic objects to prevent LangGraph
    # checkpoint serialization errors (e.g. "Unable to serialize unknown type").
    return {
        **state,
        "legacy_result": None,
        "visual_inspection_result": visual_result,
    }


async def finalize(state: dict[str, Any]) -> dict[str, Any]:
    """Finalize the vision inspection state."""
    return {
        **state,
        "status": "success",
    }
