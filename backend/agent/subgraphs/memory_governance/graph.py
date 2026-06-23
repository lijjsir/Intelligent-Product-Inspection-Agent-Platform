from __future__ import annotations

from langgraph.graph import END, StateGraph

from agent.subgraphs.memory_governance.state import MemoryGovernanceState
from agent.subgraphs.memory_governance.nodes import (
    input_adapter,
    legacy_memory_manager_node,
    normalize_governance_result,
    finalize,
)


class MemoryGovernanceGraph:
    """Memory Governance LangGraph subgraph.

    Phase 1: wraps legacy MemoryManagerGraph as a formal graph node.
    """

    def __init__(self) -> None:
        graph = StateGraph(MemoryGovernanceState)
        graph.add_node("input_adapter", input_adapter)
        graph.add_node("legacy_memory_manager", legacy_memory_manager_node)
        graph.add_node("normalize_governance_result", normalize_governance_result)
        graph.add_node("finalize", finalize)

        graph.set_entry_point("input_adapter")
        graph.add_edge("input_adapter", "legacy_memory_manager")
        graph.add_edge("legacy_memory_manager", "normalize_governance_result")
        graph.add_edge("normalize_governance_result", "finalize")
        graph.add_edge("finalize", END)

        self._graph = graph.compile()

    async def run(self, state: MemoryGovernanceState) -> MemoryGovernanceState:
        return await self._graph.ainvoke(state)
