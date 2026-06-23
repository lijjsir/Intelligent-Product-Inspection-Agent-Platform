from __future__ import annotations

from agent.contracts.quality_contracts import NormalizedRequest
from agent.graphs.memory_manager.graph import MemoryManagerGraph
from agent.router.contracts import AgentPlanStep
from agent.router.errors import make_agent_error
from agent.router.executors.graph_executor import GraphExecutor
from agent.router.manager_state import ManagerState


class MemoryGovernanceExecutor(GraphExecutor):
    SUPPORTED_CAPABILITIES = {"memory.governance"}

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
                detail={"capability": step.capability, "executor": "memory_governance"},
                source="memory_governance.executor",
            )
        try:
            graph = MemoryManagerGraph().compile()
            result = await graph.ainvoke(
                {
                    "task_context": {
                        "org_id": request.org_id,
                        "user_id": request.user_id,
                        "query": state.original_query,
                        "trace_id": state.trace_id or state.workflow_run_id,
                        "request_id": state.request_id,
                        "workflow_run_id": state.workflow_run_id,
                    },
                    "structured_memory": list((request.ext or {}).get("structured_memory") or []),
                    "memory_events": list((request.ext or {}).get("memory_events") or []),
                }
            )
        except Exception as exc:
            raise make_agent_error(
                "MEMORY_GOVERNANCE_FAILED",
                message="记忆治理图执行失败。",
                debug={"raw_error": str(exc)},
                source="memory.governance",
                cause=exc,
            ) from exc
        final = dict(result.get("final_result") or {})
        art = self._artifact(
            step,
            "memory_governance_result",
            content=final,
            metrics={
                "memory_sources_used": int(final.get("memory_sources_used") or 0),
                "contamination_nodes": int(final.get("contamination_nodes") or 0),
            },
            summary="记忆治理完成",
        )
        return self._observation(step, status="success", summary=art.summary, artifacts=[art], metrics=art.metrics), [art]
