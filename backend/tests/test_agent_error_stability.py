from __future__ import annotations

import pytest

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import AgentArtifact, AgentPlanStep, AgentRoutePlan
from agent.router.executors.base import observation
from agent.router.executors.chat_executor import ChatExecutor
from agent.router.executors.file_executor import FileExecutor
from agent.router.executors.inspection_task_executor import InspectionTaskExecutor
from agent.router.manager_dispatcher import ManagerDispatcher
from agent.router.manager_evaluator import ManagerEvaluator
from agent.router.manager_loop import ManagerLoop
from agent.router.manager_policy import ManagerPolicy, Understanding
from agent.router.manager_state import ManagerState


def _request(**overrides) -> NormalizedRequest:
    payload = {
        "request_id": "req-err-1",
        "workflow_run_id": "wf-err-1",
        "org_id": "org-1",
        "user_id": "user-1",
        "session_id": "session-1",
        "query": "hello",
        "ext": {"surface": "chat"},
    }
    payload.update(overrides)
    return NormalizedRequest(**payload)


def _state(**overrides) -> ManagerState:
    payload = {
        "request_id": "req-err-1",
        "workflow_run_id": "wf-err-1",
        "original_query": "hello",
        "org_id": "org-1",
        "user_id": "user-1",
        "session_id": "session-1",
        "selected_agent": "chat",
    }
    payload.update(overrides)
    return ManagerState(**payload)


def test_make_agent_error_payload_contains_frontend_contract_fields():
    from agent.router.errors import make_agent_error

    state = _state(trace_id="trace-1")
    error = make_agent_error(
        "RAG_RETRIEVE_FAILED",
        detail={"rag_space_id": "rag-1"},
        source="rag.retrieve",
    )

    payload = error.to_dict(state=state)

    assert payload["code"] == "RAG_RETRIEVE_FAILED"
    assert payload["title"] == "知识库检索失败"
    assert payload["message"]
    assert payload["category"] == "capability"
    assert payload["severity"] == "error"
    assert payload["status"] == "failed"
    assert payload["frontend_visible"] is True
    assert payload["retryable"] is True
    assert payload["user_action"]
    assert payload["trace_id"] == "trace-1"
    assert payload["source"] == "rag.retrieve"
    assert payload["detail"] == {"rag_space_id": "rag-1"}


@pytest.mark.asyncio
async def test_manager_loop_converts_runtime_error_to_agent_error_payload(monkeypatch):
    from agent.router.errors import make_agent_error

    async def fake_understand(self, state):
        raise make_agent_error("CHAT_COMPOSE_MODEL_UNAVAILABLE", source="chat.response.compose")

    monkeypatch.setattr("agent.router.manager_policy.ManagerPolicy.understand", fake_understand)

    output = await ManagerLoop().run(_request())

    assert output.status == "failed"
    assert output.error["code"] == "CHAT_COMPOSE_MODEL_UNAVAILABLE"
    assert output.error["title"] == "回复生成模型不可用"
    assert output.error["category"] == "model"
    assert output.error["status"] == "failed"
    assert output.error["trace_id"]
    assert output.error["workflow_run_id"] == "wf-err-1"
    assert output.agent_output["message_type"] == "error"
    assert output.agent_output["ui_schema"] == "agent_error_v1"
    assert output.agent_output["error"] == output.error


@pytest.mark.asyncio
async def test_chat_response_compose_raises_instead_of_degraded_fallback(monkeypatch):
    from agent.router.errors import AgentRuntimeError

    async def fake_call_model(self, state, request, prompt, **kwargs):
        return None

    monkeypatch.setattr("agent.router.executors.chat_executor.ChatExecutor._call_model", fake_call_model)

    state = _state()
    state.route_plan = AgentRoutePlan(
        plan_id="plan-1",
        surface="chat",
        goal="compose",
        reason="general_chat",
        steps=[
            AgentPlanStep(
                step_id="s1",
                owner_agent="chat",
                capability="chat.response.compose",
            )
        ],
    )

    with pytest.raises(AgentRuntimeError) as exc_info:
        await ChatExecutor().execute(
            state.route_plan.steps[0],
            state,
            _request(),
        )

    assert exc_info.value.code == "CHAT_COMPOSE_MODEL_UNAVAILABLE"


def test_file_executor_supports_rag_ingest_and_inspection_exposes_only_public_entry():
    assert "rag.ingest" in FileExecutor.SUPPORTED_CAPABILITIES
    assert InspectionTaskExecutor.SUPPORTED_CAPABILITIES == {"quality.inspection.execute"}


@pytest.mark.asyncio
async def test_inspection_task_executor_returns_blocked_when_graph_needs_user_input():
    class FakeGraph:
        async def run(self, request, route_decision):
            return {
                "action_state": "awaiting_clarification",
                "summary": "缺少产品编号",
                "answer": "缺少产品编号",
            }

    executor = InspectionTaskExecutor()
    executor._graph = FakeGraph()
    step = AgentPlanStep(
        step_id="s1",
        owner_agent="inspection_task",
        capability="quality.inspection.execute",
    )

    obs, artifacts = await executor.execute(step, _state(selected_agent="inspection_task"), _request())

    assert obs.status == "blocked"
    assert artifacts[0].status == "blocked"
    assert artifacts[0].needs_user_input is True
    assert artifacts[0].summary == "缺少产品编号"


@pytest.mark.asyncio
async def test_inspection_task_executor_raises_when_graph_fails():
    from agent.router.errors import AgentRuntimeError

    class FakeGraph:
        async def run(self, request, route_decision):
            return {
                "action_state": "failed",
                "summary": "规则执行失败",
            }

    executor = InspectionTaskExecutor()
    executor._graph = FakeGraph()
    step = AgentPlanStep(
        step_id="s1",
        owner_agent="inspection_task",
        capability="quality.inspection.execute",
    )

    with pytest.raises(AgentRuntimeError) as exc_info:
        await executor.execute(step, _state(selected_agent="inspection_task"), _request())

    assert exc_info.value.code == "INSPECTION_TASK_FAILED"


@pytest.mark.asyncio
async def test_dispatcher_respects_dependencies_alias_when_depends_on_is_empty():
    execution_order: list[str] = []

    class FakeExecutor:
        async def execute(self, step, state, request, *, db_session=None):
            execution_order.append(step.step_id)
            return observation(step, status="success", summary=step.step_id), []

    dispatcher = ManagerDispatcher()
    dispatcher._executors = {"chat": FakeExecutor()}
    plan = AgentRoutePlan(
        plan_id="plan-deps",
        surface="chat",
        goal="dependency order",
        steps=[
            AgentPlanStep(step_id="s2", owner_agent="chat", capability="chat.general", input={"order": 2}, dependencies=["s1"]),
            AgentPlanStep(step_id="s1", owner_agent="chat", capability="chat.general", input={"order": 1}),
        ],
    )

    await dispatcher.dispatch(plan, _state(), _request())

    assert execution_order == ["s1", "s2"]


@pytest.mark.asyncio
async def test_evaluator_accepts_empty_quality_report_and_dedupes_artifacts():
    evaluator = ManagerEvaluator()
    state = _state()
    artifact = AgentArtifact(
        artifact_id="a-quality-empty",
        type="quality_report",
        source_agent="chat",
        status="empty",
        empty_result=True,
        metrics={"report_count": 0, "found": False},
    )
    state.artifacts.append(artifact)
    plan = AgentRoutePlan(
        plan_id="plan-report",
        surface="chat",
        goal="query report",
        steps=[AgentPlanStep(step_id="s1", owner_agent="chat", capability="quality.report.query")],
    )

    result = await evaluator.evaluate(state, plan, [], [artifact])

    assert result.satisfied is True
    assert result.next_action == "finish"


@pytest.mark.asyncio
async def test_manager_policy_chooses_file_owner_for_rag_ingest():
    state = ManagerPolicy().initialize_state(
        _request(query="把文件导入 RAG", ext={"surface": "chat"})
    )
    plan = await ManagerPolicy().plan(
        state,
        Understanding(
            goal="导入知识库",
            intent="rag_ingest",
            needs=["rag.ingest"],
            missing_inputs=[],
            entities={},
            risk="high",
        ),
    )

    assert plan.steps[0].owner_agent == "file"


def test_validate_plan_rejects_owner_capability_mismatch():
    state = _state()
    state.surface = "chat"
    state.allowed_modes = ["answer", "report"]
    plan = AgentRoutePlan(
        plan_id="plan-invalid",
        surface="chat",
        goal="invalid",
        steps=[AgentPlanStep(step_id="s1", owner_agent="file", capability="chat.general")],
    )

    result = ManagerLoop()._validate_plan(state, plan)

    assert result.allowed is False
    assert result.code == "PLAN_OWNER_CAPABILITY_MISMATCH"


def test_topology_marks_quality_judgement_as_internal_engine_and_report_under_chat():
    from agent.topology_catalog import REGISTERED_SUBGRAPHS

    by_key = {item["subgraph_key"]: item for item in REGISTERED_SUBGRAPHS}

    quality_judgement = by_key["quality_judgement"]
    assert quality_judgement["type"] == "engine"
    assert quality_judgement["route_enabled"] is False
    assert quality_judgement["supports_route_toggle"] is False

    quality_report = by_key["quality_report"]
    assert quality_report["type"] == "capability"
    assert quality_report["route_enabled"] is False
    assert quality_report["parent"] == "chat"
