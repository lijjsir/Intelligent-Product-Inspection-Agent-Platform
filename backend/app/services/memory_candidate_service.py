"""MemoryCandidateService - rule-based extraction of candidate memories from agent outputs.

P0 scope: only rule-based filtering from 4 low-risk scenarios.
NL semantic extraction is deferred to P1.
"""
from __future__ import annotations

import logging

from app.schemas.memory import (
    MemoryContent,
    MemoryScope,
    MemorySource,
    MemoryType,
    MemoryWriteRequest,
    Workspace,
)

logger = logging.getLogger(__name__)

# Keyword patterns for user preference detection
PREFERENCE_KEYWORDS = [
    "以后", "默认", "每次", "总是", "一直", "偏好", "习惯",
    "always", "default", "prefer", "keep",
]

# Minimum content length to be considered a candidate
MIN_SUMMARY_LENGTH = 10
MAX_SUMMARY_LENGTH = 500


class MemoryCandidateService:
    """Extracts candidate memories from agent outputs using rule-based filtering."""

    def __init__(self, org_id: str, user_id: str | None = None):
        self._org_id = org_id
        self._user_id = user_id

    async def extract_from_chat_result(
        self,
        *,
        trace_id: str,
        user_message: str,
        assistant_answer: str,
        task_id: str | None = None,
    ) -> list[MemoryWriteRequest]:
        """Extract candidates from a completed chat exchange."""
        candidates: list[MemoryWriteRequest] = []

        # Scenario 1: User preference detection
        pref_req = self._extract_user_preference(
            trace_id=trace_id,
            user_message=user_message,
        )
        if pref_req:
            candidates.append(pref_req)

        # Scenario 2: Task episode (only when task_id is present)
        if task_id:
            task_req = self._extract_task_episode(
                trace_id=trace_id,
                task_id=task_id,
                user_message=user_message,
                assistant_answer=assistant_answer,
            )
            if task_req:
                candidates.append(task_req)

        return candidates

    async def extract_from_rag_query(
        self,
        *,
        trace_id: str,
        query: str,
        rag_space_id: str,
        hit_count: int = 0,
    ) -> MemoryWriteRequest | None:
        """Extract candidate from a RAG query log."""
        if not rag_space_id or not query.strip():
            return None
        if len(query.strip()) < MIN_SUMMARY_LENGTH:
            return None

        return MemoryWriteRequest(
            org_id=self._org_id,
            user_id=self._user_id,
            workspace=Workspace.APP,
            source=MemorySource(kind="rag", trace_id=trace_id),
            memory_type=MemoryType.RAG_USAGE_MEMORY,
            scope=MemoryScope(rag_space_id=rag_space_id),
            content=MemoryContent(
                summary=f"RAG query: {query.strip()[:MAX_SUMMARY_LENGTH]}",
                facts=[f"hit_count={hit_count}"],
            ),
            confidence=min(hit_count / 10.0, 0.8) if hit_count > 0 else 0.3,
            ttl_policy="30d",
            trace_id=trace_id,
        )

    async def extract_from_governance_action(
        self,
        *,
        trace_id: str,
        action: str,
        rollback_id: str,
        evaluation_id: str | None = None,
        reason: str = "",
    ) -> MemoryWriteRequest | None:
        """Extract candidate from governance rollback/evaluation."""
        return MemoryWriteRequest(
            org_id=self._org_id,
            user_id=self._user_id,
            workspace=Workspace.GOVERNANCE,
            source=MemorySource(kind="human_review", trace_id=trace_id),
            memory_type=MemoryType.GOVERNANCE_MEMORY,
            scope=MemoryScope(),
            content=MemoryContent(
                summary=f"Governance action '{action}' on rollback {rollback_id}: {reason[:200]}",
                risk_notes=[reason] if reason else [],
            ),
            confidence=0.9,
            ttl_policy="never",
            trace_id=trace_id,
        )

    # --- internal helpers ---

    def _extract_user_preference(
        self,
        trace_id: str,
        user_message: str,
    ) -> MemoryWriteRequest | None:
        msg = user_message.strip()
        if len(msg) < MIN_SUMMARY_LENGTH:
            return None
        if not any(kw in msg.lower() for kw in PREFERENCE_KEYWORDS):
            return None

        return MemoryWriteRequest(
            org_id=self._org_id,
            user_id=self._user_id,
            workspace=Workspace.APP,
            source=MemorySource(kind="user", trace_id=trace_id),
            memory_type=MemoryType.USER_PREFERENCE,
            scope=MemoryScope(),
            content=MemoryContent(
                summary=msg[:MAX_SUMMARY_LENGTH],
                preferences=[msg[:200]],
            ),
            confidence=0.6,
            ttl_policy="90d",
            trace_id=trace_id,
        )

    def _extract_task_episode(
        self,
        trace_id: str,
        task_id: str,
        user_message: str,
        assistant_answer: str,
    ) -> MemoryWriteRequest | None:
        summary = assistant_answer.strip()
        if len(summary) < MIN_SUMMARY_LENGTH:
            return None

        return MemoryWriteRequest(
            org_id=self._org_id,
            user_id=self._user_id,
            workspace=Workspace.APP,
            source=MemorySource(kind="agent_message", trace_id=trace_id, task_id=task_id),
            memory_type=MemoryType.TASK_EPISODE,
            scope=MemoryScope(task_id=task_id),
            content=MemoryContent(
                summary=f"Task result: {summary[:MAX_SUMMARY_LENGTH]}",
                facts=[f"query: {user_message[:200]}"],
            ),
            confidence=0.5,
            ttl_policy="30d",
            trace_id=trace_id,
        )
