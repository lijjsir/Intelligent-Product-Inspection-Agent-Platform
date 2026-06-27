from __future__ import annotations

"""Tests for manager_model_runtime injection into GraphExecutor.base_graph_state()
per agent-manager-error-observability-fix-guide Section 5.1."""

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import AgentPlanStep
from agent.router.executors.graph_executor import GraphExecutor
from agent.router.manager_state import ManagerState


def _request(**overrides) -> NormalizedRequest:
    payload = {
        "request_id": "req-grt-1",
        "workflow_run_id": "wf-grt-1",
        "org_id": "org-1",
        "user_id": "user-1",
        "session_id": "session-1",
        "query": "test query",
        "ext": {"surface": "chat"},
        "metadata": {},
    }
    payload.update(overrides)
    return NormalizedRequest(**payload)


def _state(**overrides) -> ManagerState:
    payload = {
        "request_id": "req-grt-1",
        "workflow_run_id": "wf-grt-1",
        "original_query": "test query",
        "org_id": "org-1",
        "user_id": "user-1",
        "session_id": "session-1",
        "surface": "chat",
        "selected_agent": "quality_analysis",
    }
    payload.update(overrides)
    return ManagerState(**payload)


def _step(**overrides) -> AgentPlanStep:
    payload = {
        "step_id": "step-grt-1",
        "owner_agent": "quality_analysis",
        "capability": "quality.final_analyze",
    }
    payload.update(overrides)
    return AgentPlanStep(**payload)


def test_base_graph_state_includes_model_runtime():
    """Graph state 包含 manager_model_runtime 和 model_runtime。"""
    state = _state()
    state.manager_model_runtime = {
        "model_id": "deepseek-chat",
        "provider": "deepseek",
        "api_key": "test-key",
        "base_url": "https://api.deepseek.com",
    }

    graph_state = GraphExecutor.base_graph_state(state, _request(), _step())

    assert graph_state["manager_model_runtime"]["model_id"] == "deepseek-chat"
    assert graph_state["manager_model_runtime"]["provider"] == "deepseek"
    assert graph_state["model_runtime"]["provider"] == "deepseek"
    assert graph_state["manager_state"]["manager_model_runtime"]["model_id"] == "deepseek-chat"


def test_model_runtime_not_empty_when_state_has_runtime():
    """当 state 有 manager_model_runtime 时，model_runtime 不为空。"""
    state = _state()
    state.manager_model_runtime = {
        "model_id": "deepseek-chat",
        "provider": "deepseek",
        "api_key": "sk-test",
    }

    graph_state = GraphExecutor.base_graph_state(state, _request(), _step())

    assert graph_state["model_runtime"]
    assert graph_state["model_runtime"]["model_id"] == "deepseek-chat"
    assert graph_state["model_runtime"]["api_key"] == "sk-test"


def test_manager_state_includes_model_runtime():
    """manager_state 子字典包含 manager_model_runtime。"""
    state = _state()
    state.manager_model_runtime = {
        "model_id": "deepseek-chat",
        "provider": "deepseek",
    }

    graph_state = GraphExecutor.base_graph_state(state, _request(), _step())

    mgr = graph_state["manager_state"]
    assert mgr["manager_model_runtime"]["model_id"] == "deepseek-chat"
    assert mgr["manager_model_runtime"]["provider"] == "deepseek"


def test_model_runtime_is_empty_dict_when_state_has_no_runtime():
    """当 state 没有 manager_model_runtime 时，model_runtime 为空 dict。"""
    state = _state()
    # 不设置 manager_model_runtime

    graph_state = GraphExecutor.base_graph_state(state, _request(), _step())

    assert graph_state["model_runtime"] == {}
    assert graph_state["manager_model_runtime"] == {}
    assert graph_state["manager_state"]["manager_model_runtime"] == {}


def test_base_graph_state_preserves_existing_fields():
    """注入 model_runtime 不应破坏已有的字段。"""
    state = _state()
    state.manager_model_runtime = {"model_id": "test-model"}

    graph_state = GraphExecutor.base_graph_state(state, _request(), _step())

    # 已有字段应保持完整
    assert graph_state["request_id"] == "req-grt-1"
    assert graph_state["workflow_run_id"] == "wf-grt-1"
    assert graph_state["surface"] == "chat"
    assert graph_state["query"] == "test query"
    assert graph_state["step"]["step_id"] == "step-grt-1"
    assert "request" in graph_state
    assert "manager_state" in graph_state
    assert isinstance(graph_state["artifacts"], list)
