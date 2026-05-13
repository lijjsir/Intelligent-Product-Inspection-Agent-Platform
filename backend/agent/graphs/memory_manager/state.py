"""MemoryAgentState - shared state for the MemoryManagerAgent graph."""
from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages

from agent.graphs.memory_manager.reducers import (
    dependency_edge_reducer,
    event_reducer,
    memory_reducer,
)


class MemoryAgentState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    task_context: dict[str, Any]
    agent_outputs: dict[str, dict[str, Any]]
    structured_memory: Annotated[list[dict[str, Any]], memory_reducer]
    memory_context: dict[str, Any]
    memory_events: Annotated[list[dict[str, Any]], event_reducer]
    dependency_edges: Annotated[list[dict[str, Any]], dependency_edge_reducer]
    contamination_alerts: list[dict[str, Any]]
    propagation_graph: dict[str, Any]
    rollback_plan: dict[str, Any]
    evaluation_result: dict[str, Any]
    final_result: dict[str, Any]
