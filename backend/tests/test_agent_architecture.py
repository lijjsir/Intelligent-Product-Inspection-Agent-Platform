"""Tests for agent architecture refactoring per docs/agent_architecture_refactor.md Section 19."""
from __future__ import annotations

import pytest
from agent.router.contracts import (
    AgentPlanStep,
    AgentRouteDecision,
    AgentRouterOutput,
    Capability,
    AgentArtifact,
    AgentObservation,
    AgentRuntimeError,
    AgentDispatchError,
    AgentCapabilityError,
    AgentExecutionError,
    AgentValidationError,
)
from agent.router.capability_registry import CAPABILITIES, capability_allowed, capabilities_for_surface
from agent.router.manager_dispatcher import ManagerDispatcher


class TestCapabilityModel:
    """Verify all capabilities use the new owner_agents + handler fields."""

    def test_all_capabilities_have_owner_agents_list(self):
        for key, cap in CAPABILITIES.items():
            assert isinstance(cap.owner_agents, list), f"{key}: owner_agents must be list"
            assert len(cap.owner_agents) > 0, f"{key}: owner_agents must not be empty"
            assert all(isinstance(a, str) for a in cap.owner_agents), f"{key}: all owner_agents must be strings"

    def test_no_capability_lists_rag_vision_report_as_owner_agent(self):
        forbidden = {"rag", "vision", "quality_report", "data_analysis"}
        for key, cap in CAPABILITIES.items():
            overlap = set(cap.owner_agents) & forbidden
            assert not overlap, f"{key}: owner_agents contains forbidden values: {overlap}"

    def test_owner_agents_only_business_agents(self):
        allowed = {"chat", "file", "inspection_task"}
        for key, cap in CAPABILITIES.items():
            invalid = set(cap.owner_agents) - allowed
            assert not invalid, f"{key}: owner_agents contains non-business agents: {invalid}"

    def test_all_capabilities_have_handler(self):
        for key, cap in CAPABILITIES.items():
            assert cap.handler, f"{key}: must have handler field set"

    def test_rag_retrieve_callable_by_chat_file_inspection(self):
        cap = CAPABILITIES["rag.retrieve"]
        assert "chat" in cap.owner_agents
        assert "file" in cap.owner_agents
        assert "inspection_task" in cap.owner_agents
        assert "rag" not in cap.owner_agents

    def test_image_understanding_callable_by_chat_inspection(self):
        cap = CAPABILITIES["image.understanding"]
        assert "chat" in cap.owner_agents
        assert "inspection_task" in cap.owner_agents
        assert "vision" not in cap.owner_agents

    def test_inspection_execute_only_inspection_task(self):
        cap = CAPABILITIES["quality.inspection.execute"]
        assert cap.owner_agents == ["inspection_task"]


class TestAgentPlanStep:
    """Verify AgentPlanStep uses new field names with backward compat."""

    def test_owner_agent_field_exists(self):
        step = AgentPlanStep(
            step_id="s1",
            owner_agent="chat",
            capability="chat.general",
        )
        assert step.owner_agent == "chat"
        assert step.capability == "chat.general"

    def test_backward_compat_capability_key_removed(self):
        """capability_key field has been removed -- only capability is used."""
        step = AgentPlanStep(
            step_id="s1",
            owner_agent="chat",
            capability="test.cap",
        )
        assert step.capability == "test.cap"
        with pytest.raises(AttributeError):
            _ = step.capability_key

    def test_backward_compat_agent_field_removed(self):
        """agent field has been removed -- only owner_agent is used."""
        step = AgentPlanStep(
            step_id="s1",
            owner_agent="chat",
            capability="test.cap",
        )
        assert step.owner_agent == "chat"
        with pytest.raises(AttributeError):
            _ = step.agent

    def test_construct_with_new_fields_only(self):
        """Only new field names are accepted for construction."""
        step = AgentPlanStep(
            step_id="s1",
            owner_agent="file",
            capability="file.summary",
        )
        assert step.owner_agent == "file"
        assert step.capability == "file.summary"


class TestCapabilityRegistry:
    """Verify surface policy and capability_allowed work correctly."""

    def test_chat_surface_excludes_action_capabilities(self):
        allowed_modes = ["answer", "report"]
        assert not capability_allowed(CAPABILITIES["quality.inspection.execute"], "chat", allowed_modes)
        assert capability_allowed(CAPABILITIES["chat.general"], "chat", allowed_modes)

    def test_quality_task_allows_inspection(self):
        allowed_modes = ["action", "report", "answer"]
        assert capability_allowed(CAPABILITIES["quality.inspection.execute"], "quality_task", allowed_modes)


class TestManagerDispatcher:
    """Verify only business agents are registered."""

    def test_only_business_executors_registered(self):
        dispatcher = ManagerDispatcher()
        assert set(dispatcher._executors.keys()) == {"chat", "file", "inspection_task"}

    def test_rag_not_registered_as_executor(self):
        dispatcher = ManagerDispatcher()
        assert "rag" not in dispatcher._executors

    def test_vision_not_registered_as_executor(self):
        dispatcher = ManagerDispatcher()
        assert "vision" not in dispatcher._executors

    def test_quality_report_not_registered_as_executor(self):
        dispatcher = ManagerDispatcher()
        assert "quality_report" not in dispatcher._executors

    def test_data_analysis_not_registered_as_executor(self):
        dispatcher = ManagerDispatcher()
        assert "data_analysis" not in dispatcher._executors


class TestExceptions:
    """Verify AgentRuntimeError hierarchy."""

    def test_agent_runtime_error_fields(self):
        exc = AgentRuntimeError(
            code="TEST_ERROR",
            message="测试错误消息",
            frontend_visible=True,
            detail={"key": "value"},
        )
        assert exc.code == "TEST_ERROR"
        assert exc.message == "测试错误消息"
        assert exc.frontend_visible is True
        assert exc.detail == {"key": "value"}

    def test_dispatch_error_is_runtime_error(self):
        exc = AgentDispatchError(code="UNKNOWN_OWNER_AGENT", message="未知业务 Agent")
        assert isinstance(exc, AgentRuntimeError)
        assert exc.frontend_visible is True

    def test_capability_error_is_runtime_error(self):
        exc = AgentCapabilityError(code="UNSUPPORTED_CAPABILITY", message="不支持")
        assert isinstance(exc, AgentRuntimeError)

    def test_execution_error_is_runtime_error(self):
        exc = AgentExecutionError(code="FILE_PARSE_FAILED", message="文件解析失败")
        assert isinstance(exc, AgentRuntimeError)

    def test_validation_error_is_runtime_error(self):
        exc = AgentValidationError(code="VALIDATION_FAILED", message="验证失败")
        assert isinstance(exc, AgentRuntimeError)


class TestAgentArtifact:
    """Verify artifact has new lifecycle fields."""

    def test_artifact_has_status_field(self):
        a = AgentArtifact(artifact_id="test", type="rag_hits", source_agent="chat", status="success")
        assert a.status == "success"

    def test_artifact_has_confidence_metrics(self):
        a = AgentArtifact(
            artifact_id="test", type="rag_hits", source_agent="chat",
            status="success", confidence=0.85, metrics={"hit_count": 5}
        )
        assert a.confidence == 0.85
        assert a.metrics == {"hit_count": 5}

    def test_artifact_empty_result(self):
        """Per Section 19.4: RAG zero hits = status empty, metrics.hit_count=0."""
        a = AgentArtifact(
            artifact_id="test", type="rag_hits", source_agent="chat",
            status="empty", empty_result=True, metrics={"hit_count": 0}
        )
        assert a.empty_result is True
        assert a.status == "empty"

    def test_artifact_failed_status(self):
        """Per Section 19.6: file parse failure = status failed with error code."""
        a = AgentArtifact(
            artifact_id="test", type="file_summary", source_agent="file",
            status="failed", error={"code": "FILE_PARSE_FAILED", "message": "文件解析失败"}
        )
        assert a.status == "failed"
        assert a.error["code"] == "FILE_PARSE_FAILED"

    def test_artifact_blocked_status(self):
        a = AgentArtifact(
            artifact_id="test", type="inspection_task", source_agent="inspection_task",
            status="blocked", needs_user_input=True, summary="缺少产品型号"
        )
        assert a.status == "blocked"
        assert a.needs_user_input is True


class TestRouterOutputError:
    """Verify RouterOutput has error field for frontend display."""

    def test_output_includes_error_field(self):
        output = AgentRouterOutput(
            route_decision=AgentRouteDecision(),
            status="failed",
            error={"code": "TEST", "message": "error", "frontend_visible": True},
        )
        assert output.error is not None
        assert output.error["code"] == "TEST"

    def test_selected_agent_includes_file(self):
        """Per spec: selected_agent literal now includes 'file'."""
        decision = AgentRouteDecision(selected_agent="file")
        assert decision.selected_agent == "file"


class TestSection19Scenarios:
    """Tests matching the 10 scenarios from the architecture spec."""

    def test_19_1_general_chat_owned_by_chat(self):
        cap = CAPABILITIES["chat.general"]
        assert cap.owner_agents == ["chat"]

    def test_19_2_rag_qa_owned_by_chat(self):
        cap = CAPABILITIES["rag.retrieve"]
        assert "chat" in cap.owner_agents
        assert "rag" not in cap.owner_agents

    def test_19_3_rag_failure_error_code(self):
        exc = AgentCapabilityError(code="RAG_RETRIEVE_FAILED", message="知识库检索失败")
        assert exc.code == "RAG_RETRIEVE_FAILED"
        assert exc.frontend_visible is True

    def test_19_4_rag_zero_hits_empty_status(self):
        a = AgentArtifact(
            artifact_id="test", type="rag_hits", source_agent="chat",
            status="empty", empty_result=True, metrics={"hit_count": 0}
        )
        assert a.status == "empty"
        assert a.metrics["hit_count"] == 0

    def test_19_5_file_summary_owned_by_file(self):
        cap = CAPABILITIES["file.summary"]
        assert cap.owner_agents == ["file"]

    def test_19_6_file_parse_failure_error_code(self):
        exc = AgentExecutionError(code="FILE_PARSE_FAILED", message="文件解析失败")
        assert exc.code == "FILE_PARSE_FAILED"

    def test_19_7_image_understanding_not_vision(self):
        cap = CAPABILITIES["image.understanding"]
        assert "chat" in cap.owner_agents
        assert "vision" not in cap.owner_agents

    def test_19_8_inspection_owned_by_inspection_task(self):
        cap = CAPABILITIES["quality.inspection.execute"]
        assert cap.owner_agents == ["inspection_task"]

    def test_19_9_unknown_capability_raises(self):
        exc = AgentCapabilityError(code="UNKNOWN_CAPABILITY", message="未知能力")
        assert exc.code == "UNKNOWN_CAPABILITY"

    def test_19_10_unknown_owner_agent_raises(self):
        exc = AgentDispatchError(code="UNKNOWN_OWNER_AGENT", message="未知业务 Agent：rag")
        assert exc.code == "UNKNOWN_OWNER_AGENT"
        assert "rag" in exc.message


class TestAgentObservation:
    """Verify observation model has owner_agent field (no auto-sync of backward compat agent field)."""

    def test_observation_has_owner_agent(self):
        obs = AgentObservation(
            step_id="s1",
            capability_key="chat.general",
            owner_agent="chat",
            status="success",
        )
        assert obs.owner_agent == "chat"
        # AgentObservation agent field has been removed -- only owner_agent remains.
        with pytest.raises(AttributeError):
            _ = obs.agent
