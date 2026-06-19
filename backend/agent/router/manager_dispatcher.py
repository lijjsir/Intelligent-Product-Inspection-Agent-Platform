from __future__ import annotations

import hashlib
import json

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import AgentArtifact, AgentObservation, AgentPlanStep, AgentRoutePlan
from agent.router.executors import (
    ChatExecutor,
    FileExecutor,
    InspectionTaskExecutor,
)
from agent.router.executors.base import observation
from agent.router.manager_state import ManagerState
from agent.tools import get_registry
from agent.tools.invoker import ToolInvoker


class ManagerDispatcher:
    def __init__(self) -> None:
        self._executors = {
            "chat": ChatExecutor(),
            "file": FileExecutor(),
            "inspection_task": InspectionTaskExecutor(),
        }

    async def dispatch(
        self,
        plan: AgentRoutePlan,
        state: ManagerState,
        request: NormalizedRequest,
        db_session=None,
    ) -> tuple[list[AgentObservation], list[AgentArtifact]]:
        from agent.router.contracts import AgentDispatchError, AgentExecutionError, AgentRuntimeError

        registry = get_registry()
        invoker = ToolInvoker(registry, db_session=db_session)

        # Expose tools + invoker to executors via state
        surface = str(getattr(state, "surface", "") or plan.surface or "chat")
        allowed_modes = list(getattr(state, "allowed_modes", []) or [])

        request_ext = dict(getattr(request, "ext", {}) or {})
        forced_tool_names: list[str] = []
        if request_ext.get("force_web_search"):
            forced_tool_names.append("web.search")

        # Use owner_agent for tool filtering (backward compat with selected_agent)
        filter_agent = state.selected_agent or ""
        available_tools = registry.list_for(
            agent=filter_agent, surface=surface, allowed_modes=allowed_modes
        ) if filter_agent else []
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

                # Resolve owner_agent with backward compat
                owner = getattr(step, 'owner_agent', None) or getattr(step, 'agent', None) or ''
                if not owner:
                    raise AgentDispatchError(
                        code="MISSING_OWNER_AGENT",
                        message=f"计划步骤 {step.step_id} 缺少 owner_agent。",
                        frontend_visible=True,
                    )

                executor = self._executors.get(owner)
                if executor is None:
                    raise AgentDispatchError(
                        code="UNKNOWN_OWNER_AGENT",
                        message=f"未知业务 Agent：{owner}。rag/vision/quality_report/data_analysis 不是业务 Agent。",
                        frontend_visible=True,
                    )

                try:
                    step_observation, step_artifacts = await executor.execute(
                        step,
                        state,
                        request,
                        db_session=db_session,
                    )
                except AgentRuntimeError:
                    # Re-raise AgentRuntimeError so ManagerLoop can catch and convert to output
                    raise
                except Exception as exc:
                    raise AgentExecutionError(
                        code="STEP_EXECUTION_FAILED",
                        message=f"步骤 {step.step_id} 执行失败：{exc}",
                        frontend_visible=True,
                        detail={"raw_error": str(exc)},
                    ) from exc

                observations.append(step_observation)
                artifacts.extend(step_artifacts)
                state.observations.append(step_observation)
                state.artifacts.extend(step_artifacts)
                completed.add(step.step_id)
                remaining.remove(step)
                state.used_plan_steps += 1
        return observations, artifacts

    @staticmethod
    def _step_hash(step: AgentPlanStep) -> str:
        cap = getattr(step, 'capability', None) or getattr(step, 'capability_key', '') or ''
        payload = json.dumps(
            {"capability": cap, "operation": step.operation, "input": step.input},
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
