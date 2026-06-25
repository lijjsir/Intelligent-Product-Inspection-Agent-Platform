from __future__ import annotations

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import AgentArtifact, AgentPlanStep
from agent.router.errors import AgentRuntimeError, make_agent_error
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

        try:
            from agent.subgraphs.vision_inspection.graph import VisionInspectionGraph

            graph_state = self.base_graph_state(state, request, step)
            graph_state["db_session"] = db_session
            result = await VisionInspectionGraph().run(graph_state)

            visual_result = result.get("visual_inspection_result") or {}
            status = result.get("status", "success")
            summary = visual_result.get("summary", "视觉检验完成")

            visual_artifact = self._artifact(
                step,
                "visual_inspection_result",
                status=status,
                content=visual_result,
                summary=summary,
            )

            return self._observation(
                step,
                status="success",
                summary=summary,
                artifacts=[visual_artifact],
            ), [visual_artifact]

        except AgentRuntimeError:
            raise
        except Exception as exc:
            raise make_agent_error(
                "VISION_INSPECTION_FAILED",
                message=f"视觉检验执行失败：{exc}",
                detail={
                    "step_id": step.step_id,
                    "capability": step.capability,
                },
                debug={
                    "raw_error": str(exc),
                    "error_type": exc.__class__.__name__,
                },
                source="vision.executor",
                cause=exc,
            ) from exc
