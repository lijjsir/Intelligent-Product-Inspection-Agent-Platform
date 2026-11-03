from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1 import model_configs
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.schemas.governance import ModelVerificationRequest
from app.schemas.user import CurrentUser


@pytest.mark.asyncio
async def test_verification_endpoint_checks_role_before_accessing_model():
    with pytest.raises(ForbiddenError):
        await model_configs.verify_local_model(
            "model-1", ModelVerificationRequest(capabilities=["text"]),
            CurrentUser(user_id="u", org_id="o", role="user"), None,
        )


@pytest.mark.asyncio
async def test_verification_endpoint_uses_current_tenant_and_hides_key(monkeypatch):
    calls = []
    monkeypatch.setattr(model_configs.ModelConfigService, "invalidate_runtime_cache", lambda _: None)

    class Service:
        def __init__(self, db, org_id):
            assert org_id == "org-current"

        async def get_config(self, config_id):
            if config_id != "own-model":
                raise NotFoundError()
            return SimpleNamespace(model_key="local-model")

        @staticmethod
        def invalidate_runtime_cache(org):
            pass

        @staticmethod
        def to_runtime_payload(model):
            return {"provider": "local_openai", "model_key": model.model_key, "api_key": "private-local-key"}

    async def verify(self, runtime, capabilities):
        calls.append(capabilities)
        assert runtime["api_key"] == "private-local-key"
        return [{"capability": "text", "status": "healthy", "message": "OK", "latency_ms": 1}]

    monkeypatch.setattr(model_configs, "ModelConfigService", Service)
    monkeypatch.setattr(model_configs.ModelRuntimeProbe, "verify", verify)
    user = CurrentUser(user_id="u", org_id="org-current", role="algorithm_engineer")
    request = ModelVerificationRequest(capabilities=["text"])
    result = await model_configs.verify_local_model("own-model", request, user, AsyncMock())
    assert result.data.model_key == "local-model"
    assert "private-local-key" not in result.model_dump_json()
    with pytest.raises(NotFoundError):
        await model_configs.verify_local_model("other-tenant-model", request, user, AsyncMock())
    assert calls == [["text"]]


@pytest.mark.asyncio
async def test_verification_endpoint_probes_cloud_models_and_records_failure(monkeypatch):
    model = SimpleNamespace(model_key="cloud-model")
    class Service:
        def __init__(self, *args): pass
        async def get_config(self, config_id): return model
        @staticmethod
        def to_runtime_payload(model): return {"provider":"deepseek", "model_key":model.model_key}
        @staticmethod
        def invalidate_runtime_cache(org): pass
    async def verify(self, runtime, capabilities):
        assert runtime["provider"] == "deepseek"
        return [{"capability":"text", "status":"unhealthy", "message":"endpoint closed", "latency_ms":1}]
    monkeypatch.setattr(model_configs, "ModelConfigService", Service)
    monkeypatch.setattr(model_configs.ModelRuntimeProbe, "verify", verify)
    result = await model_configs.verify_local_model("cloud", ModelVerificationRequest(capabilities=["text"]),
        CurrentUser(user_id="u", org_id="o", role="admin"), AsyncMock())
    assert result.data.results[0].status == "unhealthy"
    assert model.health_status == "unhealthy"
