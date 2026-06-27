from __future__ import annotations

import pytest

from agent.router.manager_policy import ManagerPolicy
from agent.router.manager_state import ManagerState


@pytest.mark.asyncio
async def test_chat_image_understanding_runs_vision_then_quality_analysis():
    state = ManagerState(
        request_id="request-1",
        workflow_run_id="workflow-1",
        original_query="请查看附件并说明你能识别到的信息",
        org_id="org-1",
        surface="chat",
        attachments=[
            {
                "id": "image-1",
                "name": "apple.jpg",
                "url": "/api/v1/files/apple.jpg",
                "kind": "image",
                "content_type": "image/jpeg",
            }
        ],
    )

    understanding = await ManagerPolicy().understand(state)

    assert understanding.intent == "vision_inspection"
    assert understanding.needs == ["vision.inspect", "quality.final_analyze"]


@pytest.mark.asyncio
async def test_readonly_quality_task_count_query_routes_to_task_status():
    state = ManagerState(
        request_id="request-1",
        workflow_run_id="workflow-1",
        original_query="你能检测到有几条质检任务被创建吗？",
        normalized_query="你能检测到有几条质检任务被创建吗？",
        org_id="org-1",
        surface="chat",
    )

    understanding = await ManagerPolicy().understand(state)

    assert understanding.intent == "quality_task_status"
    assert understanding.needs == ["quality.task.status"]


@pytest.mark.asyncio
async def test_recent_quality_situation_routes_to_db_backed_task_status():
    state = ManagerState(
        request_id="request-1",
        workflow_run_id="workflow-1",
        original_query="最近的质检情况",
        normalized_query="最近的质检情况",
        org_id="org-1",
        surface="chat",
    )

    policy = ManagerPolicy()
    understanding = await policy.understand(state)
    plan = await policy.plan(state, understanding)

    assert understanding.intent == "quality_task_status"
    assert understanding.needs == ["quality.task.status"]
    assert plan.reason == "quality_task_status"
    assert [step.capability for step in plan.steps] == ["quality.task.status"]


@pytest.mark.asyncio
async def test_quality_result_query_routes_to_task_status():
    state = ManagerState(
        request_id="request-1",
        workflow_run_id="workflow-1",
        original_query="检测结果",
        normalized_query="检测结果",
        org_id="org-1",
        surface="chat",
    )

    understanding = await ManagerPolicy().understand(state)

    assert understanding.intent == "quality_task_status"
    assert understanding.needs == ["quality.task.status"]
