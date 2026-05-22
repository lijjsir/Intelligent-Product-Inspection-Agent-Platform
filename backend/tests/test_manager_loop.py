from __future__ import annotations

import pytest

from agent.contracts.quality_contracts import NormalizedAttachment, NormalizedRequest
from agent.router.manager_loop import ManagerLoop


@pytest.fixture
def mock_chat_model(monkeypatch):
    async def fake_call_model(self, state, request, prompt):
        return f"[模型回复]：{state.original_query}"
    monkeypatch.setattr(
        "agent.router.executors.chat_executor.ChatExecutor._call_model",
        fake_call_model,
    )


def _request(**overrides) -> NormalizedRequest:
    payload = {
        "request_id": "req-1",
        "workflow_run_id": "wf-1",
        "org_id": "org-1",
        "user_id": "user-1",
        "session_id": "session-1",
        "query": "你好",
        "ext": {"surface": "chat"},
    }
    payload.update(overrides)
    return NormalizedRequest(**payload)


@pytest.mark.asyncio
async def test_chat_general_returns_route_trace_and_no_action(mock_chat_model):
    output = await ManagerLoop().run(_request(query="你好", ext={"surface": "chat"}))
    payload = output.agent_output

    assert output.status == "completed"
    assert output.route_decision.selected_agent == "chat"
    assert output.route_decision.sub_route == "general_chat"
    assert payload["ui_schema"] == "chat_answer_v2"
    assert payload["route_trace"]["capabilities_used"] == ["chat.general"]
    assert payload["route_trace"]["satisfied"] is True
    assert payload["artifacts"] == []


@pytest.mark.asyncio
async def test_chat_image_understanding_is_informal_and_does_not_create_task(mock_chat_model):
    output = await ManagerLoop().run(
        _request(
            query="这个图片有没有问题？",
            attachments=[
                NormalizedAttachment(
                    id="att-1",
                    name="sample.png",
                    url="https://example.test/sample.png",
                    kind="image",
                )
            ],
            ext={"surface": "chat"},
        )
    )
    payload = output.agent_output

    assert output.route_decision.selected_agent == "chat"
    assert output.route_decision.sub_route == "image_understanding"
    assert payload["message_type"] == "image_analysis"
    assert "created_task" not in payload or payload["created_task"] is None


@pytest.mark.asyncio
async def test_chat_selected_rag_uses_retrieve_then_compose_without_action(mock_chat_model):
    output = await ManagerLoop().run(
        _request(
            query="根据这个知识库解释 AQL",
            ext={
                "surface": "chat",
                "selected_rag_space": {"id": "rag-1", "name": "标准库"},
                "rag_scope": {"enabled": True, "rag_space_id": "rag-1"},
            },
        )
    )
    payload = output.agent_output

    assert output.route_decision.sub_route == "rag_qa"
    assert payload["route_trace"]["capabilities_used"] == ["rag.retrieve", "chat.response.compose"]
    assert all(item["mode"] != "action" for item in payload["route_trace"]["steps"])


@pytest.mark.asyncio
async def test_task_status_uses_task_status_message_type(mock_chat_model):
    output = await ManagerLoop().run(
        _request(
            query="查询任务状态 status",
            ext={"surface": "chat"},
        )
    )

    assert output.route_decision.sub_route == "quality_task_status"
    assert output.agent_output["message_type"] == "task_status"


@pytest.mark.asyncio
async def test_selected_rag_space_does_not_force_rag_for_general_chat(mock_chat_model):
    output = await ManagerLoop().run(
        _request(
            query="hello",
            ext={
                "surface": "chat",
                "selected_rag_space": {"id": "rag-1", "name": "standards"},
                "rag_scope": {"enabled": True, "rag_space_id": "rag-1", "mode": "auto"},
            },
        )
    )

    assert output.route_decision.sub_route == "general_chat"
    assert output.agent_output["route_trace"]["capabilities_used"] == ["chat.general"]


@pytest.mark.asyncio
async def test_general_chat_accepts_gateway_parsed_json_response(monkeypatch):
    class FakeModelConfigService:
        def __init__(self, session, org_id: str):
            pass

        async def list_runtime_models(self):
            return [{"id": "model-config-1", "model_key": "chat-fast-json", "model_type": "chat"}]

    class FakeGateway:
        async def select_runtime(self, models, *, model_types, reserve=False, excluded_runtime_ids=None):
            return {
                "runtime_key": "chat-runtime",
                "model_config_id": "model-config-1",
                "model_id": "chat-fast-json",
                "provider": "fake",
                "failover_depth": 0,
            }

    class FakeLLMClient:
        def __init__(self, **kwargs):
            pass

        async def chat(self, messages, **kwargs):
            return {"answer": "LLM answer about Chongqing, not a fixed echo."}

    monkeypatch.setattr("agent.router.manager_loop.ModelConfigService", FakeModelConfigService)
    monkeypatch.setattr("agent.router.manager_loop.LLMGateway", lambda: FakeGateway())
    monkeypatch.setattr("agent.router.executors.chat_executor.LLMClient", FakeLLMClient)

    output = await ManagerLoop().run(
        _request(query="How is Chongqing as a city?", ext={"surface": "chat"}),
        db_session="db-session",
    )

    assert output.status == "completed"
    assert output.route_decision.sub_route == "general_chat"
    assert output.agent_output["answer"] == "LLM answer about Chongqing, not a fixed echo."


@pytest.mark.asyncio
async def test_chat_task_request_is_blocked_with_task_page_guidance(mock_chat_model):
    output = await ManagerLoop().run(
        _request(
            query="帮我创建正式质检任务并执行",
            ext={"surface": "chat"},
        )
    )
    payload = output.agent_output

    assert output.status == "blocked"
    assert output.route_decision.selected_agent == "chat"
    assert output.route_decision.sub_route == "action_blocked"
    assert payload["message_type"] == "action_blocked"
    assert payload["route_trace"]["satisfied"] is False


@pytest.mark.asyncio
async def test_chat_rag_ingest_request_is_blocked_by_surface_boundary(mock_chat_model):
    output = await ManagerLoop().run(
        _request(
            query="请把这个文件加入知识库",
            ext={"surface": "chat"},
        )
    )

    assert output.status == "blocked"
    assert output.route_decision.sub_route == "action_blocked"
    assert output.agent_output["created_task"] is None
    assert output.agent_output["route_trace"]["steps"][0]["capability_key"] == "rag.ingest"


@pytest.mark.asyncio
async def test_quality_task_requires_explicit_action_intent_for_formal_inspection(mock_chat_model):
    output = await ManagerLoop().run(
        _request(
            query="执行质量检测",
            workspace="quality_task",
            metadata={"product_id": "P001", "spec_code": "STD-1", "priority": 5},
            ext={
                "surface": "quality_task",
                "allowed_modes": ["action", "report", "answer"],
            },
        )
    )
    payload = output.agent_output

    assert output.status == "blocked"
    assert output.route_decision.sub_route == "inspection_execute"
    assert "action_intent" in payload["answer"]


@pytest.mark.asyncio
async def test_manager_respects_forbidden_modes_even_on_quality_surface(mock_chat_model):
    output = await ManagerLoop().run(
        _request(
            query="执行质量检测",
            workspace="quality_task",
            metadata={"product_id": "P001", "spec_code": "STD-1", "priority": 5},
            ext={
                "surface": "quality_task",
                "allowed_modes": ["action", "report", "answer"],
                "forbidden_modes": ["action"],
                "action_intent": "quality_inspection_execute",
            },
        )
    )

    assert output.status == "blocked"
    assert output.route_decision.sub_route == "inspection_execute"
    assert output.agent_output["route_trace"]["errors"][0]["message"] == "当前页面已禁止模式：action"


@pytest.mark.asyncio
async def test_quality_task_formal_inspection_dispatches_action(monkeypatch):
    calls: list[str] = []

    async def fake_run(self, request, route_decision):
        calls.append(route_decision.sub_route)
        from agent.contracts import AgentOutput, PersistableOutput, TaskAggregate

        return AgentOutput(
            message_type="task_result",
            answer="formal inspection queued",
            summary="queued",
            action_state="queued",
            persistable_output=PersistableOutput(
                task=TaskAggregate(id="task-1", product_id="P001", spec_code="STD-1", status="queued")
            ),
        )

    monkeypatch.setattr("agent.subgraphs.inspection_task.graph.InspectionTaskGraph.run", fake_run)

    output = await ManagerLoop().run(
        _request(
            query="执行质量检测",
            workspace="quality_task",
            metadata={"product_id": "P001", "spec_code": "STD-1", "priority": 5},
            ext={
                "surface": "quality_task",
                "allowed_modes": ["action", "report", "answer"],
                "action_intent": "quality_inspection_execute",
            },
        )
    )

    assert calls == ["inspection_execute"]
    assert output.status == "completed"
    assert output.route_decision.selected_agent == "inspection_task"
    assert output.agent_output["route_trace"]["capabilities_used"] == ["quality.inspection.execute"]


@pytest.mark.asyncio
async def test_manager_model_resolves_from_chat_model_configs(monkeypatch):
    class FakeModelConfigService:
        def __init__(self, session, org_id: str):
            assert session == "db-session"
            assert org_id == "org-1"

        async def list_runtime_models(self):
            return [
                {
                    "id": "model-config-1",
                    "provider": "openai",
                    "model_key": "chat-fast-json",
                    "model_type": "chat",
                    "priority": 1,
                }
            ]

    class FakeGateway:
        async def select_runtime(self, *, models, model_types, reserve):
            assert models[0]["model_type"] == "chat"
            assert model_types == {"chat"}
            assert reserve is False
            return {
                "runtime_key": "openai:chat-fast-json",
                "model_config_id": "model-config-1",
                "model_id": "chat-fast-json",
                "provider": "openai",
                "failover_depth": 0,
            }

    monkeypatch.setattr("agent.router.manager_loop.ModelConfigService", FakeModelConfigService)
    monkeypatch.setattr("agent.router.manager_loop.LLMGateway", lambda: FakeGateway())

    output = await ManagerLoop().run(_request(query="浣犲ソ", ext={"surface": "chat"}), db_session="db-session")

    manager_model = output.agent_output["route_trace"]["manager_model"]
    assert manager_model["logical_name"] == "manager_model"
    assert manager_model["model_type"] == "chat"
    assert manager_model["model_config_id"] == "model-config-1"
    assert manager_model["model_id"] == "chat-fast-json"


@pytest.mark.asyncio
async def test_general_chat_uses_chat_model_when_available(monkeypatch):
    class FakeModelConfigService:
        def __init__(self, session, org_id: str):
            pass

        async def list_runtime_models(self):
            return [{"id": "model-config-1", "model_key": "chat-fast-json", "model_type": "chat"}]

    class FakeGateway:
        async def select_runtime(self, models, *, model_types, reserve=False, excluded_runtime_ids=None):
            return {
                "runtime_key": "chat-runtime",
                "model_config_id": "model-config-1",
                "model_id": "chat-fast-json",
                "provider": "fake",
                "failover_depth": 0,
            }

    class FakeLLMClient:
        def __init__(self, **kwargs):
            pass

        async def chat(self, messages, **kwargs):
            return {"choices": [{"message": {"content": '{"answer":"我是 ChatAgent，可以正常聊天。"}'}}]}

    monkeypatch.setattr("agent.router.manager_loop.ModelConfigService", FakeModelConfigService)
    monkeypatch.setattr("agent.router.manager_loop.LLMGateway", lambda: FakeGateway())
    monkeypatch.setattr("agent.router.executors.chat_executor.LLMClient", FakeLLMClient)

    output = await ManagerLoop().run(
        _request(query="你是什么模型，可以聊天吗", ext={"surface": "chat"}),
        db_session="db-session",
    )

    assert output.status == "completed"
    assert output.route_decision.sub_route == "general_chat"
    assert output.agent_output["answer"] == "我是 ChatAgent，可以正常聊天。"
    assert output.agent_output["route_trace"]["capabilities_used"] == ["chat.general"]
