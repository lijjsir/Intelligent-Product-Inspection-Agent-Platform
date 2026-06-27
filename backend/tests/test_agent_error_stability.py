from __future__ import annotations

import pytest

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import AgentArtifact, AgentPlanStep, AgentRoutePlan
from agent.router.executors.base import observation
from agent.router.executors.file_executor import FileExecutor
from agent.router.executors.quality_analysis_executor import QualityAnalysisExecutor
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


def test_error_payload_exposes_frontend_stage_agent_and_request_id():
    from agent.router.errors import make_agent_error

    state = _state(trace_id="trace-1", request_id="req-visible-1", selected_agent="orchestrator")
    error = make_agent_error(
        "RAG_RETRIEVE_FAILED",
        detail={"rag_space_id": "rag-1"},
        source="evidence.arbitrate",
    )

    payload = error.to_dict(state=state, stage="evidence_arbitration", agent_name="orchestrator")

    assert payload["request_id"] == "req-visible-1"
    assert payload["stage"] == "evidence_arbitration"
    assert payload["agent_name"] == "orchestrator"


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
async def test_quality_final_analyze_raises_instead_of_degraded_fallback(monkeypatch):
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
                AgentPlanStep(step_id="s1", owner_agent="quality_analysis", capability="quality.final_analyze")
            ],
        )

    with pytest.raises(AgentRuntimeError) as exc_info:
        await QualityAnalysisExecutor().execute(
            state.route_plan.steps[0],
            state,
            _request(),
        )

    assert exc_info.value.code == "CHAT_COMPOSE_MODEL_UNAVAILABLE"


def test_file_executor_supports_rag_ingest_and_inspection_exposes_only_public_entry():
    assert "rag.ingest" in FileExecutor.SUPPORTED_CAPABILITIES
    from agent.router.executors.quality_analysis_executor import QualityAnalysisExecutor

    assert QualityAnalysisExecutor.SUPPORTED_CAPABILITIES == {
        "quality.final_analyze",
        "quality.inspection.execute",
        "quality.report.query",
        "quality.task.status",
    }


@pytest.mark.asyncio
async def test_quality_analysis_executor_delegates_readonly_task_status_query():
    from agent.router.executors.quality_analysis_executor import QualityAnalysisExecutor

    step = AgentPlanStep(
        step_id="s1",
        owner_agent="quality_analysis",
        capability="quality.task.status",
    )

    obs, artifacts = await QualityAnalysisExecutor().execute(
        step,
        _state(selected_agent="quality_analysis"),
        _request(query="最近的质检情况"),
        db_session=None,
    )

    assert obs.status == "skipped"
    assert artifacts[0].type == "task_status"
    assert artifacts[0].empty_result is True


@pytest.mark.asyncio
async def test_quality_analysis_executor_returns_blocked_when_graph_needs_user_input():
    """P1.2: QualityAnalysisGraph is now the entry for quality.inspection.execute."""
    class FakeGraph:
        async def run(self, state):
            return {
                "status": "blocked",
                "summary": "需要用户补充信息",
                "answer": "需要用户补充信息",
                "final_assessment": {},
            }

    executor = QualityAnalysisExecutor()
    step = AgentPlanStep(
        step_id="s1",
        owner_agent="quality_analysis",
        capability="quality.inspection.execute",
    )
    import agent.subgraphs.quality_analysis as qa_module

    original = qa_module.QualityAnalysisGraph
    qa_module.QualityAnalysisGraph = lambda: FakeGraph()
    try:
        obs, artifacts = await executor.execute(step, _state(selected_agent="quality_analysis"), _request())
    finally:
        qa_module.QualityAnalysisGraph = original

    assert obs.status == "blocked"
    assert artifacts[0].status == "blocked"
    assert artifacts[0].needs_user_input is True


@pytest.mark.asyncio
async def test_quality_analysis_executor_raises_when_graph_fails():
    """P1.2: Graph errors must propagate as structured AgentRuntimeError."""
    from agent.router.errors import AgentRuntimeError

    class FakeGraph:
        async def run(self, state):
            raise RuntimeError("inspection graph broken")

    executor = QualityAnalysisExecutor()
    step = AgentPlanStep(
        step_id="s1",
        owner_agent="quality_analysis",
        capability="quality.inspection.execute",
    )
    import agent.subgraphs.quality_analysis as qa_module

    original = qa_module.QualityAnalysisGraph
    qa_module.QualityAnalysisGraph = lambda: FakeGraph()

    try:
        with pytest.raises(AgentRuntimeError) as exc_info:
            await executor.execute(step, _state(selected_agent="quality_analysis"), _request())
    finally:
        qa_module.QualityAnalysisGraph = original

    assert exc_info.value.code == "INSPECTION_TASK_FAILED"


@pytest.mark.asyncio
async def test_dispatcher_respects_dependencies_alias_when_depends_on_is_empty():
    execution_order: list[str] = []

    class FakeExecutor:
        async def execute(self, step, state, request, *, db_session=None):
            execution_order.append(step.step_id)
            return observation(step, status="success", summary=step.step_id), []

    dispatcher = ManagerDispatcher()
    dispatcher._executors = {"quality_analysis": FakeExecutor()}
    plan = AgentRoutePlan(
        plan_id="plan-deps",
        surface="chat",
        goal="dependency order",
        steps=[
            AgentPlanStep(step_id="s2", owner_agent="quality_analysis", capability="quality.final_analyze", input={"order": 2}, dependencies=["s1"]),
            AgentPlanStep(step_id="s1", owner_agent="quality_analysis", capability="quality.final_analyze", input={"order": 1}),
        ],
    )

    await dispatcher.dispatch(plan, _state(), _request())

    assert execution_order == ["s1", "s2"]


@pytest.mark.asyncio
async def test_evaluator_accepts_empty_evidence_packet_and_dedupes_artifacts():
    evaluator = ManagerEvaluator()
    state = _state()
    artifact = AgentArtifact(
        artifact_id="a-quality-empty",
        type="evidence_packet",
        source_agent="orchestrator",
        status="empty",
        empty_result=True,
        metrics={"source_count": 0},
    )
    state.artifacts.append(artifact)
    plan = AgentRoutePlan(
        plan_id="plan-report",
        surface="chat",
        goal="query evidence",
        steps=[AgentPlanStep(step_id="s1", owner_agent="orchestrator", capability="evidence.arbitrate")],
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
        steps=[AgentPlanStep(step_id="s1", owner_agent="file", capability="quality.final_analyze")],
    )

    result = ManagerLoop()._validate_plan(state, plan)

    assert result.allowed is False
    assert result.code == "PLAN_OWNER_CAPABILITY_MISMATCH"


def test_topology_exposes_only_business_agents_and_service_capabilities():
    from agent.topology_catalog import REGISTERED_SUBGRAPHS

    by_key = {item["subgraph_key"]: item for item in REGISTERED_SUBGRAPHS}

    assert "quality_judgement" not in by_key
    assert "inspection_task" not in by_key
    assert by_key["evidence_arbitration"]["type"] == "capability"
    assert by_key["evidence_arbitration"]["route_enabled"] is False
    assert by_key["memory_governance"]["type"] == "capability"
    assert by_key["memory_governance"]["route_enabled"] is False
    assert by_key["vision_inspection"]["route_enabled"] is True
    assert by_key["lab_detection"]["route_enabled"] is True
    assert by_key["quality_analysis"]["route_enabled"] is True
