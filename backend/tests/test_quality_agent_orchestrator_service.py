from contextlib import asynccontextmanager

import pytest

from agent.contracts import (
    AgentOutput,
    ClarificationRequest,
    NormalizedRequest,
    PersistableOutput,
    ResultAggregate,
    RouteDecision,
    RouteSignals,
    StabilityAggregate,
    TaskAggregate,
)
from app.services import quality_agent_orchestrator_service as orchestrator_mod
from app.services.quality_agent_orchestrator_service import QualityAgentOrchestratorService


def test_orchestrator_json_sanitizer_drops_callables_from_legacy_state():
    def emit():
        return None

    payload = QualityAgentOrchestratorService._json_safe(
        {
            "answer": "ok",
            "emit": emit,
            "nested": {"callback": emit, "count": 1},
        }
    )

    assert payload == {"answer": "ok", "nested": {"count": 1}}


def test_quality_chat_answer_is_not_materialized_as_task():
    output = AgentOutput(
        message_type="quality_answer",
        route_decision=RouteDecision(
            selected_subgraph="quality_chat",
            intent="rag_qa",
            reason="ordinary RAG answer",
        ),
    )

    assert QualityAgentOrchestratorService()._should_materialize_chat_output(output) is False


def test_inspection_task_result_with_structured_output_is_materialized():
    output = AgentOutput(
        message_type="task_result",
        route_decision=RouteDecision(
            selected_subgraph="inspection_task",
            intent="structured_inspection",
            reason="inspection task completed",
        ),
        persistable_output=PersistableOutput(
            task=TaskAggregate(product_id="P-1", spec_code="STD-1", status="done"),
            result=ResultAggregate(verdict="pass", overall_score=0.98),
            stability=StabilityAggregate(risk_level="low", risk_score=0.1),
        ),
    )

    assert QualityAgentOrchestratorService()._should_materialize_chat_output(output) is True


def test_inspection_task_without_full_structured_output_is_not_materialized():
    output = AgentOutput(
        message_type="task_result",
        route_decision=RouteDecision(
            selected_subgraph="inspection_task",
            intent="task_create",
            reason="task accepted but no result yet",
        ),
        persistable_output=PersistableOutput(
            task=TaskAggregate(product_id="P-1", spec_code="STD-1", status="queued"),
        ),
    )

    assert QualityAgentOrchestratorService()._should_materialize_chat_output(output) is False


def test_response_payload_prefers_subgraph_intent_over_router_default():
    request = NormalizedRequest(
        request_id="req-rag",
        workflow_run_id="wf-rag",
        session_id="session-1",
        assistant_message_id="assistant-1",
        org_id="org-1",
        user_id="user-1",
    )
    output = AgentOutput(
        message_type="assistant_text",
        answer="tgg",
        summary="RAG answer",
        raw_state={"response_payload": {"intent": "rag_qa", "message_type": "assistant_text"}},
        route_decision=RouteDecision(
            selected_subgraph="quality_chat",
            intent="general_qa",
            reason="default chat route",
            signals=RouteSignals(),
        ),
    )

    payload = QualityAgentOrchestratorService()._build_response_payload(
        request=request,
        output=output,
        task_form_defaults={},
        materialized_task=None,
        materialization_error=None,
    )

    assert payload["intent"] == "rag_qa"


@pytest.mark.asyncio
async def test_run_chat_uses_quality_graph_agent_output_contract(monkeypatch):
    persisted: list[tuple[NormalizedRequest, AgentOutput]] = []
    metrics: list[dict] = []

    from agent.router.contracts import AgentRouteDecision, AgentRouterOutput

    class FakeAgentManagerService:
        async def run_chat(self, payload: dict):
            return AgentRouterOutput(
                route_decision=AgentRouteDecision(
                    selected_agent="chat",
                    intent="general_chat",
                    reason="test",
                ),
                agent_output={
                    "message_type": "assistant_text",
                    "answer": "hi",
                    "summary": "",
                    "citations": [],
                    "quality": {},
                    "action_state": None,
                    "task_draft": None,
                    "created_task": None,
                    "clarification": None,
                    "persistable_output": {},
                    "raw_state": {},
                },
                status="completed",
            )

    class FakeGraph:
        async def run(self, request: NormalizedRequest):
            assert request.request_kind == "chat"
            assert request.query == "hello"
            return AgentOutput(
                message_type="assistant_text",
                answer="hi",
                route_decision=RouteDecision(
                    mode="router_enabled",
                    selected_subgraph="quality_judgement",
                    fallback_subgraph="quality_judgement",
                ),
            )

    async def fake_persist(self, request: NormalizedRequest, output: AgentOutput):
        persisted.append((request, output))
        return True

    async def fake_record_metrics(self, org_id: str, subgraph_key: str, *, success: bool, latency_ms: int):
        metrics.append(
            {
                "org_id": org_id,
                "subgraph_key": subgraph_key,
                "success": success,
                "latency_ms": latency_ms,
            }
        )

    service = QualityAgentOrchestratorService()
    service._agent_manager = FakeAgentManagerService()
    service._graph = FakeGraph()
    monkeypatch.setattr(QualityAgentOrchestratorService, "_persist_chat_result", fake_persist)
    monkeypatch.setattr(QualityAgentOrchestratorService, "_record_runtime_metrics", fake_record_metrics)

    result = await service.run_chat(
        {
            "request_id": "req-1",
            "session_id": "session-1",
            "assistant_message_id": "assistant-1",
            "org_id": "org-1",
            "user_id": "user-1",
            "query": "hello",
        }
    )

    assert persisted[0][1].answer == "hi"
    assert result["agent_output"]["answer"] == "hi"
    assert metrics[0]["subgraph_key"] == "quality_chat"


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
    assert any(event["event"] == "message_final" for event in events)
    final_event = next(event for event in events if event["event"] == "message_final")
    assert final_event["content"] == output.answer
    assert final_event["payload"]["message_type"] == "task_action"


@pytest.mark.asyncio
async def test_route_log_failure_does_not_fail_chat_persistence(monkeypatch):
    updates: list[dict] = []

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
            return None

    class FakeRagAnalysisRepository:
        def __init__(self, _session, _org_id):
            pass

    class BrokenAgentRouteLogRepository:
        def __init__(self, _session, _org_id):
            pass

        async def create(self, _payload):
            raise RuntimeError("agent_route_logs missing")

    monkeypatch.setattr(orchestrator_mod, "get_session", fake_get_session)
    monkeypatch.setattr(orchestrator_mod, "ChatMessageRepository", FakeChatMessageRepository)
    monkeypatch.setattr(orchestrator_mod, "ChatSessionRepository", FakeChatSessionRepository)
    monkeypatch.setattr(orchestrator_mod, "RagAnalysisRepository", FakeRagAnalysisRepository)
    monkeypatch.setattr(
        "app.repositories.agent_ops_repo.AgentRouteLogRepository",
        BrokenAgentRouteLogRepository,
    )

    request = NormalizedRequest(
        request_id="req-route-log",
        workflow_run_id="wf-route-log",
        session_id="session-1",
        assistant_message_id="assistant-1",
        org_id="org-1",
        user_id="user-1",
    )
    output = AgentOutput(
        message_type="assistant_text",
        answer="hello",
        route_decision=RouteDecision(
            mode="router_enabled",
            selected_subgraph="quality_chat",
            fallback_subgraph="quality_chat",
            intent="general_qa",
            reason="test",
        ),
    )

    success = await QualityAgentOrchestratorService()._persist_chat_result(request, output)

    assert success is True
    assert updates[0]["content"] == "hello"
