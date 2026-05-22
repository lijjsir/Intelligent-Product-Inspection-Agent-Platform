from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.model_config_service import ModelConfigService
from infra.cache.memory_cache import _model_config_cache


class FakeSession:
    async def commit(self):
        return None


def model(model_key: str, model_type: str = "chat"):
    return SimpleNamespace(
        id=model_key,
        org_id="org-1",
        provider="custom",
        model_key=model_key,
        endpoint="http://models",
        model_type=model_type,
        priority=1,
        rpm_limit=None,
        input_price_per_million=None,
        output_price_per_million=None,
        is_active=True,
        health_status="healthy",
        health_message=None,
        api_key_enc=None,
    )


@pytest.mark.asyncio
async def test_runtime_models_cache_by_org_and_model_type(monkeypatch):
    _model_config_cache.clear()
    calls: list[str] = []

    class FakeRepo:
        def __init__(self, _session):
            pass

        async def list_active(self, org_id: str):
            calls.append(org_id)
            return [model("chat-1", "chat"), model("embed-1", "embedding")]

    monkeypatch.setattr("app.services.model_config_service.ModelConfigRepository", FakeRepo)

    service = ModelConfigService(FakeSession(), "org-1")
    chat_models = await service.list_runtime_models(model_type="chat")
    embed_models = await service.list_runtime_models(model_type="embedding")
    chat_models_again = await service.list_runtime_models(model_type="chat")

    assert [item["model_key"] for item in chat_models] == ["chat-1"]
    assert [item["model_key"] for item in embed_models] == ["embed-1"]
    assert chat_models_again == chat_models
    assert calls == ["org-1", "org-1"]


@pytest.mark.asyncio
async def test_runtime_model_cache_invalidates_after_update(monkeypatch):
    _model_config_cache.clear()
    calls: list[str] = []
    stored = model("chat-old")

    class FakeRepo:
        def __init__(self, _session):
            pass

        async def list_active(self, org_id: str):
            calls.append(org_id)
            return [stored]

        async def get(self, _org_id: str, _config_id: str):
            return stored

        async def save(self, target, payload: dict):
            for key, value in payload.items():
                setattr(target, key, value)
            return target

    monkeypatch.setattr("app.services.model_config_service.ModelConfigRepository", FakeRepo)

    service = ModelConfigService(FakeSession(), "org-1")
    assert (await service.list_runtime_models())[0]["model_key"] == "chat-old"
    stored.model_key = "chat-stale"
    assert (await service.list_runtime_models())[0]["model_key"] == "chat-old"

    await service.update_config("chat-old", {"display_name": "new"})

    assert (await service.list_runtime_models())[0]["model_key"] == "chat-stale"
    assert calls == ["org-1", "org-1"]
