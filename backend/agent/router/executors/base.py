from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Protocol

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import AgentArtifact, AgentObservation, AgentPlanStep
from agent.router.manager_state import ManagerState


class CapabilityExecutor(Protocol):
    async def execute(
        self,
        step: AgentPlanStep,
        state: ManagerState,
        request: NormalizedRequest,
        *,
        db_session=None,
    ) -> tuple[AgentObservation, list[AgentArtifact]]:
        ...


def artifact(
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
    import hashlib, uuid
    source = getattr(step, 'owner_agent', None) or getattr(step, 'agent', '') or 'unknown'
    raw = f"{step.step_id}:{artifact_type}:{source}:{uuid.uuid4()}"
    artifact_id = hashlib.sha1(raw.encode()).hexdigest()[:12]
    return AgentArtifact(
        artifact_id=artifact_id,
        type=artifact_type,
        source_agent=source,
        status=status,
        content=content or {},
        summary=summary,
        citations=citations or [],
        confidence=confidence,
        metrics=metrics or {},
        empty_result=empty_result,
        needs_user_input=needs_user_input,
        error=error,
    )


def observation(
    step: AgentPlanStep,
    *,
    status: str,
    summary: str,
    artifact_ids: list[str] | None = None,
    metrics: dict[str, Any] | None = None,
    error: str | dict[str, Any] | None = None,
) -> AgentObservation:
    # Normalize error to dict format expected by AgentObservation
    error_dict: dict[str, Any] | None = None
    if isinstance(error, dict):
        error_dict = error
    elif isinstance(error, str) and error:
        error_dict = {"message": error}

    cap = getattr(step, "capability", None) or getattr(step, "capability_key", "") or ""
    owner = getattr(step, "owner_agent", None) or getattr(step, "agent", "") or ""

    return AgentObservation(
        step_id=step.step_id,
        capability_key=cap,
        owner_agent=owner,
        agent=owner,
        status=status,  # type: ignore[arg-type]
        summary=summary,
        metrics=dict(metrics or {}),
        error=error_dict,
        artifact_ids=list(artifact_ids or []),
    )
