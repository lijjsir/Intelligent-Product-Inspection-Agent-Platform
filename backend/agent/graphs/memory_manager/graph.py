"""MemoryManagerGraph - unified parent graph with governance loop.

Entry graph for the memory_manager graph.
Registered in topology_catalog.py as:
  - subgraph_key: memory_manager
  - entry_graph: MemoryManagerGraph
  - graph_version: v2
"""
from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import END, StateGraph

from agent.graphs.memory_manager.nodes import (
    contamination_monitor_node,
    governance_recovery_agent,
    manager_route_policy,
    memory_context_loader,
    propagation_graph_node,
    provenance_node,
    replay_evaluation_node,
    request_intake,
    result_synthesizer,
    rollback_planner_node,
)
from agent.graphs.memory_manager.state import MemoryAgentState


def build_graph() -> StateGraph:
    """Build and return the compiled MemoryAgentState graph."""
    builder = StateGraph(MemoryAgentState)

    # Core nodes
    builder.add_node("request_intake", request_intake)
    builder.add_node("memory_context_loader", memory_context_loader)
    builder.add_node("manager_route_policy", manager_route_policy)

    # Governance branch nodes
    builder.add_node("contamination_monitor_node", contamination_monitor_node)
    builder.add_node("provenance_node", provenance_node)
    builder.add_node("propagation_graph_node", propagation_graph_node)
    builder.add_node("rollback_planner_node", rollback_planner_node)
    builder.add_node("governance_recovery_agent", governance_recovery_agent)
    builder.add_node("replay_evaluation_node", replay_evaluation_node)
    builder.add_node("result_synthesizer", result_synthesizer)

    # Edges
    builder.set_entry_point("request_intake")
    builder.add_edge("request_intake", "memory_context_loader")
    builder.add_edge("memory_context_loader", "manager_route_policy")
    builder.add_edge("manager_route_policy", "contamination_monitor_node")

    # Conditional: alert -> governance branch, else -> result
    builder.add_conditional_edges(
        "contamination_monitor_node",
        _has_contamination_alert,
        {
            "governance": "provenance_node",
            "clean": "result_synthesizer",
        },
    )

    # Governance loop
    builder.add_edge("provenance_node", "propagation_graph_node")
    builder.add_edge("propagation_graph_node", "rollback_planner_node")
    builder.add_edge("rollback_planner_node", "governance_recovery_agent")
    builder.add_edge("governance_recovery_agent", "replay_evaluation_node")
    builder.add_edge("replay_evaluation_node", "result_synthesizer")
    builder.add_edge("result_synthesizer", END)

    return builder


def _has_contamination_alert(state: MemoryAgentState) -> Literal["governance", "clean"]:
    """Route to governance branch if contamination alerts exist."""
    alerts = state.get("contamination_alerts", [])
    manager = state.get("agent_outputs", {}).get("manager", {})
    if alerts or manager.get("has_alert"):
        return "governance"
    return "clean"


class MemoryManagerGraph:
    """Unified parent graph — renamed from SharedMemoryHierarchyGraph."""

    def __init__(self):
        self._graph = build_graph()

    def compile(self, checkpointer=None):
        return self._graph.compile(checkpointer=checkpointer)

    @property
    def builder(self) -> StateGraph:
        return self._graph


def make_checkpointer():
    """Create a MySQL-backed checkpointer for MemoryManagerGraph."""
    from infra.database.session import create_session
    from agent.graphs.memory_manager.checkpointer import MySQLCheckpointer

    async def session_factory():
        return create_session()

    return MySQLCheckpointer(session_factory)
