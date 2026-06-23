from __future__ import annotations

from typing import Any, TypedDict


class EvidenceArbitrationState(TypedDict, total=False):
    org_id: str
    user_id: str | None
    session_id: str | None
    workflow_run_id: str
    surface: str
    query: str
    request: dict[str, Any]
    manager_state: dict[str, Any]
    db_session: Any

    rag_hits: list[dict[str, Any]]
    shared_memory_hits: list[dict[str, Any]]
    kg_hits: list[dict[str, Any]]
    normalized_evidence: list[dict[str, Any]]
    conflicts: list[dict[str, Any]]
    evidence_packet: dict[str, Any]
    status: str
    summary: str
    confidence: float
