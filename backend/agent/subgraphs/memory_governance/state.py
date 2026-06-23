from __future__ import annotations

from typing import Any, TypedDict


class MemoryGovernanceState(TypedDict, total=False):
    request_id: str
    workflow_run_id: str
    org_id: str
    user_id: str
    task_context: dict[str, Any]
    structured_memory: list[dict[str, Any]]
    memory_events: list[dict[str, Any]]
    legacy_result: dict[str, Any]
    governance_result: dict[str, Any]
    status: str
    error: dict[str, Any]
