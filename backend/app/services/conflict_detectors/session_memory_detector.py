"""Session vs Memory conflict detector — lightweight rule-based only."""
from __future__ import annotations


class SessionMemoryDetector:
    """Detects conflicts between current session/user instructions and shared memory.

    Rule: current user instruction > long-term preference memory.
    """

    def detect(
        self,
        session_facts: dict | None,
        memory_hits: list[dict],
    ) -> dict:
        """Check session facts against memory items."""
        conflicts: list[dict] = []
        suppressed: set[str] = set()

        if not session_facts:
            return {"conflicts": conflicts, "suppressed_memory_ids": list(suppressed)}

        explicit_instructions = session_facts.get("explicit_instructions", [])
        if not explicit_instructions:
            return {"conflicts": conflicts, "suppressed_memory_ids": list(suppressed)}

        for mem in memory_hits:
            mem_type = str(mem.get("memory_type", ""))
            if mem_type != "user_preference":
                continue

            mem_summary = str(mem.get("summary", "")).lower()
            for instruction in explicit_instructions:
                inst_lower = str(instruction).lower()
                contradiction_keywords = ["instead", "不要", "忽略", "这次", "override", "本次"]
                if any(kw in inst_lower for kw in contradiction_keywords):
                    conflicts.append({
                        "type": "session_vs_memory",
                        "memory_id": mem.get("memory_id", ""),
                        "instruction": instruction,
                        "verdict": "conflict",
                        "confidence": 0.9,
                        "reason": "Session instruction explicitly overrides prior preferences.",
                        "source": "rule",
                    })
                    suppressed.add(mem.get("memory_id", ""))

        return {
            "conflicts": conflicts,
            "suppressed_memory_ids": list(suppressed),
        }
