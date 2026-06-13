from __future__ import annotations

import uuid

import pytest

from app.services.memory_vector_service import MemoryVectorService


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = "{}"

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


def test_memory_vector_point_id_is_stable_uuid():
    first = MemoryVectorService._point_id("mem_abc")
    second = MemoryVectorService._point_id("mem_abc")

    assert first == second
    assert str(uuid.UUID(first)) == first


@pytest.mark.asyncio
async def test_upsert_memory_ensures_collection_and_preserves_memory_id(monkeypatch):
    calls: list[tuple[str, str, dict | None]] = []

    async def embedder(text: str):
        assert text == "stable lesson"
        return [0.1, 0.2, 0.3]

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            calls.append(("GET", url, None))
            return FakeResponse(status_code=404)

        async def put(self, url, json=None, headers=None):
            calls.append(("PUT", url, json))
            return FakeResponse(status_code=200)

    monkeypatch.setattr("app.services.memory_vector_service.httpx.AsyncClient", FakeClient)
    service = MemoryVectorService(
        collection="piap_shared_memory",
        embedder_factory=embedder,
        org_id="org-1",
    )

    await service.upsert_memory(
        memory_id="mem_abc",
        org_id="org-1",
        user_id="user-1",
        memory_type="inspection_pattern",
        status="active",
        summary="stable lesson",
    )

    collection_put = calls[1]
    point_put = calls[2]
    assert collection_put[0] == "PUT"
    assert collection_put[2]["vectors"]["size"] == 3
    point = point_put[2]["points"][0]
    assert str(uuid.UUID(point["id"])) == point["id"]
    assert point["payload"]["memory_id"] == "mem_abc"


@pytest.mark.asyncio
async def test_search_filter_includes_user_and_org_shared_memory(monkeypatch):
    calls: list[tuple[str, str, dict | None]] = []

    async def embedder(text: str):
        assert text == "camera threshold"
        return [0.2, 0.1, 0.4]

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, headers=None):
            calls.append(("POST", url, json))
            return FakeResponse(
                status_code=200,
                payload={
                    "result": [
                        {
                            "id": "ignored-qdrant-id",
                            "score": 0.87,
                            "payload": {"memory_id": "mem-shared"},
                        }
                    ]
                },
            )

    monkeypatch.setattr("app.services.memory_vector_service.httpx.AsyncClient", FakeClient)
    service = MemoryVectorService(
        collection="piap_shared_memory",
        embedder_factory=embedder,
        org_id="org-1",
        user_id="user-1",
    )

    results = await service.search("camera threshold", org_id="org-1", user_id="user-1")

    qdrant_filter = calls[0][2]["filter"]
    assert {"key": "org_id", "match": {"value": "org-1"}} in qdrant_filter["must"]
    assert {"key": "status", "match": {"value": "active"}} in qdrant_filter["must"]
    assert {"key": "user_id", "match": {"value": "user-1"}} not in qdrant_filter["must"]
    assert qdrant_filter["should"] == [
        {"key": "user_id", "match": {"value": "user-1"}},
        {"key": "user_id", "match": {"value": ""}},
    ]
    assert qdrant_filter["minimum_should_match"] == 1
    assert results[0]["memory_id"] == "mem-shared"
