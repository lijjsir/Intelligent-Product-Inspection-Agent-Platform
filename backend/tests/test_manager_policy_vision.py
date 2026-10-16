from __future__ import annotations

import pytest

from agent.router.manager_policy import ManagerPolicy
from agent.router.manager_state import ManagerState


@pytest.mark.asyncio
@pytest.mark.parametrize("query", [
    "检测前需要准备哪些图片和资料？",
    "提交产品检测前需要准备哪些材料？",
    "做质检需要准备什么？",
    "检验之前需要提供哪些图片？",
])
async def test_preparation_questions_use_general_chat_not_task_record_lookup(query):
    policy = ManagerPolicy()
    state = ManagerState(request_id="prep-request", workflow_run_id="prep-workflow", org_id="org-1",
                         surface="chat", original_query=query, normalized_query=query)
    understanding = await policy.understand(state)
    assert understanding.intent == "general_chat"
    assert "quality.task.status" not in understanding.needs
    assert policy._is_readonly_task_query(query) is False


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


@pytest.mark.asyncio
@pytest.mark.parametrize("query", [
    "这个平台能做什么？",
    "如何创建检测任务并导出报告？",
    "报告在哪里下载？",
    "你能帮我做什么？",
])
async def test_platform_instructions_are_answered_without_running_a_business_action(query):
    state = ManagerState(
        request_id="request-help", workflow_run_id="workflow-help", org_id="org-1",
        surface="chat", original_query=query, normalized_query=query,
    )
    understanding = await ManagerPolicy().understand(state)
    assert understanding.intent == "general_chat"
    assert understanding.needs == ["quality.final_analyze"]


@pytest.mark.asyncio
async def test_task_creation_request_still_requires_the_task_page():
    query = "帮我创建质检任务"
    state = ManagerState(
        request_id="request-create", workflow_run_id="workflow-create", org_id="org-1",
        surface="chat", original_query=query, normalized_query=query,
    )
    understanding = await ManagerPolicy().understand(state)
    assert understanding.intent == "action_blocked"


@pytest.mark.asyncio
@pytest.mark.parametrize('query',['什么是质量监督？','产品的质量风险如何核验？','监督抽查需要哪些依据？'])
async def test_quality_questions_retrieve_platform_evidence(query):
    state = ManagerState(request_id='r',workflow_run_id='w',org_id='org-1',surface='chat',original_query=query,normalized_query=query)
    understanding = await ManagerPolicy().understand(state)
    assert understanding.intent == 'rag_qa'
    assert 'evidence.arbitrate' in understanding.needs
