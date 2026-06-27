from __future__ import annotations

import pytest

from agent.router.errors import AgentRuntimeError
from agent.subgraphs.quality_analysis.nodes import (
    build_report,
    build_final_assessment,
    finalize_response,
    llm_quality_reasoning,
    maybe_persist_task_result,
    standard_gate,
    validate_required_inputs,
)
from app.services.quality_result_materialization_service import QualityResultMaterializationService


@pytest.mark.asyncio
async def test_quality_task_prompt_includes_real_context_and_blocks_fabrication(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_run_llm_chat(**kwargs):
        captured.update(kwargs)
        return "manual review required", {"model": "quality-model"}

    monkeypatch.setattr("agent.subgraphs.common.llm_runtime.run_llm_chat", fake_run_llm_chat)

    result = await llm_quality_reasoning(
        {
            "response_mode": "inspection_execute",
            "query": "execute quality inspection task_id=task-1 product_id=screw spec_code=SCREW-A-2026-V1",
            "visual_inspection_result": {
                "model_id": "vision-model",
                "summary": "image contains three rotten apples",
                "possible_defects": ["large rotten area on the right apple"],
            },
            "evidence_packet": {"source_count": 1, "sources": {"rag": {"items": [{"hits": []}]}}},
            "request": {
                "ext": {
                    "task_id": "task-1",
                    "product_id": "screw",
                    "spec_code": "SCREW-A-2026-V1",
                }
            },
        }
    )

    prompt = captured["messages"][0]["content"]
    assert "全程只用中文输出" in prompt
    assert "不得编造测量值" in prompt
    assert "图片、产品、标准之间不一致" in prompt
    assert "# 正式质检报告" in prompt
    assert "three rotten apples" in prompt
    assert '"product_id": "screw"' in prompt
    assert result["llm_answer"] == "manual review required"


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
            "visual_inspection_result": {
                "summary": "image contains one corrosion defect",
                "model_id": "vision-model",
                "defects": [
                    {
                        "type": "corrosion",
                        "confidence": 0.91,
                        "bbox": [0.12, 0.2, 0.3, 0.24],
                        "description": "surface corrosion",
                        "image_index": 0,
                    }
                ],
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
    assert persistable.result.llm_model == "vision-model"
    assert persistable.result.reasoning_chain is not None
    assert persistable.result.reasoning_chain["defects"] == [
        {
            "type": "corrosion",
            "confidence": 0.91,
            "bbox": [0.12, 0.2, 0.3, 0.24],
            "description": "surface corrosion",
            "image_index": 0,
        }
    ]
    assert persistable.quality_trace is not None
    assert persistable.quality_trace.workflow_version == "quality_analysis_graph_v1"
    assert persistable.quality_trace.prompt_version == "quality_analysis_prompt_v1"
    assert persistable.token_usage[0].model_key == "quality-model"
    assert persistable.token_usage[0].prompt_tokens == 11
    assert persistable.token_usage[0].completion_tokens == 7
    assert persistable.token_usage[0].total_tokens == 18
    assert persistable.token_usage[0].trace_id == "trace-1"


@pytest.mark.asyncio
async def test_quality_task_prompt_redacts_data_url_image_context(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_run_llm_chat(**kwargs):
        captured.update(kwargs)
        return "ok", {"model": "quality-model"}

    monkeypatch.setattr("agent.subgraphs.common.llm_runtime.run_llm_chat", fake_run_llm_chat)

    data_url = "data:image/jpeg;base64," + ("aGVsbG8=" * 2000)
    await llm_quality_reasoning(
        {
            "response_mode": "inspection_execute",
            "query": "inspect hazelnut",
            "visual_inspection_result": {"summary": "hazelnut looks normal", "defects": [], "confidence": 0.93},
            "evidence_packet": {"source_count": 1},
            "request": {"ext": {"image_urls": [data_url], "product_id": "hazelnut", "spec_code": "AUTO-HAZELNUT-V1"}},
        }
    )

    prompt = captured["messages"][0]["content"]
    assert "aGVsbG8=" not in prompt
    assert '"redacted": true' in prompt
    assert '"image_count": 1' in prompt


@pytest.mark.asyncio
async def test_quality_task_image_requires_visual_result():
    result = await validate_required_inputs(
        {
            "capability": "quality.inspection.execute",
            "evidence_packet": {"source_count": 1},
            "request": {"ext": {"image_urls": ["data:image/jpeg;base64,aGVsbG8="]}},
        }
    )

    assert result["needs_user_input"] is True
    assert result["status"] == "blocked"
    assert "visual inspection" in result["summary"]


@pytest.mark.asyncio
async def test_quality_task_good_visual_result_can_pass_without_manual_review():
    state = {
        "response_mode": "inspection_execute",
        "request": {
            "ext": {
                "image_urls": ["data:image/jpeg;base64,aGVsbG8="],
                "product_id": "hazelnut",
                "spec_code": "AUTO-HAZELNUT-V1",
            }
        },
        "visual_inspection_result": {
            "summary": "hazelnut kernel is intact and clean",
            "defects": [],
            "confidence": 0.94,
            "risk": "low",
            "model_id": "doubao-vision-pro",
        },
        "evidence_packet": {"source_count": 1},
        "consumed_artifact_ids": ["vision-1", "evidence-1"],
    }

    gate = await standard_gate(state)
    state.update(gate)
    final = await build_final_assessment(state)

    assessment = final["final_assessment"]
    assert assessment["final_verdict"] == "pass"
    assert assessment["risk_level"] == "low"
    assert assessment["risk_score"] < 0.2


@pytest.mark.asyncio
async def test_quality_report_and_summary_use_chinese_text_without_mojibake():
    report_result = await build_report(
        {
            "response_mode": "inspection_execute",
            "llm_answer": "## 检测结论\n未见明确异常。",
        }
    )
    report = report_result["report"]

    assert report.startswith("# 正式质检报告")
    assert "## 检测结论" in report
    assert "姝" not in report
    assert "璐" not in report
    assert "Quality Inspection Report" not in report

    final = await finalize_response(
        {
            "response_mode": "inspection_execute",
            "answer": report,
            "final_assessment": {"confidence": 0.91},
        }
    )

    assert final["summary"] == "质量分析完成"
