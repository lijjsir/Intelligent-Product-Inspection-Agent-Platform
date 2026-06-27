from __future__ import annotations

import pytest

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.errors import AgentInternalError, AgentRuntimeError, make_agent_error
from agent.router.manager_loop import ManagerLoop
from agent.router.manager_state import ManagerState


def _request(**overrides) -> NormalizedRequest:
    payload = {
        "request_id": "req-obs-1",
        "workflow_run_id": "wf-obs-1",
        "org_id": "org-1",
        "user_id": "user-1",
        "session_id": "session-1",
        "query": "你好",
        "ext": {"surface": "chat"},
    }
    payload.update(overrides)
    return NormalizedRequest(**payload)


def _state(**overrides) -> ManagerState:
    payload = {
        "request_id": "req-obs-1",
        "workflow_run_id": "wf-obs-1",
        "original_query": "你好",
        "org_id": "org-1",
        "user_id": "user-1",
        "session_id": "session-1",
        "selected_agent": "quality_analysis",
    }
    payload.update(overrides)
    return ManagerState(**payload)


@pytest.mark.asyncio
async def test_manager_loop_logs_raw_exception(monkeypatch, caplog):
    """ManagerLoop 普通异常会打印 logger.exception 并保留 raw_error / error_type。"""
    import logging
    caplog.set_level(logging.ERROR, logger="agent.router.manager_loop")

    loop = ManagerLoop()

    async def fake_dispatch(*args, **kwargs):
        raise TypeError("forced dispatch error for observability test")

    monkeypatch.setattr(loop._dispatcher, "dispatch", fake_dispatch)

    result = await loop.run(_request(query="你好"))

    assert result.status == "failed"
    assert result.agent_output["ui_schema"] == "agent_error_v1"
    # 前端 payload 不应包含 debug
    assert "debug" not in result.agent_output["error"]

    # 后端日志应包含真实异常信息
    assert "forced dispatch error for observability test" in caplog.text
    assert "TypeError" in caplog.text
    assert "ManagerLoop internal exception" in caplog.text
    assert "ManagerLoop agent_error_full" in caplog.text


@pytest.mark.asyncio
async def test_public_payload_excludes_debug_in_production():
    """前端 payload 在生产环境不包含 debug 字段。"""
    state = _state(request_id="req-pub-1", workflow_run_id="wf-pub-1", trace_id="trace-1")

    wrapped = AgentInternalError(
        code="INTERNAL_AGENT_ERROR",
        title="系统内部错误",
        message="系统执行失败，请查看错误信息或联系管理员。",
        detail={
            "stage": "manager_loop.run",
            "request_id": state.request_id,
        },
        debug={
            "raw_error": "forced error",
            "error_type": "TypeError",
        },
    )

    public_payload = wrapped.to_dict(state=state, include_debug=False)

    assert "debug" not in public_payload
    assert public_payload["code"] == "INTERNAL_AGENT_ERROR"
    assert public_payload["message"] == "系统执行失败，请查看错误信息或联系管理员。"
    assert public_payload["detail"]["stage"] == "manager_loop.run"


def test_log_payload_includes_debug():
    """后端日志版 payload 包含 debug（raw_error / error_type）。"""
    state = _state(request_id="req-log-1", workflow_run_id="wf-log-1", trace_id="trace-1")

    wrapped = AgentInternalError(
        code="INTERNAL_AGENT_ERROR",
        title="系统内部错误",
        message="系统执行失败，请查看错误信息或联系管理员。",
        detail={"stage": "manager_loop.run"},
        debug={
            "raw_error": "forced error",
            "error_type": "TypeError",
        },
    )

    log_payload = wrapped.to_dict(state=state, include_debug=True)

    assert "debug" in log_payload
    assert log_payload["debug"]["raw_error"] == "forced error"
    assert log_payload["debug"]["error_type"] == "TypeError"
    assert log_payload["detail"]["stage"] == "manager_loop.run"


def test_agent_runtime_error_log_payload_includes_debug():
    """AgentRuntimeError 的 log_error_payload 包含 debug 字段。"""
    state = _state(request_id="req-are-1", workflow_run_id="wf-are-1", trace_id="trace-1")

    error = make_agent_error(
        "MODEL_CALL_FAILED",
        detail={"model_id": "deepseek-chat"},
        debug={"raw_error": "Connection refused", "error_type": "ConnectionError"},
        source="chat_executor.call_model",
    )

    log_payload = error.to_dict(state=state, include_debug=True)

    assert log_payload["debug"]["raw_error"] == "Connection refused"
    assert log_payload["debug"]["error_type"] == "ConnectionError"
    assert log_payload["request_id"] == "req-are-1"


def test_agent_runtime_error_public_payload_excludes_debug():
    """AgentRuntimeError 的 public_error_payload 在生产环境不包含 debug。"""
    state = _state(request_id="req-are-2", workflow_run_id="wf-are-2")

    error = make_agent_error(
        "MODEL_CALL_FAILED",
        detail={"model_id": "deepseek-chat"},
        debug={"raw_error": "Connection refused", "error_type": "ConnectionError"},
        source="chat_executor.call_model",
    )

    public_payload = error.to_dict(state=state, include_debug=False)

    assert "debug" not in public_payload
    assert public_payload["code"] == "MODEL_CALL_FAILED"


@pytest.mark.asyncio
async def test_agent_runtime_error_branch_logs_full_context(monkeypatch, caplog):
    """AgentRuntimeError 分支通过双通道记录日志，保留完整上下文。"""
    import logging
    caplog.set_level(logging.ERROR, logger="agent.router.manager_loop")

    loop = ManagerLoop()

    async def fake_understand(state):
        raise make_agent_error(
            "MODEL_CALL_FAILED",
            message="模型调用失败。",
            detail={"model_id": "test-model", "stage": "manager_loop.run"},
            debug={"raw_error": "Connection timeout", "error_type": "TimeoutError"},
            source="chat_executor.call_model",
        )

    monkeypatch.setattr(loop._policy, "understand", fake_understand)

    result = await loop.run(_request(query="你好"))

    assert result.status == "failed"
    assert result.agent_output["ui_schema"] == "agent_error_v1"

    # 回调端 payload 不应含 debug
    assert "debug" not in result.agent_output["error"]

    # 日志应包含完整上下文
    assert "ManagerLoop agent_runtime_error" in caplog.text


def test_state_dump_survives_unserializable_dict_values():
    """_state_dump 在 dict 字段包含 function 等不可序列化值时不应崩溃，
    而是通过 Pydantic fallback 将其转为可读的占位字符串。"""
    state = _state(request_id="req-fn-1", workflow_run_id="wf-fn-1")
    # Simulate a dict field containing a function
    state.request_ext = {"callback": lambda x: x, "text": "hello"}

    result = ManagerLoop._state_dump(state)

    # Should not crash
    assert isinstance(result, dict)
    # Function value should be replaced with type-name placeholder
    assert result["request_ext"]["callback"] == "<function>"
    assert result["request_ext"]["text"] == "hello"
