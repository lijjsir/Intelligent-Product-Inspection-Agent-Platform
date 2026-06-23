from __future__ import annotations

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.capabilities.vision_handler import VisionUnderstandingHandler
from agent.router.contracts import AgentPlanStep, CapabilityContext
from agent.router.errors import make_agent_error
from agent.router.executors.graph_executor import GraphExecutor
from agent.router.manager_state import ManagerState


class VisionInspectionExecutor(GraphExecutor):
    SUPPORTED_CAPABILITIES = {"vision.inspect"}

    async def execute(
        self,
        step: AgentPlanStep,
        state: ManagerState,
        request: NormalizedRequest,
        *,
        db_session=None,
    ):
        if step.capability not in self.SUPPORTED_CAPABILITIES:
            raise make_agent_error(
                "UNSUPPORTED_CAPABILITY",
                detail={"capability": step.capability, "executor": "vision"},
                source="vision.executor",
            )
        if not any(str(item.get("kind") or "").lower() == "image" for item in state.attachments):
            raise make_agent_error(
                "VISION_INSPECTION_FAILED",
                message="已路由到视觉检验，但请求中没有可处理图片。",
                detail={"attachment_count": len(state.attachments)},
                source="vision.inspect",
            )

        vision_step = step.model_copy(update={"capability": "image.understanding", "operation": "understand"})
        obs, artifacts = await VisionUnderstandingHandler().run(
            CapabilityContext(
                step=vision_step,
                state=state,
                request=request,
                db_session=db_session,
            )
        )
        if obs.status == "failed":
            raise make_agent_error(
                "VISION_INSPECTION_FAILED",
                detail=obs.error or {},
                source="vision.inspect",
            )
        image_artifact = artifacts[0] if artifacts else None
        result = {
            "query": state.original_query,
            "image_understanding": dict(image_artifact.content or {}) if image_artifact else {},
            "image_count": int((image_artifact.metrics or {}).get("images_processed") or 0) if image_artifact else 0,
        }
        visual_artifact = self._artifact(
            step,
            "visual_inspection_result",
            content=result,
            confidence=image_artifact.confidence if image_artifact else None,
            metrics=dict(image_artifact.metrics or {}) if image_artifact else {},
            summary=obs.summary or "视觉检验完成",
        )
        all_artifacts = [*artifacts, visual_artifact]
        return self._observation(
            step,
            status="success",
            summary=visual_artifact.summary,
            artifacts=all_artifacts,
            metrics=visual_artifact.metrics,
        ), all_artifacts
