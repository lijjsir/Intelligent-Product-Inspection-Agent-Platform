from __future__ import annotations

from typing import Any, Awaitable, Callable

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import AgentArtifact, AgentObservation, AgentPlanStep
from agent.router.executors.base import artifact, observation
from agent.router.manager_state import ManagerState


GraphRunFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class GraphExecutor:
    """Small adapter for Manager-owned LangGraph style executors."""

    def _artifact(
        self,
        step: AgentPlanStep,
        artifact_type: str,
        *,
        content: dict[str, Any] | None = None,
        citations: list[dict[str, Any]] | None = None,
        confidence: float | None = None,
        status: str = "success",
        summary: str = "",
        metrics: dict[str, Any] | None = None,
        empty_result: bool = False,
        needs_user_input: bool = False,
        error: dict[str, Any] | None = None,
    ) -> AgentArtifact:
        return artifact(
            step,
            artifact_type,
            content=content,
            citations=citations,
            confidence=confidence,
            status=status,
            summary=summary,
            metrics=metrics,
            empty_result=empty_result,
            needs_user_input=needs_user_input,
            error=error,
        )

    def _observation(
        self,
        step: AgentPlanStep,
        *,
        status: str,
        summary: str,
        artifacts: list[AgentArtifact] | None = None,
        metrics: dict[str, Any] | None = None,
        error: str | dict[str, Any] | None = None,
    ) -> AgentObservation:
        return observation(
            step,
            status=status,
            summary=summary,
            artifact_ids=[item.artifact_id for item in list(artifacts or [])],
            metrics=metrics,
            error=error,
        )

    @staticmethod
    def base_graph_state(
        state: ManagerState,
        request: NormalizedRequest,
        step: AgentPlanStep,
    ) -> dict[str, Any]:
        return {
            "request_id": state.request_id,
            "workflow_run_id": state.workflow_run_id,
            "session_id": state.session_id,
            "assistant_message_id": state.assistant_message_id,
            "org_id": state.org_id,
            "user_id": state.user_id,
            "surface": state.surface,
            "query": state.original_query,
            "attachments": list(state.attachments),
            "metadata": dict(request.metadata or {}),
            "ext": dict(request.ext or {}),
            "step": step.model_dump(),
        }
