from __future__ import annotations

"""Tests for base_graph_state correctness and completeness per 6-agent-langgraph guide Section 4.1."""

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import AgentPlanStep
from agent.router.executors.graph_executor import GraphExecutor
from agent.router.manager_state import ManagerState


def _request(**overrides) -> NormalizedRequest:
    payload = {
        "request_id": "req-gs-1",
        "workflow_run_id": "wf-gs-1",
        "org_id": "org-1",
        "user_id": "user-1",
        "session_id": "session-1",
        "query": "test query",
        "ext": {"surface": "chat", "selected_rag_space": "rag-1"},
        "metadata": {"product_id": "P001"},
    }
    payload.update(overrides)
    return NormalizedRequest(**payload)


def _state(**overrides) -> ManagerState:
    payload = {
        "request_id": "req-gs-1",
        "workflow_run_id": "wf-gs-1",
        "original_query": "test query",
        "org_id": "org-1",
        "user_id": "user-1",
        "session_id": "session-1",
        "surface": "chat",
        "selected_agent": "evidence",
    }
    payload.update(overrides)
    return ManagerState(**payload)


def _step(**overrides) -> AgentPlanStep:
    payload = {
        "step_id": "step-gs-1",
        "owner_agent": "evidence",
        "capability": "evidence.arbitrate",
    }
    payload.update(overrides)
    return AgentPlanStep(**payload)


def test_base_graph_state_contains_request_manager_state_and_artifacts():
    """Section 4.1: graph state must include request, manager_state, and artifacts."""
    graph_state = GraphExecutor.base_graph_state(_state(), _request(), _step())

    assert "request" in graph_state
    assert "manager_state" in graph_state
    assert "artifacts" in graph_state
    assert "step" in graph_state
    assert graph_state["step"]["step_id"] == "step-gs-1"


def test_base_graph_state_manager_state_has_all_required_fields():
    """Manager state sub-dict must expose all routing and context fields."""
    graph_state = GraphExecutor.base_graph_state(_state(), _request(), _step())
    mgr = graph_state["manager_state"]

    assert mgr["request_id"] == "req-gs-1"
    assert mgr["workflow_run_id"] == "wf-gs-1"
    assert mgr["session_id"] == "session-1"
    assert mgr["org_id"] == "org-1"
    assert mgr["user_id"] == "user-1"
    assert mgr["surface"] == "chat"
    assert mgr["original_query"] == "test query"
    assert mgr["selected_agent"] == "evidence"
    assert isinstance(mgr["attachments"], list)
    assert isinstance(mgr["artifacts"], list)


def test_base_graph_state_request_field_matches_request_model():
    """Request dict must mirror NormalizedRequest fields."""
    graph_state = GraphExecutor.base_graph_state(_state(), _request(), _step())
    req = graph_state["request"]

    assert req["request_id"] == "req-gs-1"
    assert req["query"] == "test query"
    assert req["org_id"] == "org-1"
    assert isinstance(req["ext"], dict)
    assert isinstance(req["metadata"], dict)


def test_base_graph_state_preserves_attachments():
    """Attachments from ManagerState must be passed through."""
    state = _state(attachments=[{"kind": "image", "name": "test.png"}])
    graph_state = GraphExecutor.base_graph_state(state, _request(), _step())

    assert len(graph_state["attachments"]) == 1
    assert graph_state["attachments"][0]["kind"] == "image"


def test_base_graph_state_surface_defaults_to_chat():
    """When surface is default (empty string), base_graph_state defaults to 'chat'."""
    state = _state(surface="")
    graph_state = GraphExecutor.base_graph_state(state, _request(), _step())

    assert graph_state["surface"] == "chat"


def test_base_graph_state_query_falls_back_to_request():
    """When original_query is empty, fall back to request.query."""
    state = _state(original_query="")
    graph_state = GraphExecutor.base_graph_state(state, _request(query="fallback query"), _step())

    assert graph_state["query"] == "fallback query"
