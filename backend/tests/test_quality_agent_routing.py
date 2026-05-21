import pytest

from agent.contracts import RouteDecision, RouteSignals
from agent.contracts.quality_contracts import NormalizedRequest
from agent.graphs.memory_manager.policy import select_subgraph
from agent.router.contracts import AgentRouteDecision, AgentRouterInput
from agent.router.route_policy import AgentRoutePolicy
from agent.subgraphs.inspection_task.graph import InspectionTaskGraph
from app.core.config import settings


def test_select_subgraph_prefers_legacy_for_task_keywords(monkeypatch):
    monkeypatch.setattr(settings, "agent_route_mode", "router_enabled")
    decision = select_subgraph(
        RouteSignals(
            has_task_keyword=True,
            has_file_attachments=True,
            attachment_types=["txt"],
        )
    )
    assert decision.selected_agent == "inspection_task"
    assert decision.sub_route == "inspection_execute"


def test_select_subgraph_routes_non_image_files_to_native(monkeypatch):
    monkeypatch.setattr(settings, "agent_route_mode", "router_enabled")
    decision = select_subgraph(
        RouteSignals(
            has_task_keyword=False,
            has_images=False,
            has_file_attachments=True,
            attachment_types=["txt"],
        )
    )
    assert decision.selected_agent == "inspection_task"
    assert decision.sub_route == "inspection_execute"


def test_select_subgraph_routes_images_to_legacy(monkeypatch):
    monkeypatch.setattr(settings, "agent_route_mode", "router_enabled")
    decision = select_subgraph(
        RouteSignals(
            has_images=True,
            attachment_types=["image"],
        )
    )
    assert decision.selected_agent == "inspection_task"
    assert decision.sub_route == "inspection_execute"


def test_route_decision_accepts_new_chat_agent_fields():
    decision = RouteDecision(selected_agent="chat", sub_route="general_chat")

    assert decision.selected_agent == "chat"
    assert decision.sub_route == "general_chat"


def test_route_policy_image_quality_question_waits_for_formal_submission():
    decision = AgentRoutePolicy().decide(
        AgentRouterInput(
            query="这个划痕算不算不合格？",
            attachments=[{"name": "sample.png", "kind": "image"}],
        )
    )

    assert decision.selected_agent == "inspection_task"
    assert decision.sub_route == "quality_qa"


def test_route_policy_forced_inspection_without_subroute_keeps_task_draft_gate():
    decision = AgentRoutePolicy().decide(
        AgentRouterInput(
            query="创建质检任务，产品编号 001",
            ext={"route_hints": {"force_agent": "inspection_task"}},
        )
    )

    assert decision.selected_agent == "inspection_task"
    assert decision.sub_route == "task_create"


@pytest.mark.asyncio
async def test_route_policy_uses_model_classifier_for_ambiguous_input(monkeypatch):
    calls: list[str] = []

    class FakeClassifier:
        async def classify(self, *, query, llm_client=None, ext=None):
            calls.append(query)
            return AgentRouteDecision(
                selected_agent="inspection_task",
                sub_route="quality_qa",
                intent="quality_qa",
            )

    monkeypatch.setattr("agent.router.model_classifier.ModelClassifier", lambda: FakeClassifier())

    decision = await AgentRoutePolicy().decide_with_model(
        AgentRouterInput(query="这个呢"),
        llm_client=object(),
    )

    assert calls == ["这个呢"]
    assert decision.selected_agent == "inspection_task"
    assert decision.sub_route == "quality_qa"


@pytest.mark.asyncio
async def test_inspection_task_quality_qa_does_not_run_formal_inspection(monkeypatch):
    async def fail_if_called(self, request):
        raise AssertionError("formal inspection should only run for inspection_execute")

    monkeypatch.setattr(InspectionTaskGraph, "_run_structured_inspection", fail_if_called)

    # Mock the LLM path: _run_quality_qa calls get_session → ModelConfigService → LLMGateway → LLMClient
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock, MagicMock

    class FakeSession:
        async def commit(self): pass
        async def rollback(self): pass
        async def close(self): pass

    @asynccontextmanager
    async def fake_get_session():
        yield FakeSession()

    monkeypatch.setattr(
        "agent.subgraphs.inspection_task.graph.get_session",
        fake_get_session,
    )
    monkeypatch.setattr(
        "agent.prompts.prompt_builder.get_session",
        fake_get_session,
    )
    monkeypatch.setattr(
        "agent.subgraphs.inspection_task.graph.ModelConfigService",
        lambda session, org_id: MagicMock(list_runtime_models=AsyncMock(return_value=[])),
    )
    # Make LLMGateway.select_runtime return None to trigger the no-model fallback
    fake_gateway = MagicMock()
    fake_gateway.select_runtime = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "agent.subgraphs.inspection_task.graph.LLMGateway",
        lambda: fake_gateway,
    )

    output = await InspectionTaskGraph().run(
        NormalizedRequest(
            request_id="req-1",
            workflow_run_id="wf-1",
            org_id="org-1",
            user_id="user-1",
            query="这个划痕算不算不合格？",
        ),
        AgentRouteDecision(selected_agent="inspection_task", sub_route="quality_qa", intent="quality_qa"),
    )

    assert output.message_type == "quality_answer"
    assert output.persistable_output.task is None


@pytest.mark.asyncio
async def test_inspection_task_quality_qa_uses_prompt_admin_override(monkeypatch):
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock, MagicMock

    captured_messages: list[list[dict[str, str]]] = []

    class FakeSession:
        async def commit(self): pass
        async def rollback(self): pass
        async def close(self): pass

    @asynccontextmanager
    async def fake_get_session():
        yield FakeSession()

    class FakeLLMClient:
        def __init__(self, **kwargs):
            return None

        async def chat(self, messages, *args, **kwargs):
            captured_messages.append(messages)
            return {"answer": "ok", "summary": "override used"}

    async def fake_prompt_get(self, prompt_key: str, *, org_id: str):
        assert prompt_key == "inspection.quality_qa.system"
        assert org_id == "org-1"
        return "INSPECTION_OVERRIDE_FROM_DB"

    monkeypatch.setattr(
        "agent.subgraphs.inspection_task.graph.get_session",
        fake_get_session,
    )
    monkeypatch.setattr(
        "agent.prompts.prompt_builder.get_session",
        fake_get_session,
    )
    monkeypatch.setattr(
        "agent.subgraphs.inspection_task.graph.ModelConfigService",
        lambda session, org_id: MagicMock(list_runtime_models=AsyncMock(return_value=[{
            "provider": "deepseek",
            "model_key": "deepseek-v4-flash",
            "endpoint": "https://api.deepseek.com",
            "api_key": "sk-db",
        }])),
    )
    fake_gateway = MagicMock()
    fake_gateway.select_runtime = AsyncMock(return_value={
        "model_id": "deepseek-v4-flash",
        "base_url": "https://api.deepseek.com",
        "api_key": "sk-db",
        "provider": "deepseek",
        "input_price_per_million": None,
        "output_price_per_million": None,
    })
    monkeypatch.setattr(
        "agent.subgraphs.inspection_task.graph.LLMGateway",
        lambda: fake_gateway,
    )
    monkeypatch.setattr(
        "agent.subgraphs.inspection_task.graph.LLMClient",
        FakeLLMClient,
    )
    monkeypatch.setattr("app.services.prompt_admin_service.PromptResolver.get", fake_prompt_get)

    output = await InspectionTaskGraph().run(
        NormalizedRequest(
            request_id="req-override",
            workflow_run_id="wf-override",
            org_id="org-1",
            user_id="user-1",
            query="这个划痕算不算不合格？",
        ),
        AgentRouteDecision(selected_agent="inspection_task", sub_route="quality_qa", intent="quality_qa"),
    )

    assert output.message_type == "quality_answer"
    assert captured_messages[0][0]["content"] == "INSPECTION_OVERRIDE_FROM_DB"


@pytest.mark.asyncio
async def test_inspection_task_inspection_execute_runs_formal_inspection(monkeypatch):
    calls: list[str] = []

    async def fake_structured(self, request):
        calls.append(request.request_id)
        from agent.contracts import AgentOutput

        return AgentOutput(message_type="task_result", answer="done")

    monkeypatch.setattr(InspectionTaskGraph, "_run_structured_inspection", fake_structured)

    output = await InspectionTaskGraph().run(
        NormalizedRequest(
            request_id="req-2",
            workflow_run_id="wf-2",
            org_id="org-1",
            user_id="user-1",
            query="开始检测",
        ),
        AgentRouteDecision(
            selected_agent="inspection_task",
            sub_route="inspection_execute",
            intent="inspection_execute",
        ),
    )

    assert calls == ["req-2"]
    assert output.message_type == "task_result"
