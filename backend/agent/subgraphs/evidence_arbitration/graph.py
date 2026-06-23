from __future__ import annotations

from time import perf_counter
from typing import Any

from langgraph.graph import END, StateGraph

from agent.subgraphs.evidence_arbitration.state import EvidenceArbitrationState
from agent.subgraphs.evidence_arbitration.nodes import (
    query_intake,
    retrieve_rag_context,
    retrieve_shared_memory_context,
    retrieve_kg_context,
    normalize_evidence,
    llm_conflict_arbitration,
    build_evidence_packet,
)


class EvidenceArbitrationGraph:
    """统一的证据检索与冲突裁决 LangGraph 子图。

    负责 RAG、共享记忆、知识图谱检索，并进行证据冲突裁决。
    输出 evidence_packet artifact 供下游 Agent 使用。
    """

    def __init__(self) -> None:
        graph = StateGraph(EvidenceArbitrationState)

        graph.add_node("query_intake", query_intake)
        graph.add_node("retrieve_rag_context", retrieve_rag_context)
        graph.add_node("retrieve_shared_memory_context", retrieve_shared_memory_context)
        graph.add_node("retrieve_kg_context", retrieve_kg_context)
        graph.add_node("normalize_evidence", normalize_evidence)
        graph.add_node("llm_conflict_arbitration", llm_conflict_arbitration)
        graph.add_node("build_evidence_packet", build_evidence_packet)

        graph.set_entry_point("query_intake")
        graph.add_edge("query_intake", "retrieve_rag_context")
        graph.add_edge("retrieve_rag_context", "retrieve_shared_memory_context")
        graph.add_edge("retrieve_shared_memory_context", "retrieve_kg_context")
        graph.add_edge("retrieve_kg_context", "normalize_evidence")
        graph.add_edge("normalize_evidence", "llm_conflict_arbitration")
        graph.add_edge("llm_conflict_arbitration", "build_evidence_packet")
        graph.add_edge("build_evidence_packet", END)

        self._graph = graph.compile()

    async def run(self, state: EvidenceArbitrationState | dict[str, Any]) -> dict:
        started_at = perf_counter()
        state = dict(state)
        state.setdefault("status", "running")
        state.setdefault("summary", "")

        result = await self._graph.ainvoke(state)
        result.setdefault("metadata", {})
        result["metadata"]["latency_ms"] = round((perf_counter() - started_at) * 1000)
        result["metadata"]["graph_name"] = "EvidenceArbitrationGraph"
        return result
