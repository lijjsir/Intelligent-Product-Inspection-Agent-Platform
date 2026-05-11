from contextlib import asynccontextmanager

import pytest

from agent.contracts import AgentOutput, ClarificationRequest, NormalizedRequest, RouteDecision, RouteSignals
from app.services import quality_agent_orchestrator_service as orchestrator_mod
from app.services.quality_agent_orchestrator_service import QualityAgentOrchestratorService


@pytest.mark.asyncio
async def test_persist_chat_result_updates_assistant_message_for_task_action(monkeypatch):
    updates: list[dict] = []
    touches: list[dict] = []
    events: list[dict] = []

    class FakeSession:
        async def commit(self):
            return None

    @asynccontextmanager
    async def fake_get_session():
        yield FakeSession()

    class FakeChatMessageRepository:
        def __init__(self, _session):
            pass

        async def update_assistant_message(self, **kwargs):
            updates.append(kwargs)
            return object()

    class FakeChatSessionRepository:
        def __init__(self, _session):
            pass

        async def touch(self, org_id: str, user_id: str, session_id: str):
            touches.append(
                {
                    "org_id": org_id,
                    "user_id": user_id,
                    "session_id": session_id,
                }
            )

    class FakeRagAnalysisRepository:
        def __init__(self, _session, _org_id):
            pass

    monkeypatch.setattr(orchestrator_mod, "get_session", fake_get_session)
    monkeypatch.setattr(orchestrator_mod, "ChatMessageRepository", FakeChatMessageRepository)
    monkeypatch.setattr(orchestrator_mod, "ChatSessionRepository", FakeChatSessionRepository)
    monkeypatch.setattr(orchestrator_mod, "RagAnalysisRepository", FakeRagAnalysisRepository)

    async def fake_emit(event: dict):
        events.append(event)

    request = NormalizedRequest(
        request_id="req-task-action",
        workflow_run_id="wf-task-action",
        session_id="session-1",
        assistant_message_id="assistant-1",
        org_id="org-1",
        user_id="user-1",
        ext={"emit": fake_emit},
    )
    output = AgentOutput(
        message_type="task_action",
        answer="识别到的产品类别：`chemical`\n缺失字段：spec_code",
        summary="等待补充必要信息",
        action_state="awaiting_clarification",
        clarification=ClarificationRequest(
            missing_fields=["spec_code"],
            reason="spec is required",
            suggestions=["Please provide the spec_code."],
            examples={"spec_code": "ELEC-RAG-BASE-V1"},
        ),
        quality={"passed": False, "risk_level": "critical", "risk_score": 0.92},
        route_decision=RouteDecision(
            mode="router_enabled",
            selected_subgraph="quality_judgement",
            fallback_subgraph="quality_judgement",
            reason="file attachment detected",
            signals=RouteSignals(has_file_attachments=True, attachment_types=["txt"]),
        ),
    )

    success = await QualityAgentOrchestratorService()._persist_chat_result(request, output)

    assert success is True
    assert len(updates) == 1
    assert updates[0]["org_id"] == "org-1"
    assert updates[0]["message_id"] == "assistant-1"
    assert updates[0]["message_type"] == "task_action"
    assert "缺失字段：spec_code" in updates[0]["content"]
    assert touches == [{"org_id": "org-1", "user_id": "user-1", "session_id": "session-1"}]
    assert any(event["event"] == "message_delta" for event in events)
    assert any(event["event"] == "message_final" for event in events)
    final_event = next(event for event in events if event["event"] == "message_final")
    assert final_event["content"] == output.answer
    assert final_event["payload"]["message_type"] == "task_action"
