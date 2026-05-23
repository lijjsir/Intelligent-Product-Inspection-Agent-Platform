from __future__ import annotations

import pytest

from app.services.rag_retrieval_service import RagRetrievalService
from infra.cache.memory_cache import _rag_result_cache, _rag_space_cache


class FakeSession:
    pass


class FakeSpaceRepo:
    async def get(self, *, org_id: str, rag_space_id: str, owner_user_id: str | None = None):
        if rag_space_id != "space-1":
            return None

        class Space:
            id = "space-1"
            name = "机械"

        return Space()


@pytest.mark.asyncio
async def test_rag_retrieval_service_returns_chunk_hits_with_scope_filters(monkeypatch):
    captured: dict[str, object] = {}

    class FakeRetriever:
        def __init__(self, **kwargs):
            captured["init"] = kwargs

        async def retrieve(self, query, top_k=5, payload_filter=None):
            captured["query"] = query
            captured["top_k"] = top_k
            captured["payload_filter"] = payload_filter
            return [
                {
                    "id": "chunk-1",
                    "title": "spec.txt",
                    "source": "机械/spec.txt",
                    "full_path": "机械/spec.txt",
                    "text": "Scratch defects larger than 2mm are rejected.",
                    "quote": "Scratch defects larger than 2mm are rejected.",
                    "score": 0.91,
                    "chunk_index": 1,
                    "page_number": None,
                }
            ]

    monkeypatch.setattr("app.services.rag_retrieval_service.RagSpaceRepository", lambda session: FakeSpaceRepo())
    monkeypatch.setattr("app.services.rag_retrieval_service.Retriever", FakeRetriever)
    service = RagRetrievalService(FakeSession(), org_id="org-1", user_id="user-1")

    result = await service.search(
        rag_space_id="space-1",
        query="scratch defect",
        top_k=3,
        scope_node_ids=["folder-1"],
    )

    assert result["hit_count"] == 1
    assert captured["payload_filter"] == {
        "org_id": "org-1",
        "user_id": "user-1",
        "rag_space_id": "space-1",
        "ancestor_node_ids": ["folder-1"],
    }
    assert result["hits"][0]["full_path"] == "机械/spec.txt"
    assert result["hits"][0]["chunk_index"] == 1
    assert result["hits"][0]["page_number"] is None


@pytest.mark.asyncio
async def test_rag_retrieval_service_caches_space_and_result(monkeypatch):
    _rag_space_cache.clear()
    _rag_result_cache.clear()
    calls = {"space": 0, "retrieve": 0}

    class FakeSpaceRepoWithCount:
        async def get(self, *, org_id: str, rag_space_id: str, owner_user_id: str | None = None):
            calls["space"] += 1

            class Space:
                id = "space-1"
                name = "cached"
                updated_at = "version-1"

            return Space()

    class FakeRetrieverWithCount:
        def __init__(self, **_kwargs):
            pass

        async def retrieve(self, query, top_k=5, payload_filter=None):
            calls["retrieve"] += 1
            return [{"id": "chunk-1", "title": "doc", "text": "cached hit", "score": 0.8}]

    monkeypatch.setattr("app.services.rag_retrieval_service.RagSpaceRepository", lambda session: FakeSpaceRepoWithCount())
    monkeypatch.setattr("app.services.rag_retrieval_service.Retriever", FakeRetrieverWithCount)

    service = RagRetrievalService(FakeSession(), org_id="org-1", user_id="user-1")
    first = await service.search(rag_space_id="space-1", query="scratch", top_k=3, scope_node_ids=["node-1"])
    second = await service.search(rag_space_id="space-1", query="scratch", top_k=3, scope_node_ids=["node-1"])

    assert first["hits"] == second["hits"]
    assert calls == {"space": 1, "retrieve": 1}
