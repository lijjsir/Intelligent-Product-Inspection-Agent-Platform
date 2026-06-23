from __future__ import annotations

from typing import Any

from agent.router.errors import make_agent_error


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


async def legacy_vision_understanding_node(state: dict[str, Any]) -> dict[str, Any]:
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
                db_session=state.get("db_session"),
            )
        )
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
            obs_dict = obs.model_dump()
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

    visual_result = {
        "status": obs_dict.get("status", "success"),
        "summary": obs_dict.get("summary") or legacy_content.get("summary") or "",
        "answer": legacy_content.get("answer") or obs_dict.get("summary") or "",
        "defects": legacy_content.get("defects") or [],
        "citations": legacy_content.get("citations") or [],
        "raw": obs_dict,
    }

    return {
        **state,
        "visual_inspection_result": visual_result,
    }


async def finalize(state: dict[str, Any]) -> dict[str, Any]:
    """Finalize the vision inspection state."""
    return {
        **state,
        "status": "success",
    }
