from __future__ import annotations

import pytest

from app.services.memory_graph_store import (
    MemoryGraphEdge,
    MemoryGraphNode,
    MySQLMemoryGraphStore,
)


class FakeSession:
    pass


class FakeDepRepo:
    def __init__(self):
        self.upserted = []
        self.edges = []

    async def upsert_edge(self, **kwargs):
        self.upserted.append(kwargs)
        return SimpleNamespace(**kwargs)

    async def list_by_edge_type(self, memory_id, edge_types, direction="source"):
        return [
            e for e in self.edges
            if e.source_memory_id == memory_id and e.edge_type in edge_types
        ]


class SimpleNamespace:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.mark.asyncio
async def test_mysql_store_create_memory_edge(monkeypatch):
    dep_repo = FakeDepRepo()
    monkeypatch.setattr(
        "app.repositories.memory_repo.MemoryDependencyRepository",
        lambda session, org_id: dep_repo,
    )
    store = MySQLMemoryGraphStore(FakeSession(), "org-1")
    edge = MemoryGraphEdge(
        source_memory_id="mem-a",
        target_memory_id="mem-b",
        edge_type="derived_from",
        strength=0.9,
    )
    await store.create_memory_edge(edge)
    assert len(dep_repo.upserted) == 1
    assert dep_repo.upserted[0]["source_memory_id"] == "mem-a"


@pytest.mark.asyncio
async def test_mysql_store_upsert_memory_node_is_noop():
    store = MySQLMemoryGraphStore(FakeSession(), "org-1")
    node = MemoryGraphNode(memory_id="mem-1", org_id="org-1")
    await store.upsert_memory_node(node)


@pytest.mark.asyncio
async def test_mysql_store_health_check():
    store = MySQLMemoryGraphStore(FakeSession(), "org-1")
    assert await store.health_check() is True


@pytest.mark.asyncio
async def test_mysql_store_upsert_rag_chunk_node_is_noop():
    store = MySQLMemoryGraphStore(FakeSession(), "org-1")
    await store.upsert_rag_chunk_node("org-1", "chunk-1")


@pytest.mark.asyncio
async def test_mysql_store_memory_rag_edge_is_noop():
    store = MySQLMemoryGraphStore(FakeSession(), "org-1")
    await store.create_memory_rag_edge("mem-1", "chunk-1", "cited_as_evidence")
