"""RetrievalConflictGuard — orchestrates conflict detection during retrieval phase.

Runs after RAG + Memory retrieval, before agent context assembly.
Phase 1: does NOT persist conflicts to DB or modify memory.status.
"""
from __future__ import annotations

import logging

from app.services.conflict_detectors.rag_memory_detector import RagMemoryDetector
from app.services.conflict_detectors.session_memory_detector import SessionMemoryDetector
from app.services.conflict_detectors.tool_memory_detector import ToolMemoryDetector
from app.services.conflict_detectors.memory_memory_detector import MemoryMemoryDetector

logger = logging.getLogger(__name__)


class RetrievalConflictGuard:
    """Lightweight conflict detection during retrieval phase.

    Input: RAG hits + Memory hits + Session facts + Tool results
    Output: filtered/ranked context ready for agent injection.
    """

    def __init__(
        self,
        org_id: str,
        user_id: str | None = None,
        trace_id: str | None = None,
    ):
        self._org_id = org_id
        self._user_id = user_id
        self._trace_id = trace_id
        self._rag_memory = RagMemoryDetector(org_id, user_id, trace_id)
        self._session_memory = SessionMemoryDetector()
        self._tool_memory = ToolMemoryDetector()
        self._memory_memory = MemoryMemoryDetector(org_id, user_id, trace_id)

    async def check(
        self,
        query: str,
        rag_hits: list[dict],
        memory_hits: list[dict],
        session_facts: dict | None = None,
        tool_results: list[dict] | None = None,
    ) -> dict:
        """Run all conflict detectors and return filtered results."""
        conflicts: list[dict] = []
        suppressed_memory_ids: set[str] = set()
        downranked_memory_ids: set[str] = set()
        warnings: list[str] = []

        # 1. Session vs Memory (highest priority)
        session_result = self._session_memory.detect(
            session_facts=session_facts,
            memory_hits=memory_hits,
        )
        conflicts.extend(session_result["conflicts"])
        suppressed_memory_ids.update(session_result["suppressed_memory_ids"])

        # 2. Tool vs Memory
        tool_result = self._tool_memory.detect(
            tool_results=tool_results,
            memory_hits=memory_hits,
        )
        conflicts.extend(tool_result["conflicts"])
        suppressed_memory_ids.update(tool_result["suppressed_memory_ids"])

        # 3. RAG vs Memory
        rag_memory_result = await self._rag_memory.detect(
            query=query,
            rag_hits=rag_hits,
            memory_hits=memory_hits,
        )
        conflicts.extend(rag_memory_result["conflicts"])
        suppressed_memory_ids.update(rag_memory_result["suppressed_memory_ids"])
        downranked_memory_ids.update(rag_memory_result["downranked_memory_ids"])

        # 4. Memory vs Memory
        memory_result = self._memory_memory.detect(memory_hits)
        conflicts.extend(memory_result["conflicts"])
        downranked_memory_ids.update(memory_result["downranked_memory_ids"])

        # 5. RAG vs RAG — prefer higher score / newer / more authoritative
        rag_rag_conflicts = self._check_rag_rag(rag_hits)
        conflicts.extend(rag_rag_conflicts)

        # Filter suppressed memories
        clean_memory_hits = [
            m for m in memory_hits
            if m.get("memory_id") not in suppressed_memory_ids
        ]

        # Apply downrank: move downranked items to end with score penalty
        clean_memory_hits = self._apply_downrank(clean_memory_hits, downranked_memory_ids)

        if suppressed_memory_ids:
            warnings.append(f"suppressed {len(suppressed_memory_ids)} memories due to conflicts")
        if downranked_memory_ids:
            warnings.append(f"downranked {len(downranked_memory_ids)} memories")

        return {
            "rag_hits": rag_hits,
            "memory_hits": clean_memory_hits,
            "conflicts": conflicts,
            "suppressed_memory_ids": list(suppressed_memory_ids),
            "downranked_memory_ids": list(downranked_memory_ids),
            "warnings": warnings,
        }

    def check_sync(
        self,
        query: str,
        memory_hits: list[dict],
        session_facts: dict | None = None,
        tool_results: list[dict] | None = None,
    ) -> dict:
        """Synchronous check (no RAG, no LLM). For quick inline use."""
        conflicts: list[dict] = []
        suppressed: set[str] = set()
        downranked: set[str] = set()

        session_result = self._session_memory.detect(session_facts, memory_hits)
        conflicts.extend(session_result["conflicts"])
        suppressed.update(session_result["suppressed_memory_ids"])

        tool_result = self._tool_memory.detect(tool_results, memory_hits)
        conflicts.extend(tool_result["conflicts"])
        suppressed.update(tool_result["suppressed_memory_ids"])

        memory_result = self._memory_memory.detect(memory_hits)
        conflicts.extend(memory_result["conflicts"])
        downranked.update(memory_result["downranked_memory_ids"])

        clean = [m for m in memory_hits if m.get("memory_id") not in suppressed]
        clean = self._apply_downrank(clean, downranked)

        warnings: list[str] = []
        if suppressed:
            warnings.append(f"suppressed {len(suppressed)} memories due to conflicts")
        if downranked:
            warnings.append(f"downranked {len(downranked)} memories")

        return {
            "memory_hits": clean,
            "conflicts": conflicts,
            "suppressed_memory_ids": list(suppressed),
            "downranked_memory_ids": list(downranked),
            "warnings": warnings,
        }

    @staticmethod
    def _check_rag_rag(rag_hits: list[dict]) -> list[dict]:
        """RAG vs RAG: prefer higher score, more authoritative, newer documents.

        Marks lower-quality RAG hits that contradict higher-quality ones as `rag_vs_rag` conflicts.
        """
        conflicts: list[dict] = []
        if len(rag_hits) < 2:
            return conflicts

        sorted_hits = sorted(
            rag_hits,
            key=lambda r: (
                -float(r.get("score", 0) or 0),
                -(r.get("page_number") or 0),
            ),
        )
        best = sorted_hits[0]
        best_score = float(best.get("score", 0) or 0)

        for other in sorted_hits[1:]:
            other_score = float(other.get("score", 0) or 0)
            if best_score > 0 and (best_score - other_score) / best_score > 0.4:
                conflicts.append({
                    "type": "rag_vs_rag",
                    "preferred_chunk_id": best.get("id", best.get("chunk_id", "")),
                    "downranked_chunk_id": other.get("id", other.get("chunk_id", "")),
                    "verdict": "prefer_higher_score",
                    "confidence": 0.7,
                    "reason": f"RAG chunk score {other_score} significantly lower than best {best_score}.",
                    "source": "rule",
                })

        return conflicts

    @staticmethod
    def _apply_downrank(memory_hits: list[dict], downranked_ids: set[str]) -> list[dict]:
        """Move downranked items to end and halve their scores."""
        normal = []
        lowered = []
        for m in memory_hits:
            if m.get("memory_id") in downranked_ids:
                m = dict(m)
                m["score"] = float(m.get("score", 0) or 0) * 0.5
                lowered.append(m)
            else:
                normal.append(m)
        return normal + lowered
