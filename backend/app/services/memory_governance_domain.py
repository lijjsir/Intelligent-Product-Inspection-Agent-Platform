from __future__ import annotations

from dataclasses import dataclass
from typing import Any


REVIEW_STATUSES = {"candidate", "approved", "disputed", "rejected", "isolated", "superseded"}
ACCESS_SCOPE_TYPES = {"meeting_room", "user", "task", "rag_space", "agent", "org_space", "collab_thread"}


@dataclass(frozen=True)
class MemoryReadiness:
    status: str
    score: float
    blockers: list[str]
    reason: str | None = None


def normalize_source_kind(raw: str | None) -> str:
    value = str(raw or "").strip().lower()
    aliases = {
        "meeting_room": "meeting",
        "meeting_message": "meeting",
        "user": "chat",
        "chat_message": "chat",
        "agent_message": "agent",
        "tool": "agent",
        "inspection_task": "task",
        "human_review": "human_review",
    }
    return aliases.get(value, value or "unknown")


def legacy_review_status(raw: str | None) -> tuple[str, bool, str | None]:
    value = str(raw or "").strip().lower()
    mapping = {
        "candidate": "candidate",
        "confirmed": "approved",
        "active": "approved",
        "disputed": "disputed",
        "contested": "disputed",
        "rejected": "rejected",
        "disabled": "rejected",
        "isolated": "isolated",
        "superseded": "superseded",
    }
    normalized = mapping.get(value)
    if normalized:
        return normalized, False, None
    return "candidate", True, f"unmapped legacy status: {value or 'empty'}"


def default_home_scope(
    *,
    source_kind: str,
    org_id: str,
    user_id: str | None = None,
    meeting_room_id: str | None = None,
    task_id: str | None = None,
    rag_space_id: str | None = None,
    agent_id: str | None = None,
) -> tuple[str | None, str | None]:
    kind = normalize_source_kind(source_kind)
    if kind == "meeting" and meeting_room_id:
        return "meeting_room", meeting_room_id
    if kind == "chat" and user_id:
        return "user", user_id
    if task_id:
        return "task", task_id
    if kind == "rag" and rag_space_id:
        return "rag_space", rag_space_id
    if kind == "agent":
        return "agent", agent_id or "general_agent"
    if kind == "human_review" and user_id:
        return "user", user_id
    if kind == "organization":
        return "org_space", org_id
    return None, None


def default_governance_target(source_kind: str, org_id: str) -> tuple[str | None, str | None]:
    kind = normalize_source_kind(source_kind)
    if kind in {"task", "rag", "agent"}:
        return "org_space", org_id
    return None, None


def evidence_role_from_legacy_support(support_type: str | None) -> str:
    value = str(support_type or "").strip().lower()
    return {
        "source_evidence": "origin",
        "support": "support",
        "rag_evidence": "rag",
        "agent_verifier": "agent_verification",
        "human_approved": "human_confirmation",
        "negative": "opposition",
        "conflict": "conflict",
    }.get(value, "support")


def calculate_readiness(
    stats: dict[str, Any],
    *,
    review_status: str,
    migration_review_required: bool = False,
) -> MemoryReadiness:
    origin_count = int(stats.get("origin_evidence_count") or 0)
    independent_count = int(stats.get("independent_support_count") or 0)
    rag_count = int(stats.get("rag_evidence_count") or 0)
    agent_count = int(stats.get("agent_verifier_count") or 0)
    human_count = int(stats.get("human_confirmation_count") or 0)
    opposition_count = int(stats.get("opposition_count") or 0)
    conflict_count = int(stats.get("conflict_count") or 0)
    unique_task_count = int(stats.get("unique_task_count") or 0)
    avg_confidence = float(stats.get("avg_confidence") or 0.0)
    rag_avg_confidence = float(stats.get("rag_avg_confidence") or avg_confidence)
    agent_avg_confidence = float(stats.get("agent_avg_confidence") or avg_confidence)

    blockers: list[str] = []
    if origin_count < 1:
        blockers.append("missing_origin_evidence")
    if conflict_count > 0 or review_status == "disputed":
        blockers.append("unresolved_conflict")
    if opposition_count > 0:
        blockers.append("opposition_evidence")
    if migration_review_required:
        blockers.append("migration_review_required")
    if review_status in {"rejected", "isolated", "superseded"}:
        blockers.append(f"review_status_{review_status}")

    score = (
        origin_count * 0.2
        + independent_count * 0.4
        + rag_count * 0.8
        + agent_count * 0.5
        + human_count * 1.0
        + unique_task_count * 0.3
        + avg_confidence * 0.5
        - opposition_count * 0.6
        - conflict_count * 0.8
    )
    if blockers:
        return MemoryReadiness(status="blocked", score=score, blockers=list(dict.fromkeys(blockers)))

    if review_status == "approved" or human_count >= 1:
        return MemoryReadiness(status="ready", score=score, blockers=[], reason="local_human_approved")
    if rag_count >= 1 and rag_avg_confidence >= 0.70:
        return MemoryReadiness(status="ready", score=score, blockers=[], reason="authoritative_rag")
    if unique_task_count >= 5:
        return MemoryReadiness(status="ready", score=score, blockers=[], reason="five_independent_tasks")
    if agent_count >= 2 and agent_avg_confidence >= 0.75:
        return MemoryReadiness(status="ready", score=score, blockers=[], reason="two_agent_verifications")
    return MemoryReadiness(status="collecting", score=score, blockers=[], reason=None)
