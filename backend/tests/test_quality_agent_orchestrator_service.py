from contextlib import asynccontextmanager

import pytest
from types import SimpleNamespace

from agent.contracts import (
    AgentOutput,
    AlertEvent,
    ClarificationRequest,
    NormalizedRequest,
    PersistableOutput,
    QualityTraceEvent,
    RagQueryLog,
    ResultAggregate,
    RouteDecision,
    RouteSignals,
    StabilityAggregate,
    TaskAggregate,
    TokenUsageEvent,
)
from app.services import quality_agent_orchestrator_service as orchestrator_mod
from app.services.quality_agent_orchestrator_service import QualityAgentOrchestratorService


@pytest.fixture(autouse=True)
def disable_background_trust_scoring(monkeypatch):
    monkeypatch.setattr(QualityAgentOrchestratorService, "_enqueue_trust_scoring", lambda *_args, **_kwargs: None)


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


def test_orchestrator_idempotency_key_hashes_long_keys_within_mysql_limit():
    request = NormalizedRequest(
        request_kind="chat",
        request_id="req-token",
        workflow_run_id="workflow-" + ("w" * 80),
        session_id="session-" + ("s" * 80),
        assistant_message_id="assistant-" + ("a" * 80),
        org_id="org-1",
        user_id="user-1",
        workspace="chat",
        query="hello",
    )

    key = QualityAgentOrchestratorService._idempotency_key(
        request,
        "chat-token",
        0,
        "doubao-seed-2-0-lite-260215",
        "trace-" + ("t" * 80),
    )
    same_key = QualityAgentOrchestratorService._idempotency_key(
        request,
        "chat-token",
        0,
        "doubao-seed-2-0-lite-260215",
        "trace-" + ("t" * 80),
    )
    different_key = QualityAgentOrchestratorService._idempotency_key(
        request,
        "chat-token",
        1,
        "doubao-seed-2-0-lite-260215",
        "trace-" + ("t" * 80),
    )

    assert len(key) <= 191
    assert len(different_key) <= 191
    assert ":sha256:" in key
    assert same_key == key
    assert different_key != key


def test_chat_answer_is_not_materialized_as_task():
    output = AgentOutput(
        message_type="quality_answer",
        route_decision=RouteDecision(
            selected_agent="chat",
            sub_route="rag_qa",
            intent="rag_qa",
            reason="ordinary RAG answer",
        ),
    )

    assert QualityAgentOrchestratorService()._should_materialize_chat_output(output) is False


def test_inspection_task_result_with_structured_output_is_materialized():
    output = AgentOutput(
        message_type="task_result",
        route_decision=RouteDecision(
            selected_agent="inspection_task",
            sub_route="inspection_execute",
            intent="inspection_execute",
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
            selected_agent="inspection_task",
            sub_route="task_create",
            intent="task_create",
            reason="task accepted but no result yet",
        ),
        persistable_output=PersistableOutput(
            task=TaskAggregate(product_id="P-1", spec_code="STD-1", status="queued"),
        ),
    )

    assert QualityAgentOrchestratorService()._should_materialize_chat_output(output) is False


def test_response_payload_prefers_router_subroute_over_legacy_subgraph_intent():
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
            selected_agent="chat",
            sub_route="general_chat",
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

    assert payload["intent"] == "general_chat"


@pytest.mark.asyncio
async def test_run_chat_uses_quality_graph_agent_output_contract(monkeypatch):
    persisted: list[tuple[NormalizedRequest, AgentOutput]] = []
    metrics: list[dict] = []

    from agent.router.contracts import AgentRouteDecision, AgentRouterOutput

    class FakeAgentManagerService:
        async def run_chat(self, payload: dict, db_session=None):
            assert db_session is not None
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
                    selected_agent="inspection_task",
                    sub_route="inspection_execute",
                ),
            )

    async def fake_persist(self, request: NormalizedRequest, output: AgentOutput):
        persisted.append((request, output))
        return True

    async def fake_record_metrics(self, org_id: str, agent_key: str, *, success: bool, latency_ms: int):
        metrics.append(
            {
                "org_id": org_id,
                "agent_key": agent_key,
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
    assert metrics[0]["agent_key"] == "chat"


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
            selected_agent="inspection_task",
            sub_route="inspection_execute",
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
    assert sum(1 for event in events if event["event"] == "message_final") == 1
    final_event = next(event for event in events if event["event"] == "message_final")
    assert final_event["content"] == output.answer
    assert final_event["payload"]["message_type"] == "task_action"


@pytest.mark.asyncio
async def test_persist_chat_result_does_not_overwrite_interrupted_message_or_emit_final(monkeypatch):
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

        async def get(self, _org_id: str, _message_id: str):
            return SimpleNamespace(payload={"status": "interrupted"})

        async def update_assistant_message(self, **_kwargs):
            raise AssertionError("interrupted assistant message must not be overwritten")

    class FakeChatSessionRepository:
        def __init__(self, _session):
            pass

        async def touch(self, *_args, **_kwargs):
            raise AssertionError("interrupted turn must not touch session")

    monkeypatch.setattr(orchestrator_mod, "get_session", fake_get_session)
    monkeypatch.setattr(orchestrator_mod, "ChatMessageRepository", FakeChatMessageRepository)
    monkeypatch.setattr(orchestrator_mod, "ChatSessionRepository", FakeChatSessionRepository)

    async def fake_emit(event: dict):
        events.append(event)

    request = NormalizedRequest(
        request_id="req-interrupted",
        workflow_run_id="wf-interrupted",
        session_id="session-1",
        assistant_message_id="assistant-1",
        org_id="org-1",
        user_id="user-1",
        ext={"emit": fake_emit},
    )
    output = AgentOutput(message_type="assistant_text", answer="late answer")

    success = await QualityAgentOrchestratorService()._persist_chat_result(request, output)

    assert success is False
    assert events == []


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
            selected_agent="chat",
            sub_route="general_chat",
            intent="general_qa",
            reason="test",
        ),
    )

    success = await QualityAgentOrchestratorService()._persist_chat_result(request, output)

    assert success is True
    assert updates[0]["content"] == "hello"


@pytest.mark.asyncio
async def test_persist_chat_result_adds_pending_trust_scoring_and_enqueues(monkeypatch):
    updates: list[dict] = []
    events: list[dict] = []
    queued: list[dict] = []

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

    async def fake_emit(event: dict):
        events.append(event)

    def fake_enqueue(_self, payload):
        queued.append(payload)

    monkeypatch.setattr(orchestrator_mod, "get_session", fake_get_session)
    monkeypatch.setattr(orchestrator_mod, "ChatMessageRepository", FakeChatMessageRepository)
    monkeypatch.setattr(orchestrator_mod, "ChatSessionRepository", FakeChatSessionRepository)
    monkeypatch.setattr(orchestrator_mod, "RagAnalysisRepository", FakeRagAnalysisRepository)
    monkeypatch.setattr(QualityAgentOrchestratorService, "_enqueue_trust_scoring", fake_enqueue)

    request = NormalizedRequest(
        request_id="req-trust",
        workflow_run_id="trace-chat",
        session_id="session-1",
        assistant_message_id="assistant-1",
        org_id="org-1",
        user_id="user-1",
        query="who am i",
        ext={"emit": fake_emit},
    )
    output = AgentOutput(
        message_type="assistant_text",
        answer="你来自 M78 星云。[RAG-1]",
        citations=[{"id": "RAG-1", "source": "profile.md"}],
        route_decision=RouteDecision(
            mode="router_enabled",
            selected_agent="chat",
            sub_route="rag_qa",
            intent="rag_qa",
            reason="test",
        ),
        raw_state={
            "response_payload": {
                "trace_id": "trace-chat",
                "llm_meta": {
                    "model": "doubao-seed-2-0-lite-260215",
                    "langfuse": {"trace_id": "trace-chat", "observation_id": "obs-1"},
                },
            }
        },
    )

    success = await QualityAgentOrchestratorService()._persist_chat_result(request, output)

    assert success is True
    assert updates[0]["payload"]["trust_scoring"]["status"] == "reviewing"
    assert updates[0]["payload"]["trust_scoring"]["trust_score"] is None
    assert queued == [
        {
            "org_id": "org-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "assistant_message_id": "assistant-1",
            "input_text": "who am i",
            "output_text": "你来自 M78 星云。[RAG-1]",
            "citations": [{"id": "RAG-1", "source": "profile.md"}],
            "trace_id": "trace-chat",
            "observation_id": "obs-1",
            "model_key": "doubao-seed-2-0-lite-260215",
        }
    ]
    final_event = next(event for event in events if event["event"] == "message_final")
    assert final_event["payload"]["trust_scoring"]["status"] == "reviewing"


@pytest.mark.asyncio
async def test_persist_chat_result_records_chat_token_usage(monkeypatch):
    ledgers: list[dict] = []
    increments: list[dict] = []

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
            return object()

    class FakeChatSessionRepository:
        def __init__(self, _session):
            pass

        async def touch(self, org_id: str, user_id: str, session_id: str):
            return None

    class FakeRagAnalysisRepository:
        def __init__(self, _session, _org_id):
            pass

    class FakeTokenLedgerRepository:
        def __init__(self, _session):
            pass

        async def get_by_idempotency_key(self, _key: str):
            return None

        async def create_once(self, data: dict):
            ledgers.append(data)
            return SimpleNamespace(created_at="created-at", **data)

        async def create(self, data: dict):
            return await self.create_once(data)

    class FakeUserTokenUsageSummaryRepository:
        def __init__(self, _session):
            pass

        async def increment(self, **kwargs):
            increments.append(kwargs)

    monkeypatch.setattr(orchestrator_mod, "get_session", fake_get_session)
    monkeypatch.setattr(orchestrator_mod, "ChatMessageRepository", FakeChatMessageRepository)
    monkeypatch.setattr(orchestrator_mod, "ChatSessionRepository", FakeChatSessionRepository)
    monkeypatch.setattr(orchestrator_mod, "RagAnalysisRepository", FakeRagAnalysisRepository)
    monkeypatch.setattr(orchestrator_mod, "TokenLedgerRepository", FakeTokenLedgerRepository)
    monkeypatch.setattr(orchestrator_mod, "UserTokenUsageSummaryRepository", FakeUserTokenUsageSummaryRepository)
    monkeypatch.setattr(QualityAgentOrchestratorService, "_enqueue_trust_scoring", lambda *_args, **_kwargs: None)

    request = NormalizedRequest(
        request_id="req-token",
        workflow_run_id="trace-token",
        session_id="session-1",
        assistant_message_id="assistant-1",
        org_id="org-1",
        user_id="user-1",
        workspace="chat",
        query="hello",
    )
    output = AgentOutput(
        message_type="assistant_text",
        answer="hello",
        persistable_output=PersistableOutput(
            token_usage=[
                TokenUsageEvent(
                    model_key="doubao-seed-2-0-lite-260215",
                    prompt_tokens=100,
                    completion_tokens=50,
                    total_tokens=150,
                    cost_amount=0.00015,
                    trace_id="trace-token",
                )
            ],
            quality_trace=QualityTraceEvent(trace_id="trace-token"),
        ),
    )

    success = await QualityAgentOrchestratorService()._persist_chat_result(request, output)

    assert success is True
    assert len(ledgers) == 1
    assert ledgers[0]["task_id"] is None
    assert ledgers[0]["result_id"] is None
    assert ledgers[0]["model_key"] == "doubao-seed-2-0-lite-260215"
    assert ledgers[0]["total_tokens"] == 150
    assert ledgers[0]["cost_amount"] == 0.00015
    assert ledgers[0]["trace_id"] == "trace-token"
    assert ledgers[0]["idempotency_key"].endswith(":chat-token:0:doubao-seed-2-0-lite-260215:trace-token")
    assert increments[0]["total_tokens"] == 150


@pytest.mark.asyncio
async def test_persist_chat_result_writes_rag_log_with_top_k_and_trace_detail(monkeypatch):
    updates: list[dict] = []
    rag_logs: list[dict] = []
    tool_logs: list[object] = []

    class FakeSession:
        async def get(self, model, key):
            return None

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

        async def create_log(self, data: dict):
            rag_logs.append(data)
            return None

    class FakeTool:
        id = "tool-rag"
        display_name = "标准知识库检索"

    class FakeToolRepository:
        def __init__(self, _session):
            pass

        async def get_by_tool_key(self, org_id: str, tool_key: str):
            assert tool_key == "rag.standard_search"
            return FakeTool()

        async def create_execution(self, execution):
            tool_logs.append(execution)
            return execution

    monkeypatch.setattr(orchestrator_mod, "get_session", fake_get_session)
    monkeypatch.setattr(orchestrator_mod, "ChatMessageRepository", FakeChatMessageRepository)
    monkeypatch.setattr(orchestrator_mod, "ChatSessionRepository", FakeChatSessionRepository)
    monkeypatch.setattr(orchestrator_mod, "RagAnalysisRepository", FakeRagAnalysisRepository)
    monkeypatch.setattr(orchestrator_mod, "ToolRepository", FakeToolRepository)

    request = NormalizedRequest(
        request_id="req-rag-detail",
        workflow_run_id="wf-rag-detail",
        session_id="session-1",
        assistant_message_id="assistant-1",
        org_id="org-1",
        user_id="user-1",
    )
    output = AgentOutput(
        message_type="task_result",
        answer="检测结论：PASS",
        summary="inspection done",
        route_decision=RouteDecision(
            mode="router_enabled",
            selected_agent="inspection_task",
            sub_route="inspection_execute",
            intent="inspection_execute",
            reason="inspection flow",
        ),
        persistable_output=PersistableOutput(
            rag_queries=[
                RagQueryLog(
                    query="苹果划痕 3mm 标准",
                    rag_space_id="rag-food",
                    top_k=6,
                    hit_count=3,
                    hit_rate=0.5,
                    citation_coverage=0.67,
                    latency_ms=188,
                    source_graph="inspection_task",
                    agent_name="inspection_task",
                    sub_route="inspection_execute",
                    trace_id="trace-rag-detail",
                    top_score=0.92,
                    metadata={
                        "top_sources": ["apple-spec.pdf"],
                        "rule_hits": ["apple.surface.scratch_limit"],
                        "verdict": "pass",
                        "product_family": "food",
                        "expectation_matched": True,
                        "retrieval_config": {"top_k": 6},
                        "retrieved_chunks": [{"chunk_id": "chunk-1"}],
                        "used_citations": [{"id": "rag-1"}],
                        "answer": "检测结论：PASS",
                        "result": {"verdict": "pass"},
                    },
                )
            ]
        ),
    )

    success = await QualityAgentOrchestratorService()._persist_chat_result(request, output)

    assert success is True
    assert updates[0]["content"] == "检测结论：PASS"
    assert len(rag_logs) == 1
    assert rag_logs[0]["top_k"] == 6
    assert rag_logs[0]["trace_id"] == "trace-rag-detail"
    assert rag_logs[0]["metadata_json"]["retrieved_chunks"][0]["chunk_id"] == "chunk-1"
    assert rag_logs[0]["metadata_json"]["used_citations"][0]["id"] == "rag-1"
    assert len(tool_logs) == 1
    assert tool_logs[0].tool_name == "标准知识库检索"
    assert tool_logs[0].input_payload["query"] == "苹果划痕 3mm 标准"
    assert tool_logs[0].output_payload["hit_count"] == 3


@pytest.mark.asyncio
async def test_persist_chat_result_writes_file_parse_tool_execution(monkeypatch):
    updates: list[dict] = []
    tool_logs: list[object] = []

    class FakeSession:
        async def get(self, model, key):
            return None

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

    class FakeTool:
        id = "tool-file"
        display_name = "文件内容解析"

    class FakeToolRepository:
        def __init__(self, _session):
            pass

        async def get_by_tool_key(self, org_id: str, tool_key: str):
            assert tool_key == "file.parse"
            return FakeTool()

        async def create_execution(self, execution):
            tool_logs.append(execution)
            return execution

    monkeypatch.setattr(orchestrator_mod, "get_session", fake_get_session)
    monkeypatch.setattr(orchestrator_mod, "ChatMessageRepository", FakeChatMessageRepository)
    monkeypatch.setattr(orchestrator_mod, "ChatSessionRepository", FakeChatSessionRepository)
    monkeypatch.setattr(orchestrator_mod, "RagAnalysisRepository", FakeRagAnalysisRepository)
    monkeypatch.setattr(orchestrator_mod, "ToolRepository", FakeToolRepository)

    request = NormalizedRequest(
        request_id="req-file-tool",
        workflow_run_id="wf-file-tool",
        session_id="session-1",
        assistant_message_id="assistant-1",
        org_id="org-1",
        user_id="user-1",
    )
    output = AgentOutput(
        message_type="file_answer",
        answer="文件内容：我叫 tgg。",
        summary="file parsed",
        route_decision=RouteDecision(
            mode="router_enabled",
            selected_agent="chat",
            sub_route="file_qa",
            intent="file_qa",
            reason="file attachment detected",
        ),
        raw_state={
            "response_payload": {
                "artifacts": [
                    {
                        "type": "file_answer",
                        "content": {
                            "parsed_files": [
                                {
                                    "name": "222.pdf",
                                    "url": "/uploads/chat_attachments/222.pdf",
                                    "content_type": "application/pdf",
                                    "kind": "pdf",
                                    "text": "我叫 tgg，重庆这个地方很美丽。",
                                    "summary": "我叫 tgg，重庆这个地方很美丽。",
                                }
                            ]
                        },
                    }
                ]
            }
        },
    )

    success = await QualityAgentOrchestratorService()._persist_chat_result(request, output)

    assert success is True
    assert updates[0]["content"] == "文件内容：我叫 tgg。"
    assert len(tool_logs) == 1
    assert tool_logs[0].tool_name == "文件内容解析"
    assert tool_logs[0].input_payload["file_name"] == "222.pdf"
    assert tool_logs[0].output_payload["kind"] == "pdf"
    assert tool_logs[0].output_payload["text_length"] > 0


@pytest.mark.asyncio
async def test_repeated_chat_finalization_uses_idempotent_rag_log(monkeypatch):
    updates: list[dict] = []
    rag_logs: dict[str, dict] = {}

    class FakeSession:
        async def commit(self):
            return None

    @asynccontextmanager
    async def fake_get_session():
        yield FakeSession()

    class FakeChatMessageRepository:
        def __init__(self, _session):
            pass

        async def get(self, _org_id: str, _message_id: str):
            return None

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

        async def create_log_once(self, data: dict):
            rag_logs.setdefault(data["idempotency_key"], data)
            return rag_logs[data["idempotency_key"]]

        async def create_log(self, data: dict):
            return await self.create_log_once(data)

    monkeypatch.setattr(orchestrator_mod, "get_session", fake_get_session)
    monkeypatch.setattr(orchestrator_mod, "ChatMessageRepository", FakeChatMessageRepository)
    monkeypatch.setattr(orchestrator_mod, "ChatSessionRepository", FakeChatSessionRepository)
    monkeypatch.setattr(orchestrator_mod, "RagAnalysisRepository", FakeRagAnalysisRepository)

    request = NormalizedRequest(
        request_id="req-idempotent-rag",
        workflow_run_id="wf-idempotent-rag",
        session_id="session-1",
        assistant_message_id="assistant-1",
        org_id="org-1",
        user_id="user-1",
        ext={"idempotency_key": "org-1:session-1:assistant-1:wf-idempotent-rag"},
    )
    output = AgentOutput(
        message_type="assistant_text",
        answer="done",
        route_decision=RouteDecision(
            mode="router_enabled",
            selected_agent="chat",
            sub_route="rag_qa",
            intent="rag_qa",
            reason="test",
        ),
        persistable_output=PersistableOutput(
            rag_queries=[
                RagQueryLog(
                    query="same query",
                    rag_space_id="space-1",
                    top_k=3,
                    hit_count=1,
                    source_graph="chat",
                )
            ]
        ),
    )

    service = QualityAgentOrchestratorService()
    first = await service._persist_chat_result(request, output)
    second = await service._persist_chat_result(request, output)

    assert first is True
    assert second is True
    assert len(updates) == 2
    assert len(rag_logs) == 1
    assert next(iter(rag_logs)).endswith(":rag:0")


@pytest.mark.asyncio
async def test_repeated_materialization_does_not_duplicate_token_ledger_or_alert(monkeypatch):
    alerts: dict[str, dict] = {}
    ledgers: dict[str, SimpleNamespace] = {}
    summary_increments: list[dict] = []
    task_store = {"task": None}

    class FakeSession:
        async def flush(self):
            return None

        async def commit(self):
            return None

    @asynccontextmanager
    async def fake_get_session():
        yield FakeSession()

    class FakeTaskRepository:
        def __init__(self, _session):
            pass

        async def get_by_chat_materialization_key(self, *_args):
            return task_store["task"]

        async def update_status(self, _org_id: str, _task_id: str, status: str):
            task_store["task"].status = status

    class FakeTaskService:
        def __init__(self, _session, _org_id):
            pass

        async def create_task(self, **kwargs):
            task_store["task"] = SimpleNamespace(
                id="task-1",
                product_id=kwargs["product_id"],
                spec_code=kwargs["spec_code"],
                image_urls=kwargs["image_urls"],
                priority=kwargs["priority"],
                meta_data=kwargs["metadata"],
                status="created",
            )
            return task_store["task"]

    class FakeResultRepository:
        def __init__(self, _session):
            pass

        async def upsert_by_task(self, _payload: dict):
            return SimpleNamespace(id="result-1")

    class FakeStabilityRepository:
        def __init__(self, _session):
            pass

        async def upsert_by_task(self, _payload: dict):
            return SimpleNamespace(id="stability-1")

    class FakeAlertRepository:
        def __init__(self, _session):
            pass

        async def create_once(self, data: dict):
            alerts.setdefault(data["idempotency_key"], data)
            return alerts[data["idempotency_key"]]

        async def create(self, data: dict):
            return await self.create_once(data)

    class FakeTokenLedgerRepository:
        def __init__(self, _session):
            pass

        async def get_by_idempotency_key(self, key: str):
            return ledgers.get(key)

        async def create_once(self, data: dict):
            ledger = ledgers.setdefault(
                data["idempotency_key"],
                SimpleNamespace(created_at="created-at", **data),
            )
            return ledger

        async def create(self, data: dict):
            return await self.create_once(data)

    class FakeUserTokenUsageSummaryRepository:
        def __init__(self, _session):
            pass

        async def increment(self, **kwargs):
            summary_increments.append(kwargs)

    class FakeRuleEngineService:
        def __init__(self, _session):
            pass

        async def evaluate_and_get_matches(self, **_kwargs):
            return []

        async def is_in_cooldown(self, *_args, **_kwargs):
            return False

    monkeypatch.setattr(orchestrator_mod, "get_session", fake_get_session)
    monkeypatch.setattr(orchestrator_mod, "TaskRepository", FakeTaskRepository)
    monkeypatch.setattr(orchestrator_mod, "TaskService", FakeTaskService)
    monkeypatch.setattr(orchestrator_mod, "ResultRepository", FakeResultRepository)
    monkeypatch.setattr(orchestrator_mod, "StabilityRepository", FakeStabilityRepository)
    monkeypatch.setattr(orchestrator_mod, "AlertRepository", FakeAlertRepository)
    monkeypatch.setattr(orchestrator_mod, "TokenLedgerRepository", FakeTokenLedgerRepository)
    monkeypatch.setattr(orchestrator_mod, "UserTokenUsageSummaryRepository", FakeUserTokenUsageSummaryRepository)
    monkeypatch.setattr("app.services.rule_engine_service.RuleEngineService", FakeRuleEngineService)
    monkeypatch.setattr(
        "worker.tasks.alert_dispatch_task.dispatch_alert.delay",
        lambda *_args, **_kwargs: None,
    )

    request = NormalizedRequest(
        request_id="req-idempotent-materialize",
        workflow_run_id="wf-idempotent-materialize",
        session_id="session-1",
        assistant_message_id="assistant-1",
        org_id="org-1",
        user_id="user-1",
        ext={"idempotency_key": "org-1:session-1:assistant-1:wf-idempotent-materialize"},
    )
    persistable = PersistableOutput(
        task=TaskAggregate(product_id="P-1", spec_code="STD-1", status="done"),
        result=ResultAggregate(verdict="pass", overall_score=0.95),
        stability=StabilityAggregate(risk_level="low", risk_score=0.1),
        alerts=[AlertEvent(severity="warning", title="review", message="check")],
        token_usage=[TokenUsageEvent(model_key="chat-model", prompt_tokens=2, completion_tokens=3, total_tokens=5)],
    )

    service = QualityAgentOrchestratorService()
    first = await service._materialize_structured_output(
        request,
        persistable,
        source_graph="inspection_task",
        source_kind="structured",
        persist_usage=True,
    )
    second = await service._materialize_structured_output(
        request,
        persistable,
        source_graph="inspection_task",
        source_kind="structured",
        persist_usage=True,
    )

    assert first["task_id"] == second["task_id"] == "task-1"
    assert len(alerts) == 1
    assert len(ledgers) == 1
    assert len(summary_increments) == 1
    assert next(iter(alerts)).endswith(":alert:review")
    assert next(iter(ledgers)).endswith(":token:0:chat-model")
