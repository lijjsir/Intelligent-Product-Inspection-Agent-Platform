from __future__ import annotations

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import AgentPlanStep, AgentRouteDecision, AgentArtifact, AgentObservation
from agent.router.executors.base import artifact, observation
from agent.router.manager_state import ManagerState


class InspectionTaskExecutor:
    SUPPORTED_CAPABILITIES = {
        "quality.inspection.execute",
        "vision.understand",
        "rag.retrieve",
        "rule.evaluate",
        "quality.report.write",
        "inspection.persist",
    }

    def __init__(self) -> None:
        self._graph = None

    @property
    def graph(self):
        if self._graph is None:
            from agent.subgraphs.inspection_task.graph import InspectionTaskGraph

            self._graph = InspectionTaskGraph()
        return self._graph

    async def execute(
        self,
        step: AgentPlanStep,
        state: ManagerState,
        request: NormalizedRequest,
        *,
        db_session=None,
    ) -> tuple[AgentObservation, list[AgentArtifact]]:
        from agent.router.contracts import AgentCapabilityError

        cap = getattr(step, 'capability', None) or getattr(step, 'capability_key', None) or ''

        if cap not in self.SUPPORTED_CAPABILITIES:
            raise AgentCapabilityError(
                code="UNSUPPORTED_CAPABILITY",
                message=f"InspectionTaskExecutor 不支持能力：{cap}",
                frontend_visible=True,
            )

        output = await self.graph.run(
            request,
            AgentRouteDecision(
                selected_agent="inspection_task",
                sub_route="inspection_execute",
                intent="inspection_execute",
                reason="quality_task surface allowed formal inspection",
            ),
        )
        raw = output.model_dump() if hasattr(output, "model_dump") else dict(output or {})
        persistable = raw.get("persistable_output") or {}
        art = artifact(
            step,
            "inspection_task",
            content={
                "answer": raw.get("answer"),
                "summary": raw.get("summary"),
                "action_state": raw.get("action_state"),
                "task": persistable.get("task"),
                "result": persistable.get("result"),
                "stability": persistable.get("stability"),
                "alerts": persistable.get("alerts"),
            },
            confidence=0.9,
        )
        return (
            observation(
                step,
                status="success",
                summary=str(raw.get("summary") or raw.get("answer") or "正式检测已处理"),
                artifact_ids=[art.artifact_id],
            ),
            [art],
        )
