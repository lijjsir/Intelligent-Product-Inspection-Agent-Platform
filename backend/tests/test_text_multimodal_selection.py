from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent.llm.model_selector import ModelSelector
from agent.llm.gateway import LLMGateway
from app.services.supervision_service import SupervisionService
from app.schemas.user import CurrentUser


def model(kind="multimodal", **extra):
    return {"id":"vlm-runtime","model_key":"demo-vlm","model_type":kind,"is_active":True,
        "provider":"local_openai","endpoint":"http://127.0.0.1:9999/v1","health_status":"healthy",**extra}


@pytest.mark.parametrize("kind",["vision","multimodal","vlm"])
def test_plain_text_selection_accepts_configured_multimodal_fallback(kind):
    selected=ModelSelector().select([model(kind)],model_types={"chat","llm","text_generation"})
    assert selected["id"]=="vlm-runtime"


def test_embeddings_inactive_and_unconfigured_models_remain_excluded():
    values=[model("embedding"),model("multimodal",is_active=False),model("vlm",endpoint="")]
    assert ModelSelector().select(values,model_types={"chat"}) is None
    assert ModelSelector().select([model("chat")],model_types={"embedding"}) is None
    assert ModelSelector().select([model("chat")],model_types={"vision"}) is None


@pytest.mark.asyncio
async def test_supervision_text_path_resolves_multimodal_and_propagates_real_call_failure(monkeypatch):
    from app.services.model_config_service import ModelConfigService
    from agent.llm.client import LLMClient
    monkeypatch.setattr(ModelConfigService,"list_runtime_models",AsyncMock(return_value=[model()]))
    monkeypatch.setattr(LLMGateway,"_within_rate_limit",AsyncMock(return_value=True))
    chat=AsyncMock(side_effect=RuntimeError("inference unavailable"));monkeypatch.setattr(LLMClient,"chat",chat)
    service=SupervisionService(SimpleNamespace(),CurrentUser(user_id="expert",org_id="local",role="expert"))
    call=await service.model_call("test-trace")
    assert call is not None and call.model_versions["analyst"]=="demo-vlm"
    with pytest.raises(RuntimeError,match="inference unavailable"):
        await call("risk_analysis",{"text":"test only"})
    chat.assert_awaited_once()
    assert call.model_versions['llm_called'] is True
    assert call.model_versions['model_success'] is False
    assert call.model_versions['successful_calls'] == 0


@pytest.mark.asyncio
async def test_partial_provider_success_does_not_claim_complete_model_success(monkeypatch):
    from app.services.model_config_service import ModelConfigService
    from agent.llm.client import LLMClient
    monkeypatch.setattr(ModelConfigService, 'list_runtime_models', AsyncMock(return_value=[model()]))
    monkeypatch.setattr(LLMGateway, '_within_rate_limit', AsyncMock(return_value=True))
    chat = AsyncMock(side_effect=[{'choices':[{'message':{'content':'{"summary":"test"}'}}]}, RuntimeError('review unavailable')])
    monkeypatch.setattr(LLMClient, 'chat', chat)
    call = await SupervisionService(SimpleNamespace(), CurrentUser(user_id='expert',org_id='local',role='expert')).model_call()
    assert await call('assessment', {}) == {'summary':'test'}
    with pytest.raises(RuntimeError):
        await call('independent_review', {})
    assert call.model_versions['attempted_calls'] == 2
    assert call.model_versions['successful_calls'] == 1
    assert call.model_versions['model_success'] is False
