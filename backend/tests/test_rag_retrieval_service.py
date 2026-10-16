from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.rag_retrieval_service import RagRetrievalService
from infra.cache.memory_cache import _rag_result_cache, _rag_space_cache


class FakeSession:
    pass


@pytest.mark.asyncio
@pytest.mark.parametrize("user_id", [None, "", "   "])
@pytest.mark.parametrize("include_system,owner", [(True, "other-user"), (False, "other-user"), (False, None)])
async def test_missing_user_identity_does_not_authorize_personal_retrieval(monkeypatch, include_system, owner, user_id):
    _rag_space_cache.clear()
    _rag_result_cache.clear()
    repo = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(
        id="private-space", name="Private", created_by=owner, updated_at=None,
    )))
    monkeypatch.setattr("app.services.rag_retrieval_service.RagSpaceRepository", lambda _session: repo)
    service = RagRetrievalService(None, org_id="org-1", user_id=user_id, include_system=include_system)
    service._retriever = SimpleNamespace(retrieve=AsyncMock())
    result = await service.search(rag_space_id="private-space", query="standard")
    assert result["hit_count"] == 0
    service._retriever.retrieve.assert_not_awaited()


@pytest.mark.asyncio
async def test_anonymous_background_search_lists_only_system_spaces(monkeypatch):
    repo = SimpleNamespace(list_for_org=AsyncMock(return_value=[
        SimpleNamespace(id="system-space", created_by=None),
        SimpleNamespace(id="personal-space", created_by="other-user"),
    ]))
    monkeypatch.setattr("app.services.rag_retrieval_service.RagSpaceRepository", lambda _session: repo)
    service = RagRetrievalService(None, org_id="org-1", user_id=None, include_system=True)
    service.search_many = AsyncMock(return_value={"hits": []})
    await service.search_authorized(query="standard")
    service.search_many.assert_awaited_once_with(rag_space_ids=["system-space"], query="standard", top_k=5)


@pytest.mark.asyncio
async def test_background_system_search_still_works(monkeypatch):
    _rag_space_cache.clear()
    _rag_result_cache.clear()
    repo = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(
        id="system-space", name="System", created_by=None, updated_at=None,
    )))
    monkeypatch.setattr("app.services.rag_retrieval_service.RagSpaceRepository", lambda _session: repo)
    service = RagRetrievalService(None, org_id="org-1", user_id=None, include_system=True)
    service._retriever = SimpleNamespace(retrieve=AsyncMock(return_value=[{"id": "hit", "text": "standard clause", "score": 0.95}]))
    service._workspace_retriever = SimpleNamespace(retrieve=AsyncMock(return_value=[]))
    result = await service.search(rag_space_id="system-space", query="standard")
    assert result["hit_count"] == 1
    assert service._retriever.retrieve.call_args.kwargs["payload_filter"]["rag_space_id"] == "system-space"


class FakeSpaceRepo:
    async def get(self, *, org_id: str, rag_space_id: str, owner_user_id: str | None = None):
        if rag_space_id != "space-1":
            return None

        class Space:
            id = "space-1"
            name = "机械"
            created_by = "user-1"

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
async def test_rag_retrieval_service_filters_hits_below_score_threshold(monkeypatch):
    _rag_space_cache.clear()
    _rag_result_cache.clear()

    class FakeRetriever:
        def __init__(self, **_kwargs):
            pass

        async def retrieve(self, query, top_k=5, payload_filter=None):
            return [
                {"id": "relevant", "title": "doc", "text": "relevant hit", "score": 0.72},
                {"id": "irrelevant", "title": "doc", "text": "irrelevant candidate", "score": 0.31},
            ]

    monkeypatch.setattr("app.services.rag_retrieval_service.RagSpaceRepository", lambda session: FakeSpaceRepo())
    monkeypatch.setattr("app.services.rag_retrieval_service.Retriever", FakeRetriever)
    monkeypatch.setattr("app.services.rag_retrieval_service.settings.rag_score_threshold", 0.55)

    service = RagRetrievalService(FakeSession(), org_id="org-1", user_id="user-1")
    result = await service.search(rag_space_id="space-1", query="anything", top_k=2)

    assert result["hit_count"] == 1
    assert result["candidate_count"] == 2
    assert result["rejected_count"] == 1
    assert result["score_threshold"] == 0.55
    assert [hit["id"] for hit in result["hits"]] == ["relevant"]


@pytest.mark.asyncio
async def test_workspace_retrieval_rejects_formal_and_managed_knowledge_points(monkeypatch):
    _rag_space_cache.clear()
    _rag_result_cache.clear()

    class FakeRetriever:
        def __init__(self, **_kwargs):
            pass

        async def retrieve(self, query, top_k=5, payload_filter=None):
            return [
                {"id": "workspace", "title": "资料", "text": "参考资料", "score": 0.9, "payload": {"resource_domain": "workspace"}},
                {"id": "standard", "title": "标准", "text": "正式标准", "score": 0.99, "payload": {"resource_domain": "formal_standard"}},
                {"id": "managed", "title": "知识", "text": "已确认知识", "score": 0.98, "payload": {"resource_domain": "professional_knowledge"}},
            ]

    monkeypatch.setattr("app.services.rag_retrieval_service.RagSpaceRepository", lambda session: FakeSpaceRepo())
    monkeypatch.setattr("app.services.rag_retrieval_service.Retriever", FakeRetriever)
    service = RagRetrievalService(FakeSession(), org_id="org-1", user_id="user-1")
    result = await service.search(rag_space_id="space-1", query="anything", top_k=5)

    assert [hit["id"] for hit in result["hits"]] == ["workspace"]
    assert result["hits"][0]["resource_domain"] == "workspace"


@pytest.mark.asyncio
async def test_rag_retrieval_service_returns_empty_when_all_candidates_are_below_threshold(monkeypatch):
    _rag_space_cache.clear()
    _rag_result_cache.clear()

    class FakeRetriever:
        def __init__(self, **_kwargs):
            pass

        async def retrieve(self, query, top_k=5, payload_filter=None):
            return [
                {"id": "weak-1", "title": "doc", "text": "weak", "score": 0.3},
                {"id": "weak-2", "title": "doc", "text": "weak", "score": 0.42},
            ]

    monkeypatch.setattr("app.services.rag_retrieval_service.RagSpaceRepository", lambda session: FakeSpaceRepo())
    monkeypatch.setattr("app.services.rag_retrieval_service.Retriever", FakeRetriever)
    monkeypatch.setattr("app.services.rag_retrieval_service.settings.rag_score_threshold", 0.55)

    service = RagRetrievalService(FakeSession(), org_id="org-1", user_id="user-1")
    result = await service.search(rag_space_id="space-1", query="unrelated", top_k=2)

    assert result["hits"] == []
    assert result["hit_count"] == 0
    assert result["candidate_count"] == 2
    assert result["rejected_count"] == 2


@pytest.mark.asyncio
async def test_rag_retrieval_service_can_return_low_confidence_fallback(monkeypatch):
    _rag_space_cache.clear()
    _rag_result_cache.clear()

    class FakeRetriever:
        def __init__(self, **_kwargs):
            pass

        async def retrieve(self, query, top_k=5, payload_filter=None):
            return [
                {"id": "weak-1", "title": "profile", "text": "我叫迪迦，来自M78星云。", "score": 0.34},
                {"id": "weak-2", "title": "other", "text": "other candidate", "score": 0.22},
            ]

    monkeypatch.setattr("app.services.rag_retrieval_service.RagSpaceRepository", lambda session: FakeSpaceRepo())
    monkeypatch.setattr("app.services.rag_retrieval_service.Retriever", FakeRetriever)
    monkeypatch.setattr("app.services.rag_retrieval_service.settings.rag_score_threshold", 0.55)

    service = RagRetrievalService(FakeSession(), org_id="org-1", user_id="user-1")
    result = await service.search(
        rag_space_id="space-1",
        query="我是谁",
        top_k=2,
        include_low_confidence_fallback=True,
    )

    assert result["hit_count"] == 1
    assert result["candidate_count"] == 2
    assert result["rejected_count"] == 1
    assert result["low_confidence_fallback"] is True
    assert [hit["id"] for hit in result["hits"]] == ["weak-1"]


@pytest.mark.asyncio
async def test_rag_retrieval_service_rereads_authorization_and_caches_only_results(monkeypatch):
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
    assert calls == {"space": 2, "retrieve": 2}


@pytest.mark.asyncio
async def test_rag_retrieval_service_search_many_merges_and_dedupes(monkeypatch):
    class FakeSpaceRepo:
        async def get(self, *, org_id: str, rag_space_id: str, owner_user_id: str | None = None):
            class Space:
                id = rag_space_id
                name = f"space-{rag_space_id}"
                updated_at = "version-1"

            return Space()

    class FakeRetriever:
        def __init__(self, **_kwargs):
            pass

        async def retrieve(self, query, top_k=5, payload_filter=None):
            rag_space_id = payload_filter["rag_space_id"]
            if rag_space_id == "space-1":
                return [{"id": "chunk-1", "title": "doc1", "quote": "same", "document_id": "doc-1", "chunk_index": 1, "score": 0.9}]
            return [{"id": "chunk-2", "title": "doc2", "quote": "other", "document_id": "doc-2", "chunk_index": 1, "score": 0.8}]

    monkeypatch.setattr("app.services.rag_retrieval_service.RagSpaceRepository", lambda session: FakeSpaceRepo())
    monkeypatch.setattr("app.services.rag_retrieval_service.Retriever", FakeRetriever)

    service = RagRetrievalService(FakeSession(), org_id="org-1", user_id="user-1")
    result = await service.search_many(rag_space_ids=["space-1", "space-1", "space-2"], query="food", top_k=4)

    assert result["rag_space_ids"] == ["space-1", "space-2"]
    assert result["hit_count"] == 2
