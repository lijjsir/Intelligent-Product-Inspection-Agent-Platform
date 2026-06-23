from __future__ import annotations

from time import perf_counter
from typing import Any

from langgraph.graph import END, StateGraph

from agent.subgraphs.quality_analysis.state import QualityAnalysisState
from agent.subgraphs.quality_analysis.nodes import (
    context_assembler,
    validate_required_inputs,
    choose_response_mode,
    llm_quality_reasoning,
    standard_gate,
    build_report,
    maybe_persist_task_result,
    memory_candidate_hook,
    finalize_response,
)


def _route_after_validate(state: dict[str, Any]) -> str:
    if state.get("needs_user_input"):
        return "finalize_response"
    return "choose_response_mode"


def _route_after_report(state: dict[str, Any]) -> str:
    if state.get("surface") == "quality_task":
        return "maybe_persist_task_result"
    return "memory_candidate_hook"


class QualityAnalysisGraph:
    """质量分析 LangGraph 子图。

    聚合证据、视觉、实验室检测结果，生成最终质量评估和用户回复。
    支持三种模式：general_answer（普通聊天）、quality_qa（综合分析）、
    inspection_execute（正式任务执行+落库）。
    """

    def __init__(self) -> None:
        graph = StateGraph(QualityAnalysisState)

        graph.add_node("context_assembler", context_assembler)
        graph.add_node("validate_required_inputs", validate_required_inputs)
        graph.add_node("choose_response_mode", choose_response_mode)
        graph.add_node("llm_quality_reasoning", llm_quality_reasoning)
        graph.add_node("standard_gate", standard_gate)
        graph.add_node("build_report", build_report)
        graph.add_node("maybe_persist_task_result", maybe_persist_task_result)
        graph.add_node("memory_candidate_hook", memory_candidate_hook)
        graph.add_node("finalize_response", finalize_response)

        graph.set_entry_point("context_assembler")
        graph.add_edge("context_assembler", "validate_required_inputs")
        graph.add_conditional_edges(
            "validate_required_inputs",
            _route_after_validate,
            {"finalize_response": "finalize_response", "choose_response_mode": "choose_response_mode"},
        )
        graph.add_edge("choose_response_mode", "llm_quality_reasoning")
        graph.add_edge("llm_quality_reasoning", "standard_gate")
        graph.add_edge("standard_gate", "build_report")
        graph.add_conditional_edges(
            "build_report",
            _route_after_report,
            {
                "maybe_persist_task_result": "maybe_persist_task_result",
                "memory_candidate_hook": "memory_candidate_hook",
            },
        )
        graph.add_edge("maybe_persist_task_result", "memory_candidate_hook")
        graph.add_edge("memory_candidate_hook", "finalize_response")
        graph.add_edge("finalize_response", END)

        self._graph = graph.compile()

    async def run(self, state: QualityAnalysisState | dict[str, Any]) -> dict:
        started_at = perf_counter()
        state = dict(state)
        state.setdefault("status", "running")
        state.setdefault("summary", "")

        result = await self._graph.ainvoke(state)
        result.setdefault("metadata", {})
        result["metadata"]["latency_ms"] = round((perf_counter() - started_at) * 1000)
        result["metadata"]["graph_name"] = "QualityAnalysisGraph"
        return result
