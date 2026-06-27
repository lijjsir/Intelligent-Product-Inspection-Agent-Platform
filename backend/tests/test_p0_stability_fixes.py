from __future__ import annotations

"""Tests for P0 stability fixes per 6-agent-langgraph guide Sections 4.3-4.4.

Covers:
- No silent fallback (Evidence executor raises structured error)
- Orchestrator returns agent_error_v1 instead of throwing 500
- make_agent_error enhanced parameters
- MemoryGovernance surface restriction
"""

import pytest

from agent.contracts.quality_contracts import NormalizedRequest, RouteDecision, RouteSignals
from agent.router.contracts import AgentPlanStep
from agent.router.errors import (
    AgentErrorCategory,
    AgentErrorStatus,
    AgentRuntimeError,
    make_agent_error,
)
from agent.router.manager_state import ManagerState


def _request(**overrides) -> NormalizedRequest:
    payload = {
        "request_id": "req-st-1",
        "workflow_run_id": "wf-st-1",
        "org_id": "org-1",
        "user_id": "user-1",
        "session_id": "session-1",
        "query": "test",
        "ext": {"surface": "chat"},
    }
    payload.update(overrides)
    return NormalizedRequest(**payload)


def _state(**overrides) -> ManagerState:
    payload = {
        "request_id": "req-st-1",
        "workflow_run_id": "wf-st-1",
        "original_query": "test",
        "org_id": "org-1",
        "user_id": "user-1",
        "session_id": "session-1",
    }
    payload.update(overrides)
    return ManagerState(**payload)


def _step(**overrides) -> AgentPlanStep:
    payload = {
        "step_id": "step-st-1",
        "owner_agent": "orchestrator",
        "capability": "evidence.arbitrate",
    }
    payload.update(overrides)
    return AgentPlanStep(**payload)


# ---------------------------------------------------------------------------
# P0.2: Enhanced make_agent_error
# ---------------------------------------------------------------------------

def test_make_agent_error_supports_explicit_status():
    error = make_agent_error("EVIDENCE_ARBITRATION_FAILED", status=AgentErrorStatus.BLOCKED)
    assert error.status == "blocked"


def test_make_agent_error_supports_explicit_retryable():
    error = make_agent_error("INTERNAL_AGENT_ERROR", retryable=False)
    assert error.retryable is False


def test_make_agent_error_supports_explicit_frontend_visible():
    error = make_agent_error("INTERNAL_AGENT_ERROR", frontend_visible=False)
    assert error.frontend_visible is False


def test_make_agent_error_supports_explicit_severity():
    error = make_agent_error("EVIDENCE_ARBITRATION_FAILED", severity="critical")
    assert error.severity == "critical"


def test_make_agent_error_supports_explicit_user_action():
    error = make_agent_error("EVIDENCE_ARBITRATION_FAILED", user_action="请重试。")
    assert error.user_action == "请重试。"


def test_make_agent_error_unknown_code_defaults_to_internal():
    error = make_agent_error("NONEXISTENT_CODE")
    assert error.category == AgentErrorCategory.INTERNAL.value
    assert isinstance(error, AgentRuntimeError)


def test_make_agent_error_to_dict_includes_stage():
    error = make_agent_error("EVIDENCE_ARBITRATION_FAILED", source="evidence.capability")
    payload = error.to_dict(stage="retrieve_rag_context", agent_name="orchestrator")

    assert payload["code"] == "EVIDENCE_ARBITRATION_FAILED"
    assert payload["frontend_visible"] is True
    assert payload["retryable"] is True
    assert payload["agent_name"] == "orchestrator"
    assert payload["stage"] == "retrieve_rag_context"


def test_make_agent_error_debug_hidden_by_default():
    error = make_agent_error("INTERNAL_AGENT_ERROR", debug={"raw_error": "secret"})
    payload = error.to_dict()

    assert "debug" not in payload


def test_make_agent_error_debug_included_when_requested():
    error = make_agent_error("INTERNAL_AGENT_ERROR", debug={"raw_error": "secret"})
    payload = error.to_dict(include_debug=True)

    assert "debug" in payload
    assert payload["debug"]["raw_error"] == "secret"


# ---------------------------------------------------------------------------
# P0.3: No silent fallback — Evidence executor
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_evidence_executor_raises_structured_error_when_service_fails(monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("service broken")

    from app.services.evidence_arbitration_service import EvidenceArbitrationService

    monkeypatch.setattr(EvidenceArbitrationService, "arbitrate", boom)

    from agent.router.executors.evidence_arbitration_executor import EvidenceArbitrationExecutor

    executor = EvidenceArbitrationExecutor()
    with pytest.raises(AgentRuntimeError) as exc_info:
        await executor.execute(
            _step(owner_agent="orchestrator", capability="evidence.arbitrate"),
            _state(selected_agent="quality_analysis"),
            _request(),
        )

    assert exc_info.value.code == "EVIDENCE_ARBITRATION_FAILED"
    assert "service broken" in str(exc_info.value.message)


# ---------------------------------------------------------------------------
# P0.4: Orchestrator _build_agent_error_output
# ---------------------------------------------------------------------------

def test_build_agent_error_output_returns_agent_error_v1():
    from app.services.quality_agent_orchestrator_service import QualityAgentOrchestratorService

    request = _request()
    exc = RuntimeError("manager broken")

    output = QualityAgentOrchestratorService._build_agent_error_output(request, exc)

    assert output.message_type == "error"
    assert output.ui_schema == "agent_error_v1"
    assert output.error is not None
    assert output.error["code"] == "INTERNAL_AGENT_ERROR"
    assert output.error["frontend_visible"] is True
    assert output.route_decision.selected_agent == "quality_analysis"
    assert output.route_decision.sub_route == "error"


def test_build_agent_error_output_preserves_existing_agent_runtime_error():
    from app.services.quality_agent_orchestrator_service import QualityAgentOrchestratorService

    request = _request()
    exc = make_agent_error(
        "EVIDENCE_ARBITRATION_FAILED",
        message="证据仲裁失败。",
        source="evidence.capability",
    )

    output = QualityAgentOrchestratorService._build_agent_error_output(request, exc)

    assert output.error["code"] == "EVIDENCE_ARBITRATION_FAILED"
    assert output.error["message"] == "证据仲裁失败。"


# ---------------------------------------------------------------------------
# P1.3: MemoryGovernance surface restriction
# ---------------------------------------------------------------------------

def test_memory_governance_not_on_chat_or_quality_task_surfaces():
    from agent.router.capability_registry import CAPABILITIES, capability_allowed

    cap = CAPABILITIES["memory.governance"]
    assert cap.surfaces == ["admin", "batch"]
    assert "chat" not in cap.surfaces
    assert "quality_task" not in cap.surfaces

    # Verify it's not allowed on chat surface
    assert not capability_allowed(cap, "chat", ["answer", "report"])
    assert not capability_allowed(cap, "quality_task", ["action", "report", "answer"])

    # But allowed on admin and batch
    assert capability_allowed(cap, "admin", ["action", "report"])
    assert capability_allowed(cap, "batch", ["action", "report"])


def test_memory_governance_is_action_mode():
    from agent.router.capability_registry import CAPABILITIES

    cap = CAPABILITIES["memory.governance"]
    assert cap.mode == "action"
