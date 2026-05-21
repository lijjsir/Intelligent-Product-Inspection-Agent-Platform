from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from agent.contracts import NormalizedRequest
from agent.subgraphs.quality_judgement.graph import QualityJudgementSubgraph


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
