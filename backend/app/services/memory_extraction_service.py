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

    async def extract_from_chat_result(
        self,
        *,
        trace_id: str,
        user_message: str,
        assistant_answer: str,
        task_id: str | None = None,
        short_term_memory: dict | None = None,
    ) -> list[MemoryWriteRequest]:
        return await self._candidate_service.extract_from_chat_result(
            trace_id=trace_id,
            user_message=user_message,
            assistant_answer=assistant_answer,
            task_id=task_id,
            short_term_memory=short_term_memory,
        )

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
