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
    artifact_type: str,
    source_agent: str,
    content: dict[str, Any],
    *,
    confidence: float | None = None,
    citations: list[dict[str, Any]] | None = None,
) -> AgentArtifact:
    digest = hashlib.sha1(
        json.dumps(content, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()[:12]
    return AgentArtifact(
        artifact_id=f"art_{artifact_type}_{digest}",
        type=artifact_type,
        source_agent=source_agent,
        content=content,
        citations=list(citations or []),
        confidence=confidence,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def observation(
    step: AgentPlanStep,
    *,
    status: str,
    summary: str,
    artifact_ids: list[str] | None = None,
    metrics: dict[str, Any] | None = None,
    error: str | None = None,
) -> AgentObservation:
    return AgentObservation(
        step_id=step.step_id,
        capability_key=step.capability_key,
        agent=step.agent,
        status=status,  # type: ignore[arg-type]
        summary=summary,
        metrics=dict(metrics or {}),
        error=error,
        artifact_ids=list(artifact_ids or []),
    )
