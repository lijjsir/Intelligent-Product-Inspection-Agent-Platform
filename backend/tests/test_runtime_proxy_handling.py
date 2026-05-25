from __future__ import annotations

from contextlib import nullcontext

import pytest

from agent.llm.client import LLMClient
from agent.rag.knowledge_indexer import KnowledgeIndexer
from agent.rag.retriever import Retriever
from agent.subgraphs.inspection_task.nodes.vision import run_vision
from agent.vision.detector_client import VisionDetectorClient


@pytest.mark.asyncio
async def test_llm_client_disables_env_proxy(monkeypatch):
    class FakeTracer:
        enabled = False

        def observe(self, **_kwargs):
            return nullcontext(None)

        @staticmethod
        def current_observation_id():
            return None

    class FakeResponse:
        status_code = 200
        is_error = False
        request = object()

        @staticmethod
        def json():
            return {
                "id": "resp-1",
                "model": "chat-1",
                "choices": [{"message": {"content": '{"answer":"ok"}'}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            assert kwargs["trust_env"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, path, json=None, headers=None):
            return FakeResponse()

    monkeypatch.setattr("agent.llm.client.LangfuseTracer", lambda: FakeTracer())
    monkeypatch.setattr("agent.llm.client.httpx.AsyncClient", FakeClient)

    client = LLMClient(api_key="secret", base_url="https://example.com/api/v3", model_id="chat-1")
    data = await client.chat([{"role": "user", "content": "ping"}])

    assert data["answer"] == "ok"


@pytest.mark.asyncio
async def test_llm_client_lazily_builds_ark_client_without_env_proxy(monkeypatch):
    sync_client_calls: list[dict] = []

    class FakeTracer:
        enabled = False

        def observe(self, **_kwargs):
            return nullcontext(None)

        @staticmethod
        def current_observation_id():
            return None

    class FakeSyncClient:
        def __init__(self, *args, **kwargs):
            sync_client_calls.append(kwargs)

    class FakeArk:
        def __init__(self, **kwargs):
            assert kwargs["api_key"] == "secret"
            assert isinstance(kwargs["http_client"], FakeSyncClient)
            self.multimodal_embeddings = self

        @staticmethod
        def create(model=None, input=None):
            return {
                "data": [{"embedding": [0.1, 0.2, 0.3]}],
                "model": model,
                "usage": {"prompt_tokens": 1, "completion_tokens": 0, "total_tokens": 1},
            }

    monkeypatch.setattr("agent.llm.client.LangfuseTracer", lambda: FakeTracer())
    monkeypatch.setattr("agent.llm.client.httpx.Client", FakeSyncClient)
    monkeypatch.setattr("agent.llm.client.Ark", FakeArk)

    client = LLMClient(api_key="secret", base_url="https://example.com/api/v3", model_id="chat-1", embed_model="ep-1")

    assert client._ark_client is None

    vector = await client.embed("ping")

    assert vector == [0.1, 0.2, 0.3]
    assert {"trust_env": False} in sync_client_calls


@pytest.mark.asyncio
async def test_retriever_disables_env_proxy(monkeypatch):
    class FakeResponse:
        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {"result": []}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            assert kwargs["trust_env"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, headers=None):
            return FakeResponse()

    async def fake_embed(self, text: str):
        return [0.1, 0.2, 0.3]

    monkeypatch.setattr("agent.rag.retriever.Embedder.embed", fake_embed)
    monkeypatch.setattr("agent.rag.retriever.httpx.AsyncClient", FakeClient)

    docs = await Retriever().retrieve("scratch defect")

    assert docs == []


@pytest.mark.asyncio
async def test_knowledge_indexer_disables_env_proxy(monkeypatch):
    client_calls: list[dict] = []

    class FakeResponse:
        status_code = 200

        @staticmethod
        def raise_for_status():
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            client_calls.append(kwargs)
            assert kwargs["trust_env"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def put(self, url, json=None, headers=None):
            return FakeResponse()

    async def fake_embed(self, text: str):
        return [0.1, 0.2, 0.3]

    monkeypatch.setattr("agent.rag.knowledge_indexer.Embedder.embed", fake_embed)
    monkeypatch.setattr("agent.rag.knowledge_indexer.httpx.AsyncClient", FakeClient)

    result = await KnowledgeIndexer(org_id="org-1").index(
        [{"id": "doc-1", "title": "Doc", "text": "defect summary", "source": "task"}]
    )

    assert result == {"accepted": 1, "failed_embeddings": 0}
    assert len(client_calls) == 2


@pytest.mark.asyncio
async def test_vision_detector_disables_env_proxy(monkeypatch):
    class FakeResponse:
        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {"detections": []}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            assert kwargs["trust_env"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, headers=None):
            return FakeResponse()

    monkeypatch.setattr("agent.vision.detector_client.settings.vision_detector_url", "https://example.com/detect")
    monkeypatch.setattr("agent.vision.detector_client.httpx.AsyncClient", FakeClient)

    result = await VisionDetectorClient().detect(image_urls=["https://example.com/a.png"])

    assert result == {"detections": []}


@pytest.mark.asyncio
async def test_run_vision_records_runtime_error_when_llm_client_init_fails(monkeypatch):
    class FailingClient:
        def __init__(self, *args, **kwargs):
            raise ValueError("Unknown scheme for proxy URL URL('socks://127.0.0.1:7897/')")

    monkeypatch.setattr("agent.subgraphs.inspection_task.nodes.vision.LLMClient", FailingClient)

    state = await run_vision(
        {
            "task_id": "task-1",
            "org_id": "org-1",
            "image_urls": ["https://example.com/a.png"],
            "model_id": "chat-1",
            "model_base_url": "https://example.com/api/v3",
            "model_api_key": "secret",
            "model_provider": "volcengine",
            "trace_id": "trace-1",
            "timeline": [],
            "usage_events": [],
            "runtime_errors": [],
        }
    )

    assert state["defects"] == []
    assert state["runtime_errors"][0]["stage"] == "vision"
    assert "Unknown scheme for proxy URL" in state["runtime_errors"][0]["message"]
