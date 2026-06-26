from __future__ import annotations

import pytest

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import AgentPlanStep, AgentRoutePlan
from agent.router.executors.base import artifact, observation
from agent.router.executors.vision_inspection_executor import VisionInspectionExecutor
from agent.router.manager_state import ManagerState
from agent.router.capabilities.vision_handler import VisionUnderstandingHandler
from agent.router.manager_loop import ManagerLoop


@pytest.mark.asyncio
async def test_chat_image_request_keeps_callback_out_of_state_and_injects_db_session(
    monkeypatch,
):
    async def emit(_event):
        return None

    db_session = object()
    captured = {}

    async def fake_run(_self, context):
        captured["db_session"] = context.db_session
        image_artifact = artifact(
            context.step,
            "image_understanding",
            content={
                "summary": "识别到一个苹果",
                "answer": "识别到一个苹果",
                "image_count": 1,
                "objects": ["apple"],
            },
        )
        return (
            observation(
                context.step,
                status="success",
                summary="识别到一个苹果",
                artifact_ids=[image_artifact.artifact_id],
            ),
            [image_artifact],
        )

    monkeypatch.setattr(
        "agent.router.capabilities.vision_handler.VisionUnderstandingHandler.run",
        fake_run,
    )

    attachment = {
        "id": "image-1",
        "name": "apple_good.jpg",
        "url": "/v1/chat/files/chat/image-1.jpg",
        "content_type": "image/jpeg",
        "kind": "image",
    }
    request = NormalizedRequest(
        request_id="request-1",
        workflow_run_id="workflow-1",
        session_id="session-1",
        org_id="org-1",
        user_id="user-1",
        query="请查看附件并说明能识别到的信息",
        ext={"emit": emit},
        attachments=[attachment],
        image_urls=[attachment["url"]],
    )
    state = ManagerState(
        request_id="request-1",
        workflow_run_id="workflow-1",
        session_id="session-1",
        original_query=request.query,
        org_id="org-1",
        user_id="user-1",
        attachments=[attachment],
        request_ext={"emit": emit},
    )
    step = AgentPlanStep(
        step_id="vision-step-1",
        owner_agent="vision",
        capability="vision.inspect",
        operation="inspect",
    )

    result, artifacts = await VisionInspectionExecutor().execute(
        step,
        state,
        request,
        db_session=db_session,
    )

    assert captured["db_session"] is db_session
    assert result.status == "success"
    assert result.summary == "识别到一个苹果"
    assert artifacts[0].content["answer"] == "识别到一个苹果"
    assert artifacts[0].content["image_count"] == 1


def test_parse_vision_response_accepts_preparsed_model_payload():
    parsed = VisionUnderstandingHandler._parse_vision_response(
        {
            "summary": "图片中有一个红色苹果",
            "objects": ["苹果"],
            "possible_defects": ["表面有轻微斑点"],
            "risk": "low",
            "__meta__": {"model": "vision-model"},
        }
    )

    assert parsed == {
        "summary": "图片中有一个红色苹果",
        "objects": ["苹果"],
        "possible_defects": ["表面有轻微斑点"],
        "risk": "low",
    }


def test_manager_answer_includes_real_visual_summary():
    step = AgentPlanStep(
        step_id="vision-step-1",
        owner_agent="vision",
        capability="vision.inspect",
        operation="inspect",
    )
    visual_artifact = artifact(
        step,
        "visual_inspection_result",
        content={
            "summary": "图片中有一个红色苹果",
            "answer": "图片中有一个红色苹果",
            "objects": ["苹果"],
        },
        summary="图片中有一个红色苹果",
    )
    state = ManagerState(
        request_id="request-1",
        workflow_run_id="workflow-1",
        original_query="请识别图片",
        org_id="org-1",
        artifacts=[visual_artifact],
        route_plan=AgentRoutePlan(
            plan_id="plan-1",
            surface="chat",
            goal="识别图片",
            reason="image_understanding",
            steps=[step],
        ),
    )

    answer = ManagerLoop._answer(state, status="completed")

    assert answer.startswith("图片中有一个红色苹果")
    assert "不等同于正式质检结果" in answer
