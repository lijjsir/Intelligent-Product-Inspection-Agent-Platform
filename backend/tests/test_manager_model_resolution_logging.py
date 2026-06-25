from __future__ import annotations

"""Tests for _resolve_manager_model logging per agent-manager-error-observability-fix-guide Section 4.3."""

import pytest

from agent.router.manager_loop import ManagerLoop
from agent.router.manager_state import ManagerState


def _state(**overrides) -> ManagerState:
    payload = {
        "request_id": "req-mmr-1",
        "workflow_run_id": "wf-mmr-1",
        "original_query": "你好",
        "org_id": "org-1",
        "user_id": "user-1",
        "session_id": "session-1",
        "selected_agent": "quality_analysis",
    }
    payload.update(overrides)
    return ManagerState(**payload)


@pytest.mark.asyncio
async def test_db_session_none_logs_warning(caplog):
    """db_session 为 None 时输出 warning 日志。"""
    import logging
    caplog.set_level(logging.WARNING, logger="agent.router.manager_loop")

    loop = ManagerLoop()
    state = _state()

    result = await loop._resolve_manager_model(state, db_session=None)

    assert result is None
    assert "db_session is None" in caplog.text
    assert state.request_id in caplog.text


@pytest.mark.asyncio
async def test_model_list_query_exception_logs_exception(monkeypatch, caplog):
    """模型列表查询异常时输出 exception 日志。"""
    import logging
    caplog.set_level(logging.ERROR, logger="agent.router.manager_loop")

    loop = ManagerLoop()
    state = _state()

    class FakeSession:
        pass

    async def fake_list_runtime_models(*args, **kwargs):
        raise RuntimeError("database connection lost")

    monkeypatch.setattr(
        "agent.router.manager_loop.ModelConfigService.list_runtime_models",
        fake_list_runtime_models,
    )

    result = await loop._resolve_manager_model(state, db_session=FakeSession())

    assert result is None
    assert "Manager model resolve failed" in caplog.text
    assert state.request_id in caplog.text
    assert "database connection lost" in caplog.text


@pytest.mark.asyncio
async def test_no_available_model_logs_warning(monkeypatch, caplog):
    """没有可用模型时输出 warning 日志。"""
    import logging
    caplog.set_level(logging.WARNING, logger="agent.router.manager_loop")

    loop = ManagerLoop()
    state = _state()

    class FakeSession:
        pass

    async def fake_list_runtime_models(*args, **kwargs):
        return [{"model_id": "gpt-4", "provider": "openai"}]

    async def fake_select_runtime(*args, **kwargs):
        return None  # 没有选中任何模型

    monkeypatch.setattr(
        "agent.router.manager_loop.ModelConfigService.list_runtime_models",
        fake_list_runtime_models,
    )
    monkeypatch.setattr(loop._gateway, "select_runtime", fake_select_runtime)

    result = await loop._resolve_manager_model(state, db_session=FakeSession())

    assert result is None
    assert "Manager model runtime not found" in caplog.text
    assert state.request_id in caplog.text


@pytest.mark.asyncio
async def test_deepseek_model_writes_to_state(monkeypatch):
    """有 DeepSeek 模型时写入 state.manager_model_runtime。"""
    loop = ManagerLoop()
    state = _state()

    runtime = {
        "model_config_id": "cfg-1",
        "model_id": "deepseek-chat",
        "provider": "deepseek",
        "api_key": "sk-test-key",
        "base_url": "https://api.deepseek.com",
        "runtime_key": "deepseek-chat-default",
        "failover_depth": 0,
    }

    class FakeSession:
        pass

    async def fake_list_runtime_models(*args, **kwargs):
        return [runtime]

    async def fake_select_runtime(*args, **kwargs):
        return runtime

    monkeypatch.setattr(
        "agent.router.manager_loop.ModelConfigService.list_runtime_models",
        fake_list_runtime_models,
    )
    monkeypatch.setattr(loop._gateway, "select_runtime", fake_select_runtime)

    result = await loop._resolve_manager_model(state, db_session=FakeSession())

    assert result is not None
    assert result["model_id"] == "deepseek-chat"
    assert result["provider"] == "deepseek"
    assert result["logical_name"] == "manager_model"
    assert result["model_type"] == "chat"

    # Verify state was updated
    assert state.manager_model_runtime is not None
    assert state.manager_model_runtime["model_id"] == "deepseek-chat"
    assert state.manager_model_runtime["api_key"] == "sk-test-key"
