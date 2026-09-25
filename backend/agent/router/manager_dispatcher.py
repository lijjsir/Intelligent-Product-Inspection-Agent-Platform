from __future__ import annotations

import hashlib
import json
import asyncio

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import AgentArtifact, AgentObservation, AgentPlanStep, AgentRoutePlan
from agent.router.executors import (
    FileExecutor,
    LabDetectionExecutor,
    QualityAnalysisExecutor,
    VisionInspectionExecutor,
)
from agent.router.executors.base import observation
from agent.router.executors.evidence_arbitration_executor import EvidenceArbitrationExecutor
from agent.router.executors.memory_governance_executor import MemoryGovernanceExecutor
from agent.router.executors.supervision_executor import (
    SupervisionExecutor,
    SupervisionTrustReviewExecutor,
)
from agent.router.manager_state import ManagerState
from agent.tools import get_registry
from agent.tools.invoker import ToolInvoker
from app.services.agent_local_memory_service import AgentLocalMemoryService
from app.services.task_blackboard_service import TaskBlackboardService


class ManagerDispatcher:
    _BUSINESS_AGENTS = {
        "vision",
        "lab_detection",
        "quality_analysis",
        "file",
        "market_monitoring",
        "public_opinion_monitoring",
        "supervision_sampling",
        "laboratory_testing",
    }

    def __init__(
        self,
        blackboard: TaskBlackboardService | None = None,
        local_memory: AgentLocalMemoryService | None = None,
    ) -> None:
        self._executors = {
            "vision": VisionInspectionExecutor(),
            "lab_detection": LabDetectionExecutor(),
            "quality_analysis": QualityAnalysisExecutor(),
            "file": FileExecutor(),
            "market_monitoring": SupervisionExecutor(),
            "public_opinion_monitoring": SupervisionExecutor(),
            "supervision_sampling": SupervisionExecutor(),
            "laboratory_testing": SupervisionExecutor(),
        }
        self._capability_executors = {
            "evidence.arbitrate": EvidenceArbitrationExecutor(),
            "memory.governance": MemoryGovernanceExecutor(),
            "trust.review": SupervisionTrustReviewExecutor(),
        }
        self._blackboard = blackboard or TaskBlackboardService()
        self._local_memory = local_memory or AgentLocalMemoryService()

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
        await self._ensure_blackboard(state)

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
            # Fan out explicitly independent professional steps with private ManagerState and DB sessions.
            group = [s for s in ready if s.parallel_group and s.parallel_group == ready[0].parallel_group]
            if len(group) > 1:
                from agent.router.capability_registry import CAPABILITIES
                group = [s for s in group if not CAPABILITIES.get(s.capability) or CAPABILITIES[s.capability].allow_parallel]
            if len(group) > 1:
                baseline_tool_calls, baseline_llm_calls = state.used_tool_calls, state.used_llm_calls
                await self._blackboard.update_global_state(state.org_id,state.workflow_run_id,{"active_step_ids":[s.step_id for s in group]})
                async def execute_branch(step):
                    branch = state.model_copy(update={"tool_invoker": None, "available_tools": []}).model_copy(deep=True)
                    branch.tool_invoker = None
                    branch.current_step_id = None
                    branch.current_owner_agent = None
                    branch.available_tools = []
                    isolated_step = step.model_copy(update={"dependencies": [], "depends_on": [], "parallel_group": None})
                    isolated_plan = plan.model_copy(update={"steps": [isolated_step]})
                    if db_session is not None:
                        from infra.database.session import get_session
                        async with get_session() as private_session:
                            output = await self.dispatch(isolated_plan, branch, request, db_session=private_session)
                            await private_session.commit()
                    else:
                        output = await self.dispatch(isolated_plan, branch, request, db_session=None)
                    return step, branch, output

                results = await asyncio.gather(*(execute_branch(s) for s in group), return_exceptions=True)
                failure = None
                for result in results:
                    if isinstance(result, BaseException):
                        failure = result
                        continue
                    step, branch, (branch_observations, branch_artifacts) = result
                    observations.extend(branch_observations)
                    artifacts.extend(branch_artifacts)
                    state.observations.extend(branch_observations)
                    state.artifacts.extend(branch_artifacts)
                    state.used_tool_calls += max(0, branch.used_tool_calls - baseline_tool_calls)
                    state.used_llm_calls += max(0, branch.used_llm_calls - baseline_llm_calls)
                    state.used_plan_steps += 1
                    state.executed_step_hashes.update(branch.executed_step_hashes)
                    completed.add(step.step_id)
                    remaining.remove(step)
                await self._blackboard.update_global_state(state.org_id, state.workflow_run_id,
                    {"completed_steps": sorted(completed), "current_step_id": None, "current_agent": None,"active_step_ids":[]})
                if failure:
                    raise failure
                continue
            for step in ready:
                step_hash = self._step_hash(step)
                if step_hash in state.executed_step_hashes:
                    skipped = observation(step, status="skipped", summary="重复 step 已跳过")
                    observations.append(skipped)
                    state.observations.append(skipped)
                    await self._blackboard.append_observation(
                        state.org_id,
                        state.workflow_run_id,
                        skipped.model_dump(mode="json"),
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

                executor = self._capability_executors.get(step.capability) or self._executors.get(owner)
                if executor is None:
                    from agent.router.errors import make_agent_error

                    raise make_agent_error(
                        "UNKNOWN_OWNER_AGENT",
                        message=f"未知执行所有者：{owner}。该 Agent 尚未注册到统一调度器。",
                        detail={"owner_agent": owner},
                        source="manager.dispatcher",
                    )

                # Per-step tool filtering by owner_agent + capability (Section 10.3 of spec)
                step_cap = step.capability
                tool_owner = owner
                available_tools = registry.list_for(
                    agent=tool_owner, capability=step_cap, surface=surface, allowed_modes=allowed_modes,
                ) if tool_owner else []
                if "web.search" in forced_tool_names and "web.search" in registry:
                    web_spec = registry.get("web.search")
                    available_tools = [web_spec] + [t for t in available_tools if t.name != "web.search"]
                state.available_tools = available_tools
                state.selected_agent = owner
                state.current_step_id = step.step_id
                state.current_capability = step.capability
                state.current_owner_agent = owner
                state.blackboard_snapshot = await self._blackboard.snapshot(
                    state.org_id,
                    state.workflow_run_id,
                )
                state.blackboard_context = state.blackboard_snapshot
                await self._load_agent_local_memory(state, owner)
                await self._blackboard.update_global_state(
                    state.org_id,
                    state.workflow_run_id,
                    {
                        "status": "running",
                        "current_step_id": step.step_id,
                        "current_agent": owner if owner != "orchestrator" else None,
                        "current_capability": step.capability,
                        "completed_steps": sorted(completed),
                        "used_tool_calls": state.used_tool_calls,
                        "used_llm_calls": state.used_llm_calls,
                    },
                )

                try:
                    step_observation, step_artifacts = await executor.execute(
                        step,
                        state,
                        request,
                        db_session=db_session,
                    )
                except AgentRuntimeError:
                    state.executed_step_hashes.discard(step_hash)
                    await self._mark_step_failed(state, step)
                    # Re-raise AgentRuntimeError so ManagerLoop can catch and convert to output
                    raise
                except Exception as exc:
                    state.executed_step_hashes.discard(step_hash)
                    await self._mark_step_failed(state, step)
                    from agent.router.errors import make_agent_error

                    raise make_agent_error(
                        "STEP_EXECUTION_FAILED",
                        message=f"步骤 {step.step_id} 执行失败：{exc}",
                        detail={"raw_error": str(exc)},
                        source="manager.dispatcher",
                    ) from exc

                observations.append(step_observation)
                normalized_artifacts = []
                for item in step_artifacts:
                    content = dict(item.content or {})
                    consumed_ids = list(
                        item.consumed_artifact_ids
                        or content.get("consumed_artifact_ids")
                        or []
                    )
                    candidate_extractable = bool(
                        item.candidate_extractable
                        or content.get("candidate_extractable")
                    )
                    normalized_artifacts.append(
                        item.model_copy(
                            update={
                                "workflow_run_id": state.workflow_run_id,
                                "step_id": step.step_id,
                                "consumed_artifact_ids": consumed_ids,
                                "candidate_extractable": candidate_extractable,
                            }
                        )
                    )
                step_artifacts = normalized_artifacts
                try:
                    self._validate_expected_artifact(step, step_artifacts)
                except AgentRuntimeError:
                    await self._mark_step_failed(state, step)
                    raise
                artifacts.extend(step_artifacts)
                state.observations.append(step_observation)
                state.artifacts.extend(step_artifacts)
                await self._blackboard.append_observation(
                    state.org_id,
                    state.workflow_run_id,
                    step_observation.model_dump(mode="json"),
                )
                for item in step_artifacts:
                    await self._blackboard.append_artifact(
                        state.org_id,
                        state.workflow_run_id,
                        item.model_dump(mode="json"),
                    )
                    candidate_source = self._candidate_source_from_artifact(item)
                    if candidate_source:
                        await self._blackboard.append_candidate_source(
                            state.org_id,
                            state.workflow_run_id,
                            candidate_source,
                        )
                await self._append_agent_local_memory(
                    state,
                    step,
                    step_observation,
                    step_artifacts,
                )
                completed.add(step.step_id)
                remaining.remove(step)
                state.used_plan_steps += 1
                await self._blackboard.update_global_state(
                    state.org_id,
                    state.workflow_run_id,
                    {
                        "status": "running",
                        "current_step_id": None,
                        "current_agent": None,
                        "current_capability": None,
                        "completed_steps": sorted(completed),
                        "used_tool_calls": state.used_tool_calls,
                        "used_llm_calls": state.used_llm_calls,
                    },
                )
                state.blackboard_snapshot = await self._blackboard.snapshot(
                    state.org_id,
                    state.workflow_run_id,
                )
                state.blackboard_context = state.blackboard_snapshot
        return observations, artifacts

    async def _ensure_blackboard(self, state: ManagerState) -> None:
        snapshot = await self._blackboard.snapshot(state.org_id, state.workflow_run_id)
        if not snapshot:
            await self._blackboard.init_blackboard(
                state.org_id,
                state.workflow_run_id,
                state.task_id,
                86400,
            )
            snapshot = await self._blackboard.snapshot(state.org_id, state.workflow_run_id)
        state.blackboard_snapshot = snapshot
        state.blackboard_context = snapshot

    async def _load_agent_local_memory(self, state: ManagerState, owner: str) -> None:
        if owner not in self._BUSINESS_AGENTS:
            state.agent_local_memory_context = []
            state.agent_local_memory_owner = None
            return
        state.agent_local_memory_context = await self._local_memory.snapshot(
            org_id=state.org_id,
            agent_id=owner,
            workflow_run_id=state.workflow_run_id,
        )
        state.agent_local_memory_owner = owner

    async def _append_agent_local_memory(
        self,
        state: ManagerState,
        step: AgentPlanStep,
        observation_item: AgentObservation,
        artifacts: list[AgentArtifact],
    ) -> None:
        owner = step.owner_agent
        if owner not in self._BUSINESS_AGENTS:
            return
        global_state = dict((state.blackboard_snapshot or {}).get("global_state") or {})
        product_line = str(global_state.get("product_line") or "").strip() or None
        for item in artifacts:
            summary = str(
                item.summary
                or (item.content or {}).get("summary")
                or observation_item.summary
                or ""
            ).strip()
            if not summary:
                continue
            content = dict(item.content or {})
            shareable = bool(item.candidate_extractable and product_line)
            memory_item = {
                "memory_id": f"local_{item.artifact_id}",
                "source_artifact_id": item.artifact_id,
                "source_step_id": step.step_id,
                "source_capability": step.capability,
                "artifact_type": item.type,
                "summary": summary[:500],
                "facts": [
                    f"artifact_type: {item.type}",
                    f"status: {item.status}",
                ],
                "confidence": item.confidence,
                "product_line": product_line,
                "shareable": shareable,
                "share_reason": (
                    item.candidate_reason
                    or content.get("candidate_reason")
                    or "can_improve_other_agents"
                    if shareable
                    else None
                ),
                "share_value_score": (
                    content.get("share_value_score")
                    or content.get("overall_score")
                    or item.confidence
                    or 0.0
                ),
                "target_agents": list(
                    item.target_agents or content.get("target_agents") or []
                ),
                "status": "active",
            }
            await self._local_memory.append(
                org_id=state.org_id,
                agent_id=owner,
                workflow_run_id=state.workflow_run_id,
                item=memory_item,
            )
        state.agent_local_memory_context = await self._local_memory.snapshot(
            org_id=state.org_id,
            agent_id=owner,
            workflow_run_id=state.workflow_run_id,
        )

    @staticmethod
    def _validate_expected_artifact(
        step: AgentPlanStep,
        artifacts: list[AgentArtifact],
    ) -> None:
        if not step.expected_artifact or not step.required:
            return
        if any(item.type == step.expected_artifact for item in artifacts):
            return
        from agent.router.errors import make_agent_error

        raise make_agent_error(
            "EXPECTED_ARTIFACT_MISSING",
            message=(
                f"步骤 {step.step_id} 未输出预期产物 "
                f"{step.expected_artifact}。"
            ),
            detail={
                "step_id": step.step_id,
                "capability": step.capability,
                "expected_artifact": step.expected_artifact,
                "actual_artifacts": [item.type for item in artifacts],
            },
            source="manager.dispatcher",
        )

    async def _mark_step_failed(self, state: ManagerState, step: AgentPlanStep) -> None:
        snapshot = await self._blackboard.snapshot(state.org_id, state.workflow_run_id)
        failed = list((snapshot.get("global_state") or {}).get("failed_steps") or [])
        if step.step_id not in failed:
            failed.append(step.step_id)
        await self._blackboard.update_global_state(
            state.org_id,
            state.workflow_run_id,
            {
                "status": "failed",
                "current_step_id": step.step_id,
                "current_capability": step.capability,
                "failed_steps": failed,
            },
        )

    @staticmethod
    def _candidate_source_from_artifact(artifact: AgentArtifact) -> dict | None:
        if not artifact.candidate_extractable:
            return None
        content = dict(artifact.content or {})
        score = float(
            content.get("share_value_score")
            or content.get("overall_score")
            or artifact.confidence
            or 0.0
        )
        return {
            "source_artifact_id": artifact.artifact_id,
            "source_agent": artifact.source_agent,
            "candidate_type": content.get("candidate_type") or "inspection_pattern",
            "share_value_score": max(0.0, min(1.0, score)),
            "target_agents": list(artifact.target_agents or content.get("target_agents") or []),
            "reason": artifact.candidate_reason or content.get("candidate_reason") or "artifact marked extractable",
            "evidence_artifact_ids": list(
                artifact.consumed_artifact_ids
                or content.get("consumed_artifact_ids")
                or []
            ),
        }

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


# Public architecture name; ManagerDispatcher remains for compatibility.
OrchestrationDispatcher = ManagerDispatcher
