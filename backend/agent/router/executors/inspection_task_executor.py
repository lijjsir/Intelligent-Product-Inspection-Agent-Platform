from __future__ import annotations

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import AgentPlanStep, AgentRouteDecision, AgentArtifact, AgentObservation
from agent.router.executors.base import artifact, observation
from agent.router.manager_state import ManagerState


class InspectionTaskExecutor:
    SUPPORTED_CAPABILITIES = {
        "quality.inspection.execute",
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
        cap = step.capability

        if cap not in self.SUPPORTED_CAPABILITIES:
            from agent.router.errors import make_agent_error

            raise make_agent_error(
                "UNSUPPORTED_CAPABILITY",
                message=f"InspectionTaskExecutor 不支持能力：{cap}",
                detail={"capability": cap, "executor": "inspection_task"},
                source="inspection_task.executor",
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
        action_state = str(raw.get("action_state") or "").lower()
        status = str(raw.get("status") or "").lower()
        answer = str(raw.get("answer") or "")
        summary = str(raw.get("summary") or answer or "")

        if action_state in {"awaiting_clarification", "blocked", "need_user_input"}:
            art = artifact(
                step,
                "inspection_task",
                status="blocked",
                needs_user_input=True,
                content=raw,
                summary=summary or "正式质检缺少必要输入。",
                confidence=0.0,
            )
            return (
                observation(
                    step,
                    status="blocked",
                    summary=summary or "正式质检缺少必要输入。",
                    artifact_ids=[art.artifact_id],
                ),
                [art],
            )

        if action_state in {"failed", "error"} or status == "failed":
            from agent.router.errors import make_agent_error
            raise make_agent_error(
                "INSPECTION_TASK_FAILED",
                message=summary or "正式质检任务执行失败。",
                detail={"raw_output": raw},
                source="quality.inspection.execute",
            )

        persistable = raw.get("persistable_output") or {}
        art = artifact(
            step,
            "inspection_task",
            status="success",
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
