from unittest.mock import AsyncMock

import pytest

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.executors.chat_executor import ChatExecutor
from agent.router.manager_state import ManagerState


@pytest.mark.asyncio
@pytest.mark.parametrize("role, has_user_guide", [("user", True), ("expert", False)])
async def test_chat_prompt_includes_help_for_the_authenticated_role(monkeypatch, role, has_user_guide):
    monkeypatch.setattr("app.services.prompt_admin_service.PromptResolver.get", AsyncMock(return_value="管理员配置的问答提示词"))
    state = ManagerState(request_id="request-1", workflow_run_id="workflow-1", org_id="org-1", surface="chat", original_query="这个平台能做什么？")
    request = NormalizedRequest(request_id="request-1", org_id="org-1", user_id="user-1", metadata={"user_role": role})
    prompt = await ChatExecutor()._resolve_system_prompt(state, request, compose=False)
    assert "管理员配置的问答提示词" in prompt
    assert ("PIAP 普通用户功能与操作说明" in prompt) is has_user_guide
    if has_user_guide:
        assert "我的任务" in prompt
        assert "报告导出" in prompt
        assert "普通问题照常回答" in prompt
