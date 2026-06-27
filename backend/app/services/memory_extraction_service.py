"""Unified facade for extracting shared-memory write candidates."""
from __future__ import annotations

from app.schemas.memory import (
    MemoryContent,
    MemoryScope,
    MemorySource,
    MemoryType,
    MemoryWriteRequest,
)
from app.services.memory_candidate_service import MemoryCandidateService


class MemoryExtractionService:
    """Routes memory extraction for chat, RAG, tool, and inspection sources."""

    def __init__(self, org_id: str, user_id: str | None = None):
        self._org_id = org_id
        self._user_id = user_id
        self._candidate_service = MemoryCandidateService(org_id=org_id, user_id=user_id)

    @staticmethod
    def _is_promotable_from_short_term(candidate: dict, stm: dict | None) -> tuple[bool, str]:
        """Decide whether a short-term candidate qualifies for shared memory promotion."""
        if not stm:
            return True, "no_stm_context"

        memory_type = candidate.get("memory_type", "")
        source = candidate.get("source", {})

        # Never promote unconfirmed pending actions
        if candidate.get("derived_from_pending_action") and not candidate.get("human_confirmed"):
            return False, "pending_action_not_confirmed"

        if memory_type == "user_preference":
            if candidate.get("confidence", 0) >= 0.75:
                return True, "stable_user_preference"
            return False, "low_confidence_user_preference"

        if memory_type == "inspection_pattern":
            if candidate.get("task_id") or candidate.get("product_line"):
                return True, "inspection_pattern_with_scope"
            return False, "missing_inspection_scope"

        if memory_type == "rag_usage_memory":
            if candidate.get("rag_space_id") and candidate.get("evidence_pointers"):
                return True, "rag_usage_with_evidence"
            return False, "missing_rag_evidence"

        if memory_type == "agent_ops_memory":
            if candidate.get("trace_id"):
                return True, "agent_ops_with_trace"
            return False, "missing_trace"

        # Default: allow if confidence is high enough
        if candidate.get("confidence", 0) >= 0.8:
            return True, "high_confidence_default"
        return False, "unsupported_or_low_confidence"

    async def extract_from_chat_result(
        self,
        *,
        trace_id: str,
        user_message: str,
        assistant_answer: str,
        task_id: str | None = None,
        short_term_memory: dict | None = None,
    ) -> list[MemoryWriteRequest]:
        candidates = await self._candidate_service.extract_from_chat_result(
            trace_id=trace_id,
            user_message=user_message,
            assistant_answer=assistant_answer,
            task_id=task_id,
            short_term_memory=short_term_memory,
        )

        # Apply promotion gating
        filtered = []
        for c in candidates:
            candidate_dict = {
                "memory_type": c.memory_type.value if hasattr(c.memory_type, 'value') else str(c.memory_type),
                "confidence": c.confidence,
                "derived_from_pending_action": getattr(c, "derived_from_pending_action", False),
                "human_confirmed": getattr(c, "human_confirmed", False),
                "task_id": c.scope.task_id if c.scope and hasattr(c.scope, 'task_id') else None,
                "product_line": c.scope.product_line if c.scope and hasattr(c.scope, 'product_line') else None,
                "rag_space_id": c.scope.rag_space_id if c.scope and hasattr(c.scope, 'rag_space_id') else None,
                "evidence_pointers": c.evidence_pointers,
                "trace_id": c.trace_id,
            }
            promotable, reason = self._is_promotable_from_short_term(candidate_dict, short_term_memory)
            if promotable:
                if c.evidence_pointers is None:
                    c.evidence_pointers = {}
                c.evidence_pointers["promotion_reason"] = reason
                filtered.append(c)

        return filtered

    async def extract_from_rag_query(
        self,
        *,
        trace_id: str,
        query: str,
        rag_space_id: str,
        hit_count: int = 0,
    ) -> MemoryWriteRequest | None:
        return await self._candidate_service.extract_from_rag_query(
            trace_id=trace_id,
            query=query,
            rag_space_id=rag_space_id,
            hit_count=hit_count,
        )

    async def extract_from_tool_result(
        self,
        *,
        trace_id: str,
        tool_name: str,
        result_summary: str,
        task_id: str | None = None,
        confidence: float = 0.5,
    ) -> MemoryWriteRequest | None:
        summary = result_summary.strip()
        if len(summary) < 10:
            return None
        return MemoryWriteRequest(
            org_id=self._org_id,
            user_id=self._user_id,
            source=MemorySource(kind="tool", trace_id=trace_id, task_id=task_id, agent_id=tool_name),
            memory_type=MemoryType.AGENT_OPS_MEMORY,
            scope=MemoryScope(task_id=task_id) if task_id else MemoryScope(),
            content=MemoryContent(
                summary=f"Tool result from {tool_name}: {summary[:500]}",
                facts=[summary[:200]],
            ),
            evidence_pointers={"tool_name": tool_name},
            confidence=max(0.0, min(1.0, confidence)),
            ttl_policy="30d",
            trace_id=trace_id,
        )

    async def extract_from_inspection_pattern(
        self,
        *,
        trace_id: str,
        product_line: str,
        pattern_summary: str,
        confidence: float = 0.6,
    ) -> MemoryWriteRequest | None:
        summary = pattern_summary.strip()
        if not product_line.strip() or len(summary) < 10:
            return None
        return MemoryWriteRequest(
            org_id=self._org_id,
            user_id=self._user_id,
            source=MemorySource(kind="agent_message", trace_id=trace_id),
            memory_type=MemoryType.INSPECTION_PATTERN,
            scope=MemoryScope(product_line=product_line.strip()),
            content=MemoryContent(summary=summary[:500], facts=[summary[:200]]),
            confidence=max(0.0, min(1.0, confidence)),
            ttl_policy="90d",
            trace_id=trace_id,
        )

    async def extract_from_governance_action(self, **kwargs) -> MemoryWriteRequest | None:
        return await self._candidate_service.extract_from_governance_action(**kwargs)
