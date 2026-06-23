from __future__ import annotations

from langgraph.graph import END, StateGraph

from agent.subgraphs.vision_inspection.state import VisionInspectionState
from agent.subgraphs.vision_inspection.nodes import (
    input_adapter,
    legacy_vision_understanding_node,
    normalize_visual_result,
    finalize,
)


class VisionInspectionGraph:
    """Vision Inspection LangGraph subgraph.

    Phase 1: wraps the legacy VisionUnderstandingHandler as a formal graph node.
    Phase 2: replaces legacy node with image_quality_check → defect_localization →
             visual_evidence_alignment pipeline.
    """

    def __init__(self) -> None:
        graph = StateGraph(VisionInspectionState)
        graph.add_node("input_adapter", input_adapter)
        graph.add_node("legacy_vision_understanding", legacy_vision_understanding_node)
        graph.add_node("normalize_visual_result", normalize_visual_result)
        graph.add_node("finalize", finalize)

        graph.set_entry_point("input_adapter")
        graph.add_edge("input_adapter", "legacy_vision_understanding")
        graph.add_edge("legacy_vision_understanding", "normalize_visual_result")
        graph.add_edge("normalize_visual_result", "finalize")
        graph.add_edge("finalize", END)

        self._graph = graph.compile()

    async def run(self, state: VisionInspectionState) -> VisionInspectionState:
        return await self._graph.ainvoke(state)
