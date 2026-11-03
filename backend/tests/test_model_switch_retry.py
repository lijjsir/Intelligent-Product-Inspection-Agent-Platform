from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from agent.llm.health_checker import ModelHealthChecker
from agent.llm.runtime_failure import model_failure
from app.api.v1 import agent as api
from app.core.exceptions import ConflictError, ForbiddenError, ValidationError
from app.schemas.user import CurrentUser
from app.services import task_execution_service as launcher


def closed_endpoint():
    response = httpx.Response(400, request=httpx.Request("POST", "https://model.test/chat/completions"),
        json={"error": {"code": "InvalidEndpoint.ClosedEndpoint", "message": "private-request-content"}})
    return httpx.HTTPStatusError("closed", request=response.request, response=response)


def test_failure_message_explains_closed_endpoint_without_exposing_request():
    message, retryable = model_failure(closed_endpoint())
    assert retryable and "端点" in message
    assert "private-request-content" not in message
    assert model_failure(httpx.HTTPStatusError("input", request=httpx.Request("POST", "https://model.test"),
        response=httpx.Response(400)))[1] is False


@pytest.mark.asyncio
async def test_discoverable_cloud_model_with_closed_endpoint_is_not_healthy(monkeypatch):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"data": [{"id": "closed"}]})
        if request.method == "GET" else httpx.Response(400, json={"error": {"code": "InvalidEndpoint.ClosedEndpoint"}}))
    client = httpx.AsyncClient(transport=transport, base_url="https://model.test")
    monkeypatch.setattr("agent.llm.health_checker.httpx.AsyncClient", lambda **_: client)
    status, message = await ModelHealthChecker()._check_one({"endpoint": "https://model.test", "model_key": "closed",
        "provider": "volcengine", "api_key": "private-test-key", "model_type": "multimodal"})
    assert status == "unhealthy" and "端点" in message


@pytest.mark.asyncio
async def test_retry_keeps_input_and_enforces_owner_and_scope(monkeypatch):
    task = SimpleNamespace(status="failed", image_urls=["original.png"], meta_data={"input_mode": "image"})
    class Repo:
        def __init__(self, db): pass
        async def get_for_user(self, org, task_id, owner_user_id):
            assert (org, owner_user_id) == ("org", "owner")
            return task
    launch = AsyncMock(return_value={"status": "queued"})
    monkeypatch.setattr(api, "TaskRepository", Repo)
    monkeypatch.setattr(api, "launch_task_execution", launch)
    user = CurrentUser(user_id="owner", org_id="org", role="user")
    response = await api.retry_task_pipeline("task", user, object())
    assert response.data["status"] == "queued" and task.image_urls == ["original.png"]
    launch.assert_awaited_once_with(task_id="task", org_id="org")
    task.meta_data = {"input_mode": "mixed"}
    with pytest.raises(ValidationError): await api.retry_task_pipeline("task", user, object())
    with pytest.raises(ForbiddenError):
        await api.retry_task_pipeline("task", CurrentUser(user_id="u", org_id="org", role="algorithm_engineer"), object())
    assert launch.await_count == 1


@pytest.mark.asyncio
async def test_launcher_clears_previous_error_and_prevents_duplicate_execution(monkeypatch):
    task = SimpleNamespace(status="failed", meta_data={"input_mode":"image", "execution":
        {"error":"old failure", "finished_at":"2026-11-03T00:00:00Z", "job_id":"old-job"}})
    session = AsyncMock()
    @asynccontextmanager
    async def get_session(): yield session
    class Repo:
        def __init__(self, s): pass
        async def get(self, org, task_id, **kwargs): return task
        async def update_status(self, org, task_id, status): task.status = status
        async def patch_metadata(self, org, task_id, metadata): task.meta_data = metadata
    monkeypatch.setattr(launcher, "get_session", get_session)
    monkeypatch.setattr(launcher, "TaskRepository", Repo)
    monkeypatch.setattr(launcher, "has_active_celery_worker", AsyncMock(return_value=True))
    delay = lambda _: SimpleNamespace(id="new-job")
    monkeypatch.setattr(launcher.run_inspection, "delay", delay)
    await launcher.launch_task_execution("task", "org")
    assert task.meta_data["execution"]["job_id"] == "new-job"
    assert "error" not in task.meta_data["execution"]
    assert task.meta_data["execution_history"][0]["error"] == "old failure"
    with pytest.raises(ConflictError): await launcher.launch_task_execution("task", "org")


@pytest.mark.asyncio
async def test_vision_switches_away_from_closed_model(monkeypatch):
    from agent.router.capabilities.vision_handler import VisionUnderstandingHandler
    from agent.llm.gateway import LLMGateway
    models = [{"id": "cloud", "model_key": "closed"}, {"id": "local", "model_key": "qwen"}]
    class Service:
        def __init__(self, *args): pass
        async def list_runtime_models(self): return models
        async def get_config(self, key): return SimpleNamespace(id=key)
        @staticmethod
        def invalidate_runtime_cache(org): pass
    async def select(self, **kwargs):
        candidates = [m for m in models if m["id"] not in kwargs.get("excluded_runtime_ids", set())]
        return {"model_id": candidates[0]["model_key"], "model_config_id": candidates[0]["id"],
            "runtime_key": candidates[0]["id"], "provider": "local_openai"} if candidates else None
    calls = []
    class Client:
        def __init__(self, **kwargs): self.model = kwargs["model_id"]
        async def vision_chat(self, prompt, urls):
            calls.append((self.model, list(urls)))
            if self.model == "closed": raise closed_endpoint()
            return {"summary": "visible scratch", "defects": []}
    monkeypatch.setattr("app.services.model_config_service.ModelConfigService", Service)
    monkeypatch.setattr(LLMGateway, "select_runtime", select)
    monkeypatch.setattr("agent.llm.client.LLMClient", Client)
    monkeypatch.setattr("app.services.object_storage.resolver.attachment_to_data_url", lambda _: None)
    monkeypatch.setattr("agent.vision.detector_client.VisionDetectorClient.detect", AsyncMock(return_value={}))
    state = SimpleNamespace(trace_id=None, workflow_run_id=None, request_id="request", session_id=None, used_llm_calls=0)
    request = SimpleNamespace(org_id="org", ext={}, metadata={})
    result = await VisionUnderstandingHandler()._try_multimodal_understanding(
        [{"attachment": {"url": "same-image"}}], state, request, db_session=AsyncMock())
    assert result["model_id"] == "qwen"
    assert calls == [("closed", ["same-image"]), ("qwen", ["same-image"])]
    assert result["model_failovers"][0]["model_id"] == "closed"
