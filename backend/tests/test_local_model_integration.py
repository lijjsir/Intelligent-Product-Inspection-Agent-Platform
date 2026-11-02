from __future__ import annotations

import json
import threading
from contextlib import nullcontext
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from agent.adapters.llm_adapter import LLMAgentAdapter
from agent.llm.client import LLMClient
from agent.llm.health_checker import ModelHealthChecker
from agent.llm.runtime_probe import ModelRuntimeProbe
from app.schemas.governance import ModelConfigCreate, ModelConfigUpdate, ModelVerificationRequest
from app.services.meeting_ai_service import MeetingAiService


class FakeTracer:
    enabled = False

    def observe(self, **kwargs):
        return nullcontext(None)

    @staticmethod
    def current_observation_id():
        return None


@pytest.fixture
def local_model_api(monkeypatch):
    """Exercise real HTTP and SSE without downloading weights or calling providers."""
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send_json(self, payload, status=200):
            raw = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            assert self.path == "/v1/models"
            self.send_json({"data": [{"id": "piap-test"}]})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append({"path": self.path, "body": body, "authorization": self.headers.get("Authorization")})
            if body.get("model") == "broken":
                self.send_json({"error": "model cannot load"}, status=503)
                return
            if self.path == "/v1/embeddings":
                self.send_json({"data": [{"embedding": [0.1, 0.2, 0.3]}]})
                return
            assert self.path == "/v1/chat/completions"
            if body.get("stream"):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(b'data: {"choices":[{"delta":{"content":"local reply"}}]}\n\ndata: [DONE]\n\n')
                return
            message = {"content": "local reply"}
            if body.get("tools"):
                message = {"content": None, "tool_calls": [{"id": "call_1", "type": "function", "function": {
                    "name": "piap_probe", "arguments": '{"value":"piap"}',
                }}]}
            elif body.get("response_format"):
                message = {"content": '{"ok":true}'}
            self.send_json({"model": body["model"], "choices": [{"message": message, "finish_reason": "stop"}]})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # An explicit LAN/host URL bypasses container-specific loopback remapping.
    monkeypatch.setattr("agent.llm.base_url_resolver._maybe_remap_local_openai_loopback", lambda url: url)
    monkeypatch.setattr("agent.llm.client.LangfuseTracer", FakeTracer)
    endpoint = f"http://127.0.0.1:{server.server_port}/v1"
    try:
        yield endpoint, calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.asyncio
async def test_local_model_works_in_core_meeting_and_streaming_without_key(local_model_api, monkeypatch):
    endpoint, calls = local_model_api
    # A configured cloud credential must never leak into a keyless local runtime.
    monkeypatch.setattr("agent.adapters.llm_adapter.settings.deepseek_api_key", "unrelated-cloud-key")
    monkeypatch.setattr("agent.llm.runtime_options.settings.local_model_reasoning_effort", "none")
    runtime = {"provider": "local_openai", "base_url": endpoint, "model_id": "piap-test"}
    client = LLMClient(**runtime, embed_model="piap-test")
    assert (await client.chat([{"role": "user", "content": "hello"}]))["text"] == "local reply"
    assert (await client.vision_chat("describe", ["data:image/png;base64,test"]))["text"] == "local reply"
    assert await client.embed("hello") == [0.1, 0.2, 0.3]
    assert (await client.chat_with_tools([], tools=[{"type": "function", "function": {"name": "piap_probe"}}]))["tool_calls"][0]["name"] == "piap_probe"

    service = MeetingAiService(None, "org-test", "user-test")
    assert await service._request_completion([], runtime=runtime, temperature=0, max_tokens=20) == "local reply"
    deltas = []

    async def emit(event):
        deltas.append(event)

    assert await LLMAgentAdapter()._stream_llm([], emit, runtime_model=runtime) == "local reply"
    assert deltas == [{"event": "message_delta", "delta": "local reply"}]
    assert len(calls) == 6
    assert all(call["authorization"] is None for call in calls)
    assert all(call["body"].get("reasoning_effort") == "none" for call in calls if "messages" in call["body"])
    assert all("reasoning_effort" not in call["body"] for call in calls if "input" in call["body"])


@pytest.mark.asyncio
async def test_local_model_preserves_its_own_key(local_model_api):
    endpoint, calls = local_model_api
    runtime = {"provider": "local_openai", "base_url": endpoint, "model_id": "piap-test", "api_key": "local-secret"}
    await MeetingAiService(None, "o", "u")._request_completion([], runtime=runtime, temperature=0, max_tokens=16)
    assert calls[0]["authorization"] == "Bearer local-secret"


@pytest.mark.asyncio
async def test_all_capabilities_use_real_local_http_and_validate_responses(local_model_api):
    endpoint, calls = local_model_api
    item = {"provider": "local_openai", "endpoint": endpoint, "model_key": "piap-test"}
    results = await ModelRuntimeProbe().verify(item, ["text", "json", "vision", "tools", "embedding", "text"])
    assert len(results) == len(calls) == 5
    assert all(result["status"] == "healthy" for result in results)
    assert results[-1]["vector_dimension"] == 3
    assert all(call["authorization"] is None for call in calls)
    image = calls[2]["body"]["messages"][0]["content"][1]["image_url"]["url"]
    assert image.startswith("data:image/png;base64,")


@pytest.mark.asyncio
@pytest.mark.parametrize("model_type,expected_path", [("chat", "/v1/chat/completions"), ("multimodal", "/v1/chat/completions"), ("embedding", "/v1/embeddings")])
async def test_local_health_requires_actual_inference(local_model_api, model_type, expected_path):
    endpoint, calls = local_model_api
    checked = await ModelHealthChecker().check([{
        "provider": "local_openai", "endpoint": endpoint, "model_key": "piap-test", "model_type": model_type,
    }])
    assert checked[0]["health_status"] == "healthy"
    assert calls[0]["path"] == expected_path
    if model_type == "multimodal":
        assert isinstance(calls[0]["body"]["messages"][0]["content"], list)


@pytest.mark.asyncio
@pytest.mark.parametrize("status,payload,expected", [
    (200, {"choices": []}, "unhealthy"),
    (200, {"choices": [{"message": {"content": ""}}]}, "unhealthy"),
    (503, {"error": "cannot load model"}, "degraded"),
    (401, {"error": "unauthorized"}, "unhealthy"),
    (400, {"error": "unsupported images"}, "unhealthy"),
])
async def test_listed_local_model_is_not_healthy_when_inference_fails(monkeypatch, status, payload, expected):
    real_client = httpx.AsyncClient

    def handler(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "local-model"}]})
        return httpx.Response(status, json=payload)

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(handler)))
    checked = await ModelHealthChecker().check([{
        "provider": "local_openai", "endpoint": "http://model-service:11434/v1", "model_key": "local-model",
    }])
    assert checked[0]["health_status"] == expected


@pytest.mark.parametrize("capability,payload", [
    ("embedding", {"data": [{"embedding": []}]}),
    ("embedding", {"data": [{"embedding": [float("nan")]}]}),
    ("tools", {"choices": [{"message": {"content": "I would call a tool"}}]}),
    ("tools", {"choices": [{"message": None}]}),
    ("tools", {"choices": [{"message": {"tool_calls": ["invalid"]}}]}),
    ("json", {"choices": [{"message": {"content": "not json"}}]}),
])
def test_capability_checks_reject_invalid_protocol_output(capability, payload):
    with pytest.raises((ValueError, KeyError)):
        ModelRuntimeProbe._validate(payload, capability)


@pytest.mark.parametrize("alias,canonical", [("vision", "multimodal"), ("vlm", "multimodal"), ("llm", "chat"), ("embed", "embedding")])
def test_model_type_aliases_are_normalized_on_create_and_update(alias, canonical):
    created = ModelConfigCreate(provider="local_openai", model_key="m", display_name="m", source_uri="m", endpoint="http://model/v1", model_type=alias)
    assert created.model_type == canonical
    assert ModelConfigUpdate(model_type=alias).model_type == canonical


def test_verification_request_rejects_unknown_capability():
    with pytest.raises(ValueError):
        ModelVerificationRequest(capabilities=["execute_business_tool"])
