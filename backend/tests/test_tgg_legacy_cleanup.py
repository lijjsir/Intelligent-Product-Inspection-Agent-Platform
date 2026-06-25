from pathlib import Path

import pytest
from pydantic import ValidationError

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import AgentPlanStep
from agent.router.manager_state import ManagerState
from app.services.evidence_arbitration_service import EvidenceArbitrationService
from app.services.memory_capability_service import MemoryCapabilityService


BACKEND_ROOT = Path(__file__).parents[1]


def test_only_three_business_langgraphs_remain():
    graph_sources = sorted(
        path.relative_to(BACKEND_ROOT).as_posix()
        for path in (BACKEND_ROOT / "agent/subgraphs").glob("*/graph.py")
    )

    assert graph_sources == [
        "agent/subgraphs/lab_detection/graph.py",
        "agent/subgraphs/quality_analysis/graph.py",
        "agent/subgraphs/vision_inspection/graph.py",
    ]


def test_legacy_graph_and_executor_sources_are_removed():
    removed_paths = [
        "agent/subgraphs/inspection_task",
        "agent/subgraphs/evidence_arbitration",
        "agent/subgraphs/memory_governance",
        "agent/subgraphs/quality_chat",
        "agent/subgraphs/quality_judgement",
        "agent/subgraphs/legacy_quality",
        "agent/subgraphs/llm_native_quality",
        "agent/graphs/memory_manager",
        "agent/graphs/quality_root",
    ]
    for relative in removed_paths:
        assert not any((BACKEND_ROOT / relative).rglob("*.py"))
    assert not (
        BACKEND_ROOT / "agent/router/executors/inspection_task_executor.py"
    ).exists()


@pytest.mark.parametrize("owner", ["evidence", "memory_governance", "inspection_task"])
def test_capabilities_cannot_be_planned_as_legacy_agents(owner):
    with pytest.raises(ValidationError):
        AgentPlanStep(
            step_id="step-invalid",
            owner_agent=owner,
            capability="evidence.arbitrate",
        )


def _quality_task_state(**overrides) -> ManagerState:
    payload = {
        "request_id": "request-1",
        "workflow_run_id": "workflow-1",
        "org_id": "org-1",
        "user_id": "user-1",
        "original_query": "检查螺丝外观",
        "surface": "quality_task",
    }
    payload.update(overrides)
    return ManagerState(**payload)


def _quality_task_request(**overrides) -> NormalizedRequest:
    payload = {
        "request_kind": "task",
        "request_id": "request-1",
        "workflow_run_id": "workflow-1",
        "org_id": "org-1",
        "user_id": "user-1",
        "query": "检查螺丝外观",
        "product_id": "screw",
        "spec_code": "GB/T-SCREW",
        "metadata": {"product_family": "fastener"},
        "ext": {"surface": "quality_task"},
    }
    payload.update(overrides)
    return NormalizedRequest(**payload)


@pytest.mark.asyncio
async def test_quality_task_evidence_uses_system_rag_without_manual_space(monkeypatch):
    captured = {}

    async def fake_search(**kwargs):
        captured.update(kwargs)
        return {
            "hits": [
                {
                    "id": "chunk-1",
                    "text": "螺丝表面不得有裂纹。",
                    "score": 0.93,
                }
            ],
            "hit_count": 1,
            "rag_space_id": "system-space",
            "rag_space_name": "系统标准库",
            "system_rag_space_ids": ["system-space"],
        }

    monkeypatch.setattr(
        "app.services.system_rag_service.resolve_and_search_system_rag",
        fake_search,
    )

    hits = await EvidenceArbitrationService()._retrieve_rag(
        step=AgentPlanStep(
            step_id="evidence-1",
            owner_agent="orchestrator",
            capability="evidence.arbitrate",
        ),
        state=_quality_task_state(),
        request=_quality_task_request(),
        db_session=object(),
    )

    assert captured["product_id"] == "screw"
    assert captured["spec_code"] == "GB/T-SCREW"
    assert hits[0]["hit_count"] == 1
    assert hits[0]["rag_space_id"] == "system-space"


@pytest.mark.asyncio
async def test_quality_task_evidence_skip_is_explicit(monkeypatch):
    async def fail_if_called(**_kwargs):
        raise AssertionError("RAG must not be called when explicitly skipped")

    monkeypatch.setattr(
        "app.services.system_rag_service.resolve_and_search_system_rag",
        fail_if_called,
    )

    hits = await EvidenceArbitrationService()._retrieve_rag(
        step=AgentPlanStep(
            step_id="evidence-1",
            owner_agent="orchestrator",
            capability="evidence.arbitrate",
        ),
        state=_quality_task_state(
            request_ext={"manager_skip_rag_evidence": True}
        ),
        request=_quality_task_request(),
        db_session=object(),
    )

    assert hits == []


@pytest.mark.asyncio
async def test_memory_capability_is_service_workflow_not_graph():
    result = await MemoryCapabilityService(object(), "org-1").govern(
        task_context={"query": "", "user_id": "user-1", "trace_id": "trace-1"},
        structured_memory=[],
        memory_events=[],
    )

    assert result["status"] == "completed"
    assert result["memory_sources_used"] == 0
    assert result["contamination_nodes"] == 0
    assert result["alerts"] == []
