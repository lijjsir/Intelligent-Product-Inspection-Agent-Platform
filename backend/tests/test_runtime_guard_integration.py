from types import SimpleNamespace

import pytest

from agent.router.runtime_guard import AgentRuntimeGuard
from app.services.agent_manager_service import AgentManagerService
from infra.cache.memory_cache import _runtime_guard_cache


@pytest.mark.asyncio
async def test_agent_manager_service_passes_db_session_to_manager():
    captured: dict[str, object] = {}
    fake_session = object()

    class FakeManager:
        async def run(self, request, db_session=None):
            captured["request_id"] = request.request_id
            captured["db_session"] = db_session
            return SimpleNamespace(status="completed")

    service = AgentManagerService()
    service._manager = FakeManager()
    output = await service.run_chat(
        {
            "request_id": "req-guard-1",
            "workflow_run_id": "wf-guard-1",
            "session_id": "session-1",
            "assistant_message_id": "message-1",
            "org_id": "org-1",
            "user_id": "user-1",
            "query": "你好",
        },
        db_session=fake_session,
    )

    assert captured == {
        "request_id": "req-guard-1",
        "db_session": fake_session,
    }
    assert output.status == "completed"


@pytest.mark.asyncio
async def test_runtime_guard_caches_allowed_result(monkeypatch):
    _runtime_guard_cache.clear()
    execute_calls: list[str] = []

    class FakeResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    class FakeSession:
        async def execute(self, _stmt):
            execute_calls.append("execute")
            if len(execute_calls) == 1:
                return FakeResult(
                    SimpleNamespace(
                        id="agent-1",
                        name="Chat",
                        route_enabled=True,
                    )
                )
            return FakeResult(
                SimpleNamespace(
                    runtime_status="running",
                )
            )

    first = await AgentRuntimeGuard.check("org-1", "chat", "general_chat", FakeSession())
    second = await AgentRuntimeGuard.check("org-1", "chat", "general_chat", FakeSession())

    assert first.allowed is True
    assert second.allowed is True
    assert execute_calls == ["execute", "execute"]


@pytest.mark.asyncio
async def test_runtime_guard_cache_can_be_invalidated(monkeypatch):
    _runtime_guard_cache.clear()
    execute_calls: list[str] = []

    class FakeResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    class FakeSession:
        async def execute(self, _stmt):
            execute_calls.append("execute")
            return FakeResult(
                SimpleNamespace(id="agent-1", name="Chat", route_enabled=False)
                if len(execute_calls) % 2 == 1
                else None
            )

    blocked = await AgentRuntimeGuard.check("org-1", "chat", "general_chat", FakeSession())
    _runtime_guard_cache.delete_prefix("runtime_guard:org-1")
    blocked_again = await AgentRuntimeGuard.check("org-1", "chat", "general_chat", FakeSession())

    assert blocked.allowed is False
    assert blocked_again.allowed is False
    assert len(execute_calls) == 2
