import pytest

from agent.llm.health_checker import ModelHealthChecker


def test_missing_model_key_message_includes_available_candidates():
    message = ModelHealthChecker._missing_model_key_message(
        "target-model",
        {"model-b", "model-a", "model-c", "model-d", "model-e", "model-f"},
    )

    assert message is not None
    assert "missing model_key: target-model" in message
    assert "available: [model-a, model-b, model-c, model-d, model-e]" in message


def test_direct_probe_success_message_includes_available_candidates():
    message = ModelHealthChecker._direct_probe_success_message(
        "ep-test",
        {"deepseek-r1", "deepseek-r1-250120"},
        probe_path="/chat/completions",
    )

    assert message is not None
    assert "/chat/completions accepted model_key: ep-test" in message
    assert "available: [deepseek-r1, deepseek-r1-250120]" in message


@pytest.mark.asyncio
async def test_health_checker_disables_env_proxy(monkeypatch):
    class FakeResponse:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return [{"id": "chat-1"}]

    class FakeClient:
        def __init__(self, *args, **kwargs):
            assert kwargs["trust_env"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, path, headers=None):
            return FakeResponse()

    monkeypatch.setattr("agent.llm.health_checker.httpx.AsyncClient", FakeClient)

    checked = await ModelHealthChecker().check(
        [
            {
                "id": "cfg-1",
                "endpoint": "https://example.com/api/v3",
                "model_key": "chat-1",
            }
        ]
    )

    assert checked[0]["health_status"] == "healthy"


@pytest.mark.asyncio
async def test_health_checker_remaps_local_openai_loopback_endpoint_inside_container(monkeypatch):
    class FakeResponse:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return [{"id": "qwen2.5:7b-instruct"}]

    class FakeClient:
        calls: list[dict] = []

        def __init__(self, *args, **kwargs):
            self.calls.append(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, path, headers=None):
            return FakeResponse()

    monkeypatch.setattr("agent.llm.health_checker.httpx.AsyncClient", FakeClient)
    monkeypatch.setattr("agent.llm.base_url_resolver.os.path.exists", lambda path: path == "/.dockerenv")
    monkeypatch.setattr(
        "agent.llm.base_url_resolver.settings.local_openai_docker_base_url",
        "http://host.docker.internal:11434/v1",
    )

    checked = await ModelHealthChecker().check(
        [
            {
                "id": "cfg-1",
                "provider": "local_openai",
                "endpoint": "http://localhost:11434/v1",
                "model_key": "qwen2.5:7b-instruct",
            }
        ]
    )

    assert FakeClient.calls[0]["base_url"] == "http://host.docker.internal:11434/v1"
    assert checked[0]["health_status"] == "healthy"
