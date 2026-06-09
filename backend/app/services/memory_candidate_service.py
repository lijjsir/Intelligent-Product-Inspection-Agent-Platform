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
        short_term_memory: dict | None = None,
    ) -> list[MemoryWriteRequest]:
        """Extract candidates from a completed chat exchange."""
        candidates: list[MemoryWriteRequest] = []

        # Scenario 1: User preference detection
        pref_req = self._extract_user_preference(
            trace_id=trace_id,
            user_message=user_message,
            short_term_memory=short_term_memory,
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
                short_term_memory=short_term_memory,
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
        short_term_memory: dict | None = None,
    ) -> MemoryWriteRequest | None:
        msg = self._find_reusable_preference(user_message, short_term_memory)
        if len(msg) < MIN_SUMMARY_LENGTH:
            return None
        evidence = self._short_term_evidence(short_term_memory)
        if msg != user_message.strip():
            evidence["extracted_from"] = "short_term_memory.recent_messages"

        return MemoryWriteRequest(
            org_id=self._org_id,
            user_id=self._user_id,

            source=MemorySource(kind="user", trace_id=trace_id),
            memory_type=MemoryType.USER_PREFERENCE,
            scope=MemoryScope(),
            content=MemoryContent(
                summary=msg[:MAX_SUMMARY_LENGTH],
                preferences=[msg[:200]],
            ),
            evidence_pointers=evidence or None,
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
        short_term_memory: dict | None = None,
    ) -> MemoryWriteRequest | None:
        summary = assistant_answer.strip()
        if len(summary) < MIN_SUMMARY_LENGTH:
            return None
        evidence = self._short_term_evidence(short_term_memory)
        stm_facts = self._short_term_facts(short_term_memory)

        return MemoryWriteRequest(
            org_id=self._org_id,
            user_id=self._user_id,

            source=MemorySource(kind="agent_message", trace_id=trace_id, task_id=task_id),
            memory_type=MemoryType.TASK_EPISODE,
            scope=MemoryScope(task_id=task_id),
            content=MemoryContent(
                summary=f"Task result: {summary[:MAX_SUMMARY_LENGTH]}",
                facts=[f"query: {user_message[:200]}", *stm_facts],
            ),
            evidence_pointers=evidence or None,
            confidence=0.5,
            ttl_policy="30d",
            trace_id=trace_id,
        )

    @staticmethod
    def _find_reusable_preference(user_message: str, short_term_memory: dict | None) -> str:
        current = user_message.strip()
        if MemoryCandidateService._looks_like_preference(current):
            return current

        if not isinstance(short_term_memory, dict):
            return ""

        for message in reversed(list(short_term_memory.get("recent_messages") or [])[-8:]):
            if not isinstance(message, dict):
                continue
            if message.get("role") != "user":
                continue
            content = str(message.get("content") or "").strip()
            if MemoryCandidateService._looks_like_preference(content):
                return content
        return ""

    @staticmethod
    def _looks_like_preference(text: str) -> bool:
        msg = text.strip().lower()
        if len(msg) < MIN_SUMMARY_LENGTH:
            return False
        return any(kw in msg for kw in PREFERENCE_KEYWORDS)

    @staticmethod
    def _short_term_evidence(short_term_memory: dict | None) -> dict:
        if not isinstance(short_term_memory, dict):
            return {}

        evidence: dict = {}
        summary = str(short_term_memory.get("conversation_summary") or "").strip()
        if summary:
            evidence["short_term_summary"] = summary[:500]

        session_facts = short_term_memory.get("session_facts")
        if isinstance(session_facts, dict) and session_facts:
            evidence["short_term_fact_keys"] = sorted(str(key) for key in session_facts.keys())[:20]

        recent_messages = short_term_memory.get("recent_messages")
        if isinstance(recent_messages, list):
            evidence["short_term_recent_count"] = len(recent_messages)

        return evidence

    @staticmethod
    def _short_term_facts(short_term_memory: dict | None) -> list[str]:
        if not isinstance(short_term_memory, dict):
            return []

        facts: list[str] = []
        summary = str(short_term_memory.get("conversation_summary") or "").strip()
        if summary:
            facts.append(f"short_term_summary: {summary[:200]}")

        session_facts = short_term_memory.get("session_facts")
        if isinstance(session_facts, dict):
            for key, value in list(session_facts.items())[:5]:
                facts.append(f"session_fact.{key}: {str(value)[:120]}")
        return facts
