from __future__ import annotations

from time import perf_counter
from typing import Any

from langgraph.graph import END, StateGraph

from agent.subgraphs.lab_detection.state import LabDetectionState
from agent.subgraphs.lab_detection.nodes import (
    input_adapter,
    validate_lab_context,
    normalize_measurements,
    load_reference_context,
    compute_anomaly_features,
    llm_early_risk_reasoning,
    recommend_next_tests,
    finalize_assessment,
)


class LabDetectionGraph:
    """独立的实验室检测早期异常研判 LangGraph 子图 Agent。

    当前阶段：
    - 不注册 capability
    - 不接入 InspectionTask
    - 不接入 ManagerDispatcher
    - 只作为可独立运行和测试的子图 Agent
    """

    def __init__(self) -> None:
        graph = StateGraph(LabDetectionState)

        graph.add_node("input_adapter", input_adapter)
        graph.add_node("validate_lab_context", validate_lab_context)
        graph.add_node("normalize_measurements", normalize_measurements)
        graph.add_node("load_reference_context", load_reference_context)
        graph.add_node("compute_anomaly_features", compute_anomaly_features)
        graph.add_node("llm_early_risk_reasoning", llm_early_risk_reasoning)
        graph.add_node("recommend_next_tests", recommend_next_tests)
        graph.add_node("finalize_assessment", finalize_assessment)

        graph.set_entry_point("input_adapter")
        graph.add_edge("input_adapter", "validate_lab_context")
        graph.add_edge("validate_lab_context", "normalize_measurements")
        graph.add_edge("normalize_measurements", "load_reference_context")
        graph.add_edge("load_reference_context", "compute_anomaly_features")
        graph.add_edge("compute_anomaly_features", "llm_early_risk_reasoning")
        graph.add_edge("llm_early_risk_reasoning", "recommend_next_tests")
        graph.add_edge("recommend_next_tests", "finalize_assessment")
        graph.add_edge("finalize_assessment", END)

        self._graph = graph.compile()

    async def run(self, state: LabDetectionState | dict[str, Any]) -> LabDetectionState:
        started_at = perf_counter()
        state = dict(state)
        state.setdefault("schema_version", "1.0.0")
        state.setdefault("workflow_version", "lab_detection_v1")
        state.setdefault("metadata", {})
        state["metadata"]["agent"] = "lab_detection"
        state["metadata"]["graph_name"] = "LabDetectionGraph"

        result = await self._graph.ainvoke(state)
        result.setdefault("metadata", {})
        result["metadata"]["latency_ms"] = round((perf_counter() - started_at) * 1000)
        return result
