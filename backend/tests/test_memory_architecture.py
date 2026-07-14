from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.schemas.memory import (
    MemoryContent,
    MemoryContext,
    MemoryScope,
    MemorySearchItem,
    MemorySearchRequest,
    MemorySearchResponse,
    MemorySource,
    MemoryType,
    MemoryWriteRequest,
    RetrievalGatewayRequest,
    RetrievalGatewayScope,
    ScopeFilter,
    Workspace,
)
from app.services.memory_service import MemoryService
from app.services.retrieval_gateway_service import RetrievalGatewayService


class FakeEventRepo:
    def __init__(self):
        self.events = []

    async def create(self, event):
        self.events.append(event)
        return event


class FakeItemRepo:
    def __init__(self, eligible=None):
        self.created = []
        self.calls = []
        self.eligible = eligible or []

    async def create(self, item):
        self.created.append(item)
        return item

    async def list_retrievable_by_scope(self, **kwargs):
        self.calls.append(kwargs)
        return self.eligible


class FakeVector:
    def __init__(self, results=None):
        self.search_calls = []
        self.upserts = []
        self.results = results or []

    async def upsert_memory(self, **kwargs):
        self.upserts.append(kwargs)

    async def search(self, **kwargs):
        self.search_calls.append(kwargs)
        return self.results


def memory_write_request(scope: MemoryScope | None) -> MemoryWriteRequest:
    return MemoryWriteRequest(
        org_id="org-1",
        user_id="user-1",
        source=MemorySource(kind="tool", trace_id="trace-1"),
        memory_type=MemoryType.INSPECTION_PATTERN,
        scope=scope,
        content=MemoryContent(summary="P001 抽检风险在近期批次中上升"),
        confidence=0.85,
        trace_id="trace-1",
    )


def test_memory_write_accepts_product_line_scope():
    request = memory_write_request(MemoryScope(product_line="P001"))

    assert request.scope is not None
    assert request.scope.product_line == "P001"


def test_memory_write_rejects_missing_product_line_scope():
    with pytest.raises(ValueError, match="requires product_line"):
        memory_write_request(MemoryScope())


@pytest.mark.asyncio
async def test_memory_search_passes_current_scope_filters_to_repo_and_vector():
    memory = SimpleNamespace(
        memory_id="mem-1",
        memory_type="inspection_pattern",
        content_summary="P001 批次 B-01 需要提高抽检比例",
        content_json={},
        source_event_ids=None,
        evidence_pointers=None,
        trust_score=0.9,
        confidence=0.8,
        usage_policy="context_only",
        scope_json={
            "product_line": "P001",
        },
        trace_id="trace-1",
    )
    fake_items = FakeItemRepo(eligible=[memory])
    fake_events = FakeEventRepo()
    fake_vector = FakeVector(results=[{"memory_id": "mem-1", "score": 0.77}])
    service = MemoryService(None, "org-1", vector_service=fake_vector)
    service._item_repo = fake_items
    service._event_repo = fake_events

    response = await service.search(
        MemorySearchRequest(
            org_id="org-1",
            user_id="user-1",
            query="P001 批次风险",
            scope_filter=ScopeFilter(product_line="P001"),
            top_k=3,
        )
    )

    assert response.items[0].memory_id == "mem-1"
    repo_call = fake_items.calls[0]
    assert repo_call["product_line"] == "P001"
    vector_call = fake_vector.search_calls[0]
    assert vector_call["product_line"] == "P001"


@pytest.mark.asyncio
async def test_retrieval_gateway_keeps_document_and_memory_evidence_separate():
    class FakeRagService:
        async def search(self, **kwargs):
            return {
                "hits": [{"id": "doc-1", "quote": "标准要求按 AQL 抽检", "score": 0.88}],
                "hit_count": 1,
            }

    class FakeMemoryService:
        async def search(self, request):
            item = MemorySearchItem(
                memory_id="mem-1",
                memory_type="inspection_pattern",
                summary="P001 近期批次有冲突风险",
                score=0.81,
                warnings=["冲突风险需复核"],
            )
            return MemorySearchResponse(
                memory_context=MemoryContext(items=[item]),
                items=[item],
            )

    service = RetrievalGatewayService(
        object(),
        org_id="org-1",
        user_id="user-1",
        rag_service=FakeRagService(),
        memory_service=FakeMemoryService(),
    )

    response = await service.search(
        RetrievalGatewayRequest(
            org_id="org-1",
            user_id="user-1",
            workspace=Workspace.APP,
            query="P001 抽检要求",
            scope=RetrievalGatewayScope(rag_space_id="rag-1", product_id="P001"),
            top_k=3,
        )
    )

    assert response.document_evidence[0]["id"] == "doc-1"
    assert response.memory_evidence[0].memory_id == "mem-1"
    assert response.memory_context.items[0].memory_id == "mem-1"
    assert response.conflicts[0]["memory_id"] == "mem-1"
    assert "memory_document_conflict_check_required" in response.warnings
