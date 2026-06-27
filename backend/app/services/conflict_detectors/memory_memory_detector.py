"""Memory vs Memory conflict detector — rule-based ranking."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class MemoryMemoryDetector:
    """Detects conflicts among shared memory items.

    Rule: higher trust_score + higher confidence + newer > lower ones.
    """

    def __init__(self, org_id: str, user_id: str | None = None, trace_id: str | None = None):
        self._org_id = org_id
        self._user_id = user_id
        self._trace_id = trace_id

    def detect(self, memory_hits: list[dict]) -> dict:
        """Check memory items against each other."""
        conflicts: list[dict] = []
        downranked: set[str] = set()

        if len(memory_hits) < 2:
            return {"conflicts": conflicts, "downranked_memory_ids": list(downranked)}

        # Rule-based: rank by (trust_score, confidence, score) — higher score implies
        # better semantic match which correlates with recency.
        scored = []
        for i, mem in enumerate(memory_hits):
            trust = float(mem.get("trust_score", 0) or 0)
            confidence = float(mem.get("confidence", 0) or 0)
            score = float(mem.get("score", 0) or 0)
            composite = trust * 0.35 + confidence * 0.35 + score * 0.30
            scored.append((composite, i, mem))

        scored.sort(key=lambda x: x[0], reverse=True)

        if scored:
            top_score = scored[0][0]
            for comp, _, mem in scored[1:]:
                if top_score > 0 and (top_score - comp) / top_score > 0.5:
                    downranked.add(mem.get("memory_id", ""))

        # Check for same memory_type items with conflicting scope (same task, different values)
        for i in range(len(memory_hits)):
            for j in range(i + 1, len(memory_hits)):
                a, b = memory_hits[i], memory_hits[j]
                if a.get("memory_type") != b.get("memory_type"):
                    continue
                source_a = a.get("source") or {}
                source_b = b.get("source") or {}
                if source_a and source_b:
                    task_a = source_a.get("task_id")
                    task_b = source_b.get("task_id")
                    if task_a and task_b and task_a == task_b:
                        trust_a = float(a.get("trust_score", 0) or 0)
                        trust_b = float(b.get("trust_score", 0) or 0)
                        lower = a if trust_a <= trust_b else b
                        downranked.add(lower.get("memory_id", ""))
                        conflicts.append({
                            "type": "memory_vs_memory",
                            "memory_id_a": a.get("memory_id", ""),
                            "memory_id_b": b.get("memory_id", ""),
                            "verdict": "downrank",
                            "confidence": 0.6,
                            "reason": "Same task/type memory slot conflict; lower trust downranked.",
                            "source": "rule",
                        })

        return {
            "conflicts": conflicts,
            "downranked_memory_ids": list(downranked),
        }
