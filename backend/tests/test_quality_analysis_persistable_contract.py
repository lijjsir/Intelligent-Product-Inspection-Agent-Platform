from __future__ import annotations

import pytest

from agent.router.errors import AgentRuntimeError
from agent.subgraphs.quality_analysis.nodes import maybe_persist_task_result
from app.services.quality_result_materialization_service import QualityResultMaterializationService


@pytest.mark.asyncio
async def test_quality_task_persistable_build_failure_is_structured_error(monkeypatch):
    class BrokenMaterializationService:
        def __init__(self, _db_session):
            pass

        async def build_persistable_output(self, **_kwargs):
            raise RuntimeError("database unavailable")

    monkeypatch.setattr(
        "app.services.quality_result_materialization_service.QualityResultMaterializationService",
        BrokenMaterializationService,
    )

    with pytest.raises(AgentRuntimeError) as exc_info:
        await maybe_persist_task_result(
            {
                "surface": "quality_task",
                "db_session": object(),
                "org_id": "org-1",
                "workflow_run_id": "wf-persist-1",
                "final_assessment": {"final_verdict": "manual_required"},
                "standard_evaluation": {"passed": True},
            }
        )

    assert exc_info.value.code == "INSPECTION_TASK_FAILED"
    assert exc_info.value.detail["stage"] == "maybe_persist_task_result"
    assert exc_info.value.debug["raw_error"] == "database unavailable"


@pytest.mark.asyncio
async def test_quality_task_missing_db_session_is_structured_error():
    with pytest.raises(AgentRuntimeError) as exc_info:
        await maybe_persist_task_result(
            {
                "surface": "quality_task",
                "db_session": None,
                "workflow_run_id": "wf-persist-2",
                "final_assessment": {"final_verdict": "manual_required"},
            }
        )

    assert exc_info.value.code == "INSPECTION_TASK_FAILED"
    assert "db_session" in exc_info.value.detail["missing"]


@pytest.mark.asyncio
async def test_materialization_builds_task_and_token_usage_from_graph_state():
    persistable = await QualityResultMaterializationService(object()).build_persistable_output(
        org_id="org-1",
        workflow_run_id="wf-persist-3",
        final_state={
            "ext": {
                "task_id": "task-1",
                "product_id": "P-1",
                "spec_code": "STD-1",
                "image_urls": ["img-a", "img-b"],
            },
            "final_assessment": {
                "final_verdict": "manual_required",
                "overall_score": 0.72,
                "risk_level": "medium",
                "risk_score": 0.28,
                "confidence": 0.72,
            },
            "llm_meta": {
                "model": "quality-model",
                "trace_id": "trace-1",
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 7,
                    "total_tokens": 18,
                },
            },
        },
        standard_evaluation={"passed": True},
    )

    assert persistable.task is not None
    assert persistable.task.id == "task-1"
    assert persistable.task.product_id == "P-1"
    assert persistable.task.spec_code == "STD-1"
    assert persistable.task.image_count == 2
    assert persistable.result is not None
    assert persistable.result.task_id == "task-1"
    assert persistable.result.llm_model == "quality-model"
    assert persistable.token_usage[0].model_key == "quality-model"
    assert persistable.token_usage[0].prompt_tokens == 11
    assert persistable.token_usage[0].completion_tokens == 7
    assert persistable.token_usage[0].total_tokens == 18
    assert persistable.token_usage[0].trace_id == "trace-1"
