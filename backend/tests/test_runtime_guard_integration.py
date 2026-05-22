from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from agent.contracts import NormalizedRequest
from agent.subgraphs.quality_judgement.graph import QualityJudgementSubgraph
from agent.router.runtime_guard import AgentRuntimeGuard
from infra.cache.memory_cache import _runtime_guard_cache


@pytest.mark.asyncio
async def test_quality_judgement_passes_db_session_to_agent_manager(monkeypatch):
    captured: dict[str, object] = {}
    fake_session = object()

    @asynccontextmanager
    async def fake_get_session():
        captured["session_opened"] = True
        yield fake_session

    class FakeManager:
        async def run(self, request, db_session=None):
            captured["request_id"] = request.request_id
            captured["db_session"] = db_session
            return SimpleNamespace(
                route_decision=SimpleNamespace(
                    selected_agent="chat",
                    sub_route="general_chat",
                    reason="test",
                    intent="general_chat",
                    confidence=1.0,
                    requires_confirmation=False,
                    route_source="rule",
                    fallback_agent=None,
                ),
                agent_output={
                    "message_type": "assistant_text",
                    "answer": "guarded",
                    "summary": "",
                    "citations": [],
                    "quality": {},
                    "persistable_output": {},
                    "raw_state": {},
                },
            )

    monkeypatch.setattr("agent.subgraphs.quality_judgement.graph.get_session", fake_get_session)
    monkeypatch.setattr("agent.router.AgentManager", FakeManager)

    output = await QualityJudgementSubgraph().run(
        NormalizedRequest(
            request_id="req-guard-1",
            workflow_run_id="wf-guard-1",
            org_id="org-1",
            user_id="user-1",
            query="你好",
        )
    )

    assert captured == {
        "session_opened": True,
        "request_id": "req-guard-1",
        "db_session": fake_session,
    }
    assert output.answer == "guarded"


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
