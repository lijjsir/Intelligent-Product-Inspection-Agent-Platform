"""Tool Result vs Memory conflict detector — rule-based only."""
from __future__ import annotations


STATUS_CONFLICT_PAIRS = [
    (["completed", "done", "finished", "已完成", "完成", "success", "通过", "合格", "active", "enabled", "启用", "开启"],
     ["running", "pending", "进行中", "排队中", "failed", "error", "失败", "不合格", "inactive", "disabled", "禁用", "关闭"]),
]


class ToolMemoryDetector:
    """Detects conflicts between real-time tool results and shared memory.

    Rule: real-time tool result > historical memory.
    """

    def detect(
        self,
        tool_results: list[dict] | None,
        memory_hits: list[dict],
    ) -> dict:
        """Check tool results against memory items."""
        conflicts: list[dict] = []
        suppressed: set[str] = set()

        if not tool_results:
            return {"conflicts": conflicts, "suppressed_memory_ids": list(suppressed)}

        for mem in memory_hits:
            mem_summary = str(mem.get("summary", "")).lower()
            for tool in tool_results:
                tool_output = str(tool.get("output", "") or tool.get("result", "") or "").lower()
                if not tool_output:
                    continue

                for positive_terms, negative_terms in STATUS_CONFLICT_PAIRS:
                    mem_pos = any(t in mem_summary for t in positive_terms)
                    mem_neg = any(t in mem_summary for t in negative_terms)
                    tool_pos = any(t in tool_output for t in positive_terms)
                    tool_neg = any(t in tool_output for t in negative_terms)

                    if mem_pos and tool_neg:
                        conflicts.append({
                            "type": "tool_vs_memory",
                            "memory_id": mem.get("memory_id", ""),
                            "tool_name": tool.get("name", tool.get("tool", "")),
                            "verdict": "conflict",
                            "confidence": 0.85,
                            "reason": "Memory says positive status but tool result shows negative/failure.",
                            "source": "rule",
                        })
                        suppressed.add(mem.get("memory_id", ""))
                        break
                    if mem_neg and tool_pos:
                        conflicts.append({
                            "type": "tool_vs_memory",
                            "memory_id": mem.get("memory_id", ""),
                            "tool_name": tool.get("name", tool.get("tool", "")),
                            "verdict": "conflict",
                            "confidence": 0.80,
                            "reason": "Memory says negative/failure but tool result shows success.",
                            "source": "rule",
                        })
                        suppressed.add(mem.get("memory_id", ""))
                        break

        return {
            "conflicts": conflicts,
            "suppressed_memory_ids": list(suppressed),
        }
