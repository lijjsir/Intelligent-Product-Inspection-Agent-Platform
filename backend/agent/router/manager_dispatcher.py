from __future__ import annotations

import hashlib
import json

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import AgentArtifact, AgentObservation, AgentPlanStep, AgentRoutePlan
from agent.router.executors import (
    ChatExecutor,
    DataAnalysisExecutor,
    FileExecutor,
    InspectionTaskExecutor,
    QualityReportExecutor,
    RagExecutor,
    VisionExecutor,
)
from agent.router.executors.base import observation
from agent.router.manager_state import ManagerState
from agent.tools import get_registry
from agent.tools.invoker import ToolInvoker


class ManagerDispatcher:
    def __init__(self) -> None:
        self._executors = {
            "chat": ChatExecutor(),
            "rag": RagExecutor(),
            "file": FileExecutor(),
            "vision": VisionExecutor(),
            "quality_report": QualityReportExecutor(),
            "inspection_task": InspectionTaskExecutor(),
            "data_analysis": DataAnalysisExecutor(),
        }

    async def dispatch(
        self,
        plan: AgentRoutePlan,
        state: ManagerState,
        request: NormalizedRequest,
        db_session=None,
    ) -> tuple[list[AgentObservation], list[AgentArtifact]]:
        registry = get_registry()
        invoker = ToolInvoker(registry, db_session=db_session)

        # Expose tools + invoker to executors via state
        surface = str(getattr(state, "surface", "") or plan.surface or "chat")
        agent = state.selected_agent or ""
        allowed_modes = list(getattr(state, "allowed_modes", []) or [])

        request_ext = dict(getattr(request, "ext", {}) or {})
        forced_tool_names: list[str] = []
        if request_ext.get("force_web_search"):
            forced_tool_names.append("web.search")

        available_tools = registry.list_for(agent=agent, surface=surface, allowed_modes=allowed_modes)
        if "web.search" in forced_tool_names and "web.search" in registry:
            # User explicitly selected web search; put it first so the tool loop can force it.
            web_spec = registry.get("web.search")
            available_tools = [web_spec] + [t for t in available_tools if t.name != "web.search"]
        state.available_tools = available_tools
        state.forced_tool_names = forced_tool_names
        state.tool_invoker = invoker

        observations: list[AgentObservation] = []
        artifacts: list[AgentArtifact] = []
        completed: set[str] = set()
        remaining = list(plan.steps)

        while remaining:
            ready = [step for step in remaining if all(dep in completed for dep in step.depends_on)]
            if not ready:
                break
            for step in ready:
                step_hash = self._step_hash(step)
                if step_hash in state.executed_step_hashes:
                    observations.append(
                        observation(step, status="skipped", summary="重复 step 已跳过")
                    )
                    completed.add(step.step_id)
                    remaining.remove(step)
                    continue

                state.executed_step_hashes.add(step_hash)
                executor = self._executors.get(step.agent)
                if executor is None:
                    step_observation = observation(step, status="skipped", summary="能力暂未实现")
                    step_artifacts: list[AgentArtifact] = []
                else:
                    try:
                        step_observation, step_artifacts = await executor.execute(
                            step,
                            state,
                            request,
                            db_session=db_session,
                        )
                    except Exception as exc:
                        step_observation = observation(
                            step,
                            status="failed",
                            summary="能力执行失败",
                            error=str(exc),
                        )
                        step_artifacts = []
                observations.append(step_observation)
                artifacts.extend(step_artifacts)
                state.observations.append(step_observation)
                state.artifacts.extend(step_artifacts)
                completed.add(step.step_id)
                remaining.remove(step)
                state.used_tool_calls += 1
        return observations, artifacts

    @staticmethod
    def _step_hash(step: AgentPlanStep) -> str:
        payload = json.dumps(
            {"capability_key": step.capability_key, "operation": step.operation, "input": step.input},
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
