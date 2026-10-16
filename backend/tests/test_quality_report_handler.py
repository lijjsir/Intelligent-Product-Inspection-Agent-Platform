from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent.router.capabilities.quality_report_handler import QualityReportHandler
from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import AgentPlanStep, CapabilityContext
from agent.router.manager_state import ManagerState


def test_task_collection_content_includes_real_task_and_result_facts():
    tasks = [
        SimpleNamespace(
            id="task-hazelnut",
            product_id="hazelnut",
            spec_code="STD-HAZELNUT",
            status="done",
            priority=5,
            created_at="2026-06-27 00:46:38",
            updated_at="2026-06-27 00:47:20",
        ),
        SimpleNamespace(
            id="task-screw",
            product_id="screw",
            spec_code="STD-SCREW",
            status="done",
            priority=5,
            created_at="2026-06-03 13:11:37",
            updated_at="2026-06-03 13:12:06",
        ),
    ]
    results = {
        "task-hazelnut": SimpleNamespace(
            id="result-hazelnut",
            task_id="task-hazelnut",
            verdict="通过",
            overall_score=0.95,
            created_at="2026/6/26 16:47:20",
        ),
        "task-screw": SimpleNamespace(
            id="result-screw",
            task_id="task-screw",
            verdict="不通过",
            overall_score=1.0,
            created_at="2026/6/3 05:12:06",
        ),
    }

    content = QualityReportHandler._task_collection_content(tasks, total=2, results_by_task_id=results)

    assert content["found"] is True
    assert content["total"] == 2
    assert "共找到 2 条质检任务" in content["summary"]
    assert "hazelnut" in content["summary"]
    assert "screw" in content["summary"]
    assert "通过" in content["summary"]
    assert "不通过" in content["summary"]
    assert "95.0" in content["summary"]
    assert "100.0" in content["summary"]


def test_task_answer_uses_the_same_review_verdict_as_the_result_page():
    task = SimpleNamespace(id="task-1", product_id="sample", spec_code="test", status="done", priority=5)
    result = SimpleNamespace(
        id="result-1", verdict="pass", overall_score=0.9, prompt_version="quality_analysis_v1",
        reviewed_by=None, citations=[], reasoning_chain={},
    )
    content = QualityReportHandler._task_content(task, result)
    assert content["verdict"] == "manual_required"
    assert content["score_status"] == "not_calibrated"
    assert "需人工复核" in content["summary"]


@pytest.mark.asyncio
async def test_explicit_task_query_enforces_owner_and_does_not_substitute_another_task(monkeypatch):
    lookup = AsyncMock(return_value=None)
    fallback = AsyncMock()
    monkeypatch.setattr("app.repositories.task_repo.TaskRepository.get_for_user", lookup)
    monkeypatch.setattr("app.repositories.task_repo.TaskRepository.list_paged", fallback)
    state = ManagerState(request_id="req-1", workflow_run_id="wf-1", org_id="org-1", surface="chat", original_query="查询任务状态")
    request = NormalizedRequest(
        request_id="req-1", org_id="org-1", user_id="user-1",
        metadata={"user_role": "user", "task_id": "foreign-task"},
    )
    context = CapabilityContext(
        step=AgentPlanStep(step_id="s1", capability="quality.task.status"),
        state=state, request=request, db_session=object(),
    )
    _observation, artifacts = await QualityReportHandler().run(context)
    lookup.assert_awaited_once_with("org-1", "foreign-task", owner_user_id="user-1")
    fallback.assert_not_awaited()
    assert artifacts[0].content["found"] is False
