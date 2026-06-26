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
