from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.contracts.quality_contracts import NormalizedAttachment, NormalizedRequest
from agent.router.contracts import AgentPlanStep
from agent.router.executors.chat_executor import ChatExecutor
from agent.router.executors.vision_executor import VisionExecutor
from agent.router.manager_state import ManagerState
from agent.router.manager_loop import ManagerLoop
from agent.tools.contracts import ToolResult, ToolSpec


@pytest.fixture
def mock_chat_model(monkeypatch):
    async def fake_call_model(self, state, request, prompt, **kwargs):
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
async def test_vision_understanding_does_not_select_text_only_chat_runtime(monkeypatch):
    seen: dict[str, object] = {}

    class FakeModelConfigService:
        def __init__(self, session, org_id: str):
            pass

        async def list_runtime_models(self):
            return [{"id": "chat-1", "model_key": "text-only", "model_type": "chat"}]

    class FakeGateway:
        async def select_runtime(self, models, *, model_types, reserve=False, excluded_runtime_ids=None):
            seen["model_types"] = set(model_types)
            return None

    monkeypatch.setattr("app.services.model_config_service.ModelConfigService", FakeModelConfigService)
    monkeypatch.setattr("agent.router.executors.vision_executor.LLMGateway", lambda: FakeGateway())

    state = ManagerState(
        request_id="req-1",
        workflow_run_id="wf-1",
        original_query="这个图片的内容是什么",
        org_id="org-1",
        user_id="user-1",
        session_id="session-1",
        selected_agent="chat",
    )
    routed = [{"attachment": {"url": "https://example.test/apple.jpg"}, "node": {}}]

    result = await VisionExecutor()._try_multimodal_understanding(
        routed,
        state,
        _request(query="这个图片的内容是什么"),
        db_session=object(),
    )

    assert seen["model_types"] == {"multimodal", "vision", "vlm"}
    assert result == {"error": "no multimodal/vision model configured in this org"}


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
async def test_selected_rag_space_forces_rag_for_general_question(mock_chat_model):
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

    assert output.route_decision.sub_route == "rag_qa"
    assert output.agent_output["route_trace"]["capabilities_used"] == ["rag.retrieve", "chat.response.compose"]


@pytest.mark.asyncio
async def test_selected_rag_question_injects_retrieved_evidence_into_compose_prompt(monkeypatch):
    captured = {}

    class FakeRagRetrievalService:
        def __init__(self, session, *, org_id: str, user_id: str | None = None):
            pass

        async def search(self, *, rag_space_id, query, top_k=4, scope_node_ids=None):
            return {
                "rag_space_id": rag_space_id,
                "rag_space_name": "Test Standards",
                "hits": [
                    {
                        "id": "chunk-1",
                        "title": "用户档案",
                        "source": "profile.md",
                        "quote": "用户姓名是张三。",
                        "score": 0.91,
                    }
                ],
                "hit_count": 1,
            }

    async def fake_call_model(self, state, request, prompt, **kwargs):
        captured["prompt"] = prompt
        return "根据知识库，您的名字是张三。[RAG-1]"

    monkeypatch.setattr("app.services.rag_retrieval_service.RagRetrievalService", FakeRagRetrievalService)
    monkeypatch.setattr("agent.router.executors.chat_executor.ChatExecutor._call_model", fake_call_model)

    output = await ManagerLoop().run(
        _request(
            query="我的名字是什么",
            ext={
                "surface": "chat",
                "selected_rag_space": {"id": "rag-1", "name": "Test Standards"},
                "rag_scope": {"enabled": True, "rag_space_id": "rag-1"},
            },
        ),
        db_session=object(),
    )

    prompt = captured["prompt"]
    assert output.route_decision.sub_route == "rag_qa"
    assert "用户姓名是张三" in prompt
    assert "[RAG-1]" in prompt
    assert "仍然要继续回答用户问题" in prompt
    assert "不要伪造知识库引用" in prompt
    assert output.agent_output["answer"] == "根据知识库，您的名字是张三。[RAG-1]"
    assert output.agent_output["citations"][0]["quote"] == "用户姓名是张三。"
    rag_log = output.agent_output["persistable_output"]["rag_queries"][0]
    assert rag_log["rag_space_id"] == "rag-1"
    assert rag_log["hit_count"] == 1
    assert rag_log["source_graph"] == "manager"
    assert rag_log["metadata"]["used_citations"][0]["quote"] == "用户姓名是张三。"


@pytest.mark.asyncio
async def test_selected_rag_empty_recall_still_lets_model_answer(monkeypatch):
    captured = {}

    class FakeRagRetrievalService:
        def __init__(self, session, *, org_id: str, user_id: str | None = None):
            pass

        async def search(self, *, rag_space_id, query, top_k=4, scope_node_ids=None):
            return {
                "rag_space_id": rag_space_id,
                "rag_space_name": "Empty Space",
                "hits": [],
                "hit_count": 0,
                "latency_ms": 7,
            }

    async def fake_call_model(self, state, request, prompt, **kwargs):
        captured["prompt"] = prompt
        return "当前知识库没有提供可引用依据。基于通用知识，我可以继续回答这个问题。"

    monkeypatch.setattr("app.services.rag_retrieval_service.RagRetrievalService", FakeRagRetrievalService)
    monkeypatch.setattr("agent.router.executors.chat_executor.ChatExecutor._call_model", fake_call_model)

    output = await ManagerLoop().run(
        _request(
            query="张雪峰老师现状",
            ext={
                "surface": "chat",
                "selected_rag_space": {"id": "rag-empty", "name": "Empty Space"},
                "rag_scope": {"enabled": True, "rag_space_id": "rag-empty"},
            },
        ),
        db_session=object(),
    )

    prompt = captured["prompt"]
    assert output.route_decision.sub_route == "rag_qa"
    assert "未检索到可用片段" in prompt
    assert "仍然要继续回答用户问题" in prompt
    assert "不要伪造知识库引用" in prompt
    assert output.agent_output["answer"] == "当前知识库没有提供可引用依据。基于通用知识，我可以继续回答这个问题。"
    assert output.agent_output["citations"] == []
    rag_log = output.agent_output["persistable_output"]["rag_queries"][0]
    assert rag_log["hit_count"] == 0
    assert rag_log["metadata"]["empty_recall"] is True


@pytest.mark.asyncio
async def test_selected_rag_hit_without_answer_marker_is_not_counted_as_used(monkeypatch):
    class FakeRagRetrievalService:
        def __init__(self, session, *, org_id: str, user_id: str | None = None):
            pass

        async def search(self, *, rag_space_id, query, top_k=4, scope_node_ids=None):
            return {
                "rag_space_id": rag_space_id,
                "rag_space_name": "Test Standards",
                "hits": [
                    {
                        "id": "chunk-1",
                        "title": "Profile",
                        "source": "profile.md",
                        "quote": "The stored name is Zhang San.",
                        "score": 0.91,
                    }
                ],
                "hit_count": 1,
            }

    async def fake_call_model(self, state, request, prompt, **kwargs):
        return "The answer was generated without a RAG citation marker."

    monkeypatch.setattr("app.services.rag_retrieval_service.RagRetrievalService", FakeRagRetrievalService)
    monkeypatch.setattr("agent.router.executors.chat_executor.ChatExecutor._call_model", fake_call_model)

    output = await ManagerLoop().run(
        _request(
            query="what is my name",
            ext={
                "surface": "chat",
                "selected_rag_space": {"id": "rag-1", "name": "Test Standards"},
                "rag_scope": {"enabled": True, "rag_space_id": "rag-1"},
            },
        ),
        db_session=object(),
    )

    assert output.agent_output["citations"] == []
    assert output.agent_output["rag_summary"]["hit_count"] == 1
    assert output.agent_output["rag_summary"]["citation_coverage"] == 0.0
    rag_log = output.agent_output["persistable_output"]["rag_queries"][0]
    assert rag_log["hit_count"] == 1
    assert rag_log["citation_coverage"] == 0.0
    assert rag_log["metadata"]["evidence_found"] is True
    assert rag_log["metadata"]["evidence_used"] is False
    assert rag_log["metadata"]["used_citations"] == []


@pytest.mark.asyncio
async def test_rag_compose_lets_model_skip_web_tool_when_not_forced(monkeypatch):
    invoked: list[tuple[str, dict]] = []
    captured_tools: list[str] = []

    class FakeLLMClient:
        def __init__(self, **kwargs):
            self.model_id = kwargs.get("model_id")

        async def chat_with_tools(self, messages, **kwargs):
            captured_tools.extend(tool["function"]["name"] for tool in kwargs["tools"])
            return {
                "content": '{"answer":"Model decided no tool is needed."}',
                "tool_calls": None,
            }

        async def _post_json(self, path, payload, **kwargs):
            raise AssertionError("No final tool answer should be generated when no tool is used")

    class FakeInvoker:
        async def invoke(self, *, tool_name, arguments, context):
            invoked.append((tool_name, arguments))
            raise AssertionError("Tool should not be invoked unless the model calls it")

    monkeypatch.setattr("agent.router.executors.chat_executor.LLMClient", FakeLLMClient)

    state = ManagerState(
        request_id="req-1",
        workflow_run_id="wf-1",
        original_query="basic product explanation",
        org_id="org-1",
        user_id="user-1",
        session_id="session-1",
        selected_agent="chat",
        manager_model_runtime={"model_id": "fake-model", "provider": "fake"},
        selected_rag_space={"id": "rag-1", "name": "Test Standards"},
    )
    state.available_tools = [
        ToolSpec(
            name="web.search",
            title="Web search",
            description="Search the web",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer"},
                },
                "required": ["query"],
            },
        )
    ]
    state.tool_invoker = FakeInvoker()

    observation, artifacts = await ChatExecutor().execute(
        AgentPlanStep(
            step_id="compose-1",
            capability_key="chat.response.compose",
            agent="chat",
            operation="compose",
            mode="answer",
        ),
        state,
        _request(query="basic product explanation", ext={"surface": "chat"}),
    )

    assert observation.status == "success"
    assert captured_tools == ["web_search"]
    assert invoked == []
    assert state.used_tool_calls == 0
    assert artifacts[0].content["answer"] == "Model decided no tool is needed."


@pytest.mark.asyncio
async def test_rag_compose_forced_web_search_invokes_web_tool(monkeypatch):
    invoked: list[tuple[str, dict]] = []

    class FakeLLMClient:
        def __init__(self, **kwargs):
            self.model_id = kwargs.get("model_id")

        async def chat_with_tools(self, messages, **kwargs):
            raise AssertionError("force_web_search should invoke web.search before model tool_calls")

        async def _post_json(self, path, payload, **kwargs):
            assert any(message.get("role") == "tool" for message in payload["messages"])
            return {
                "choices": [
                    {
                        "message": {
                            "content": "Web search result based answer.",
                        }
                    }
                ]
            }

    class FakeInvoker:
        async def invoke(self, *, tool_name, arguments, context):
            invoked.append((tool_name, arguments))
            return ToolResult(
                tool_name=tool_name,
                status="success",
                data={
                    "results": [
                        {
                            "title": "Latest status",
                            "snippet": "Fresh web result.",
                            "url": "https://example.test/latest",
                        }
                    ]
                },
            )

    monkeypatch.setattr("agent.router.executors.chat_executor.LLMClient", FakeLLMClient)

    state = ManagerState(
        request_id="req-1",
        workflow_run_id="wf-1",
        original_query="zhang xuefeng status",
        org_id="org-1",
        user_id="user-1",
        session_id="session-1",
        selected_agent="chat",
        manager_model_runtime={"model_id": "fake-model", "provider": "fake"},
        selected_rag_space={"id": "rag-1", "name": "Test Standards"},
    )
    state.forced_tool_names = ["web.search"]
    state.available_tools = [
        ToolSpec(
            name="web.search",
            title="Web search",
            description="Search the web",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer"},
                },
                "required": ["query"],
            },
        )
    ]
    state.tool_invoker = FakeInvoker()

    observation, artifacts = await ChatExecutor().execute(
        AgentPlanStep(
            step_id="compose-1",
            capability_key="chat.response.compose",
            agent="chat",
            operation="compose",
            mode="answer",
        ),
        state,
        _request(query="zhang xuefeng status", ext={"surface": "chat", "force_web_search": True}),
    )

    assert observation.status == "success"
    assert invoked == [
        ("web.search", {"query": "zhang xuefeng status", "max_results": 5, "region": "cn-zh"})
    ]
    assert state.used_tool_calls == 1
    assert artifacts[0].content["answer"] == "Web search result based answer."


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

        async def chat_with_tools(self, messages, **kwargs):
            return {"content": "{\"answer\":\"LLM answer about Chongqing, not a fixed echo.\"}", "tool_calls": None}

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
async def test_general_chat_lets_model_decide_no_tool_with_json_mode(monkeypatch):
    class FakeModelConfigService:
        def __init__(self, session, org_id: str):
            pass

        async def list_runtime_models(self):
            return [{"id": "model-config-1", "model_key": "chat-fast", "model_type": "chat"}]

    class FakeGateway:
        async def select_runtime(self, models, *, model_types, reserve=False, excluded_runtime_ids=None):
            return {
                "runtime_key": "chat-runtime",
                "model_config_id": "model-config-1",
                "model_id": "chat-fast",
                "provider": "fake",
                "failover_depth": 0,
            }

    class FakeLLMClient:
        def __init__(self, **kwargs):
            pass

        async def chat_with_tools(self, messages, **kwargs):
            assert kwargs.get("tools")
            names = [tool["function"]["name"] for tool in kwargs["tools"]]
            assert all("." not in name for name in names)
            return {
                "content": "{\"answer\":\"张雪峰最近仍以教育咨询和公开表达为主。\"}",
                "tool_calls": None,
            }

        async def chat(self, messages, **kwargs):
            raise AssertionError("未调用工具时不需要二次汇总")

    monkeypatch.setattr("agent.router.manager_loop.ModelConfigService", FakeModelConfigService)
    monkeypatch.setattr("agent.router.manager_loop.LLMGateway", lambda: FakeGateway())
    monkeypatch.setattr("agent.router.executors.chat_executor.LLMClient", FakeLLMClient)

    output = await ManagerLoop().run(
        _request(query="张雪峰现在怎么样了", ext={"surface": "chat"}),
        db_session="db-session",
    )

    assert output.status == "completed"
    assert output.route_decision.sub_route == "general_chat"
    assert output.agent_output["answer"] == "张雪峰最近仍以教育咨询和公开表达为主。"


@pytest.mark.asyncio
async def test_general_chat_force_web_search_runs_tool_once_through_manager(monkeypatch):
    invoked: list[tuple[str, dict]] = []

    class FakeModelConfigService:
        def __init__(self, session, org_id: str):
            pass

        async def list_runtime_models(self):
            return [{"id": "model-config-1", "model_key": "chat-fast", "model_type": "chat"}]

    class FakeGateway:
        async def select_runtime(self, models, *, model_types, reserve=False, excluded_runtime_ids=None):
            return {
                "runtime_key": "chat-runtime",
                "model_config_id": "model-config-1",
                "model_id": "chat-fast",
                "provider": "fake",
                "failover_depth": 0,
            }

    class FakeLLMClient:
        def __init__(self, **kwargs):
            self.model_id = kwargs.get("model_id")

        async def chat_with_tools(self, messages, **kwargs):
            raise AssertionError("force_web_search must call web.search before asking the model")

        async def chat(self, messages, **kwargs):
            joined = "\n".join(str(message.get("content") or "") for message in messages)
            assert "web_search_results result" in joined
            assert "results" in joined
            return {"answer": "根据联网搜索结果，张雪峰近期仍有教育咨询相关公开动态。"}

    async def fake_invoke(self, *, tool_name, arguments, context):
        invoked.append((tool_name, arguments))
        return ToolResult(
            tool_name=tool_name,
            status="success",
            data={"results": [{"title": "张雪峰动态", "snippet": "教育咨询相关公开动态"}]},
        )

    monkeypatch.setattr("agent.router.manager_loop.ModelConfigService", FakeModelConfigService)
    monkeypatch.setattr("agent.router.manager_loop.LLMGateway", lambda: FakeGateway())
    monkeypatch.setattr("agent.router.executors.chat_executor.LLMClient", FakeLLMClient)
    monkeypatch.setattr("agent.tools.invoker.ToolInvoker.invoke", fake_invoke)

    output = await ManagerLoop().run(
        _request(query="张雪峰现在怎么样了", ext={"surface": "chat", "force_web_search": True}),
        db_session="db-session",
    )

    assert output.status == "completed"
    assert output.agent_output["answer"] == "根据联网搜索结果，张雪峰近期仍有教育咨询相关公开动态。"
    assert invoked == [
        ("web.search", {"query": "张雪峰现在怎么样了", "max_results": 5, "region": "cn-zh"})
    ]
    assert output.agent_output["route_trace"]["capabilities_used"] == ["web.search", "chat.response.compose"]
    assert [item["type"] for item in output.agent_output["artifacts"]] == [
        "web_search_results",
        "composed_response",
    ]


@pytest.mark.asyncio
async def test_tool_loop_final_answer_receives_tool_context():
    final_call: dict[str, object] = {}

    class FakeClient:
        async def chat_with_tools(self, messages, **kwargs):
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "name": "web_search",
                        "arguments": {"query": "张雪峰现在怎么样了"},
                    }
                ],
            }

        async def chat(self, messages, **kwargs):
            final_call["messages"] = messages
            return {"answer": "根据工具结果，张雪峰近期仍以教育咨询和公开表达为主。"}

    class FakeInvoker:
        async def invoke(self, *, tool_name, arguments, context):
            assert tool_name == "web.search"
            return SimpleNamespace(
                status="success",
                data={"summary": "张雪峰近期有教育咨询相关公开内容。"},
                error=None,
            )

    state = ManagerState(
        request_id="req-1",
        workflow_run_id="wf-1",
        original_query="张雪峰现在怎么样了",
        org_id="org-1",
        user_id="user-1",
        session_id="session-1",
        selected_agent="chat",
        max_tool_calls=1,
    )
    state.tool_invoker = FakeInvoker()

    answer = await ChatExecutor()._run_tool_loop(
        state,
        FakeClient(),
        "用户问题：张雪峰现在怎么样了",
        [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "search",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        {"web_search": "web.search"},
    )

    final_messages = final_call["messages"]
    assert answer == "根据工具结果，张雪峰近期仍以教育咨询和公开表达为主。"
    assert any(
        message.get("role") == "tool" and "张雪峰近期有教育咨询相关公开内容" in message.get("content", "")
        for message in final_messages
    )
    assert "直接回答用户问题" in final_messages[-1]["content"]


@pytest.mark.asyncio
async def test_tool_loop_coerces_argument_json_content_into_tool_call():
    final_call: dict[str, object] = {}
    invoked: list[tuple[str, dict]] = []

    class FakeClient:
        async def chat_with_tools(self, messages, **kwargs):
            return {
                "content": '{"query":"张雪峰 2025 最新动态 现状","max_results":5,"region":"cn-zh"}',
                "tool_calls": None,
            }

        async def chat(self, messages, **kwargs):
            final_call["messages"] = messages
            return {"answer": "张雪峰近期仍有教育咨询相关公开动态。"}

    class FakeInvoker:
        async def invoke(self, *, tool_name, arguments, context):
            invoked.append((tool_name, arguments))
            return SimpleNamespace(
                status="success",
                data={"results": [{"title": "张雪峰动态", "snippet": "教育咨询相关公开动态"}]},
                error=None,
            )

    state = ManagerState(
        request_id="req-1",
        workflow_run_id="wf-1",
        original_query="张雪峰现在怎么样了",
        org_id="org-1",
        user_id="user-1",
        session_id="session-1",
        selected_agent="chat",
        max_tool_calls=1,
    )
    state.tool_invoker = FakeInvoker()

    answer = await ChatExecutor()._run_tool_loop(
        state,
        FakeClient(),
        "用户问题：张雪峰现在怎么样了",
        [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "search",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "max_results": {"type": "integer"},
                            "region": {"type": "string"},
                        },
                        "required": ["query"],
                    },
                },
            }
        ],
        {"web_search": "web.search"},
    )

    assert answer == "张雪峰近期仍有教育咨询相关公开动态。"
    assert invoked == [
        ("web.search", {"query": "张雪峰 2025 最新动态 现状", "max_results": 5, "region": "cn-zh"})
    ]
    assert any(
        message.get("role") == "tool" and "教育咨询相关公开动态" in message.get("content", "")
        for message in final_call["messages"]
    )


@pytest.mark.asyncio
async def test_tool_loop_forces_web_search_when_model_skips_tool_call():
    final_call: dict[str, object] = {}
    invoked: list[tuple[str, dict]] = []

    class FakeClient:
        async def chat_with_tools(self, messages, **kwargs):
            raise AssertionError("force_web_search must not wait for model tool_calls")

        async def chat(self, messages, **kwargs):
            final_call["messages"] = messages
            return {"answer": "根据联网搜索结果，张雪峰近期仍有教育咨询相关公开动态。"}

    class FakeInvoker:
        async def invoke(self, *, tool_name, arguments, context):
            invoked.append((tool_name, arguments))
            return SimpleNamespace(
                status="success",
                data={"results": [{"title": "张雪峰动态", "snippet": "教育咨询相关公开动态"}]},
                error=None,
            )

    state = ManagerState(
        request_id="req-1",
        workflow_run_id="wf-1",
        original_query="张雪峰现在怎么样了",
        org_id="org-1",
        user_id="user-1",
        session_id="session-1",
        selected_agent="chat",
        max_tool_calls=1,
    )
    state.forced_tool_names = ["web.search"]
    state.tool_invoker = FakeInvoker()

    answer = await ChatExecutor()._run_tool_loop(
        state,
        FakeClient(),
        "用户问题：张雪峰现在怎么样了",
        [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "search",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "max_results": {"type": "integer"},
                            "region": {"type": "string"},
                        },
                        "required": ["query"],
                    },
                },
            }
        ],
        {"web_search": "web.search"},
    )

    assert answer == "根据联网搜索结果，张雪峰近期仍有教育咨询相关公开动态。"
    assert invoked == [
        ("web.search", {"query": "张雪峰现在怎么样了", "max_results": 5, "region": "cn-zh"})
    ]
    assert any(
        message.get("role") == "tool" and "教育咨询相关公开动态" in message.get("content", "")
        for message in final_call["messages"]
    )


def test_llm_tool_names_are_sanitized_and_mapped():
    used_names: set[str] = set()
    web_name = ChatExecutor._llm_tool_name("web.search", used_names)
    rag_name = ChatExecutor._llm_tool_name("rag.standard_search", used_names)

    assert web_name == "web_search"
    assert rag_name == "rag_standard_search"
    assert all("." not in name for name in {web_name, rag_name})


def test_extract_answer_removes_trailing_json_block_from_mixed_model_content():
    content = """根据图片分析结果，这张图展示了三块不同腐烂程度的苹果。

```json
{
  "answer": "三块腐烂苹果，不适宜食用。",
  "summary": "腐烂苹果"
}
```"""

    answer = ChatExecutor._extract_answer({"content": content})

    assert answer == "根据图片分析结果，这张图展示了三块不同腐烂程度的苹果。"


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

        async def chat_with_tools(self, messages, **kwargs):
            return {"content": "{\"answer\":\"我是 ChatAgent，可以正常聊天。\"}", "tool_calls": None}

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
