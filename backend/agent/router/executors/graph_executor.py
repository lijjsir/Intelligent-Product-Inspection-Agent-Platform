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
        artifacts = [
            item.model_dump(mode="json")
            for item in list(getattr(state, "artifacts", []) or [])
        ]

        request_ext = dict(getattr(request, "ext", {}) or {})
        request_metadata = dict(getattr(request, "metadata", {}) or {})
        manager_model_runtime = getattr(state, "manager_model_runtime", None)
        runtime_payload = dict(manager_model_runtime or {})

        manager_state = {
            "request_id": getattr(state, "request_id", None),
            "workflow_run_id": getattr(state, "workflow_run_id", None),
            "session_id": getattr(state, "session_id", None),
            "assistant_message_id": getattr(state, "assistant_message_id", None),
            "org_id": getattr(state, "org_id", None),
            "user_id": getattr(state, "user_id", None),
            "surface": getattr(state, "surface", None),
            "original_query": getattr(state, "original_query", None),
            "selected_agent": getattr(state, "selected_agent", None),
            "selected_rag_space": getattr(state, "selected_rag_space", None),
            "rag_scope": getattr(state, "rag_scope", None),
            "attachments": list(getattr(state, "attachments", []) or []),
            "request_ext": dict(getattr(state, "request_ext", {}) or {}),
            "request_metadata": dict(getattr(state, "request_metadata", {}) or {}),
            "manager_model_runtime": runtime_payload,
            "artifacts": artifacts,
        }

        return {
            "request_id": getattr(state, "request_id", None),
            "workflow_run_id": getattr(state, "workflow_run_id", None),
            "session_id": getattr(state, "session_id", None),
            "assistant_message_id": getattr(state, "assistant_message_id", None),
            "org_id": getattr(state, "org_id", None),
            "user_id": getattr(state, "user_id", None),
            "surface": getattr(state, "surface", None) or "chat",
            "query": getattr(state, "original_query", "") or getattr(request, "query", ""),
            "attachments": list(getattr(state, "attachments", []) or []),
            "metadata": request_metadata,
            "ext": request_ext,
            "step": step.model_dump(mode="json"),
            "request": request.model_dump(mode="json"),
            "manager_state": manager_state,
            "manager_model_runtime": runtime_payload,
            "model_runtime": runtime_payload,
            "artifacts": artifacts,
        }
