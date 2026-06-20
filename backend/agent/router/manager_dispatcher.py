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
        from agent.router.contracts import AgentRuntimeError

        registry = get_registry()
        invoker = ToolInvoker(registry, db_session=db_session)

        # Setup shared infrastructure (unchanged per step)
        surface = str(getattr(state, "surface", "") or plan.surface or "chat")
        allowed_modes = list(getattr(state, "allowed_modes", []) or [])

        request_ext = dict(getattr(request, "ext", {}) or {})
        forced_tool_names: list[str] = []
        if request_ext.get("force_web_search"):
            forced_tool_names.append("web.search")

        state.forced_tool_names = forced_tool_names
        state.tool_invoker = invoker

        observations: list[AgentObservation] = []
        artifacts: list[AgentArtifact] = []
        completed: set[str] = set()
        remaining = list(plan.steps)

        while remaining:
            ready = [
                step
                for step in remaining
                if all(dep in completed for dep in self._step_dependencies(step))
            ]
            if not ready:
                from agent.router.errors import make_agent_error

                raise make_agent_error(
                    "PLAN_DEPENDENCY_DEADLOCK",
                    message="计划步骤依赖无法满足，无法继续调度。",
                    detail={
                        "remaining_steps": [step.model_dump() for step in remaining],
                        "completed": list(completed),
                    },
                    source="manager.dispatcher",
                )
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

                # Resolve owner_agent
                owner = step.owner_agent
                if not owner:
                    from agent.router.errors import make_agent_error

                    raise make_agent_error(
                        "MISSING_OWNER_AGENT",
                        message=f"计划步骤 {step.step_id} 缺少 owner_agent。",
                        source="manager.dispatcher",
                    )

                executor = self._executors.get(owner)
                if executor is None:
                    from agent.router.errors import make_agent_error

                    raise make_agent_error(
                        "UNKNOWN_OWNER_AGENT",
                        message=f"未知业务 Agent：{owner}。rag/vision/quality_report/data_analysis 不是业务 Agent。",
                        detail={"owner_agent": owner},
                        source="manager.dispatcher",
                    )

                # Per-step tool filtering by owner_agent + capability (Section 10.3 of spec)
                step_cap = step.capability
                available_tools = registry.list_for(
                    agent=owner, capability=step_cap, surface=surface, allowed_modes=allowed_modes,
                ) if owner else []
                if "web.search" in forced_tool_names and "web.search" in registry:
                    web_spec = registry.get("web.search")
                    available_tools = [web_spec] + [t for t in available_tools if t.name != "web.search"]
                state.available_tools = available_tools

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
                    from agent.router.errors import make_agent_error

                    raise make_agent_error(
                        "STEP_EXECUTION_FAILED",
                        message=f"步骤 {step.step_id} 执行失败：{exc}",
                        detail={"raw_error": str(exc)},
                        source="manager.dispatcher",
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
    def _step_dependencies(step: AgentPlanStep) -> list[str]:
        return list(dict.fromkeys([*step.depends_on, *step.dependencies]))

    @staticmethod
    def _step_hash(step: AgentPlanStep) -> str:
        cap = step.capability
        payload = json.dumps(
            {"capability": cap, "operation": step.operation, "input": step.input},
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
