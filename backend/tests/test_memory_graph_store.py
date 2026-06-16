from __future__ import annotations

import json

import pytest

from app.services.memory_graph_store import (
    MemoryGraphEdge,
    MemoryGraphNode,
    MySQLMemoryGraphStore,
)
from app.errors.memory_errors import GraphMemoryError


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
        org_id="org-1",
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


@pytest.mark.asyncio
async def test_neo4j_store_uses_async_driver_and_merges_edge_nodes(monkeypatch):
    from app.services import neo4j_memory_graph_store as graph_mod

    executed: list[tuple[str, dict]] = []

    class FakeResult:
        async def consume(self):
            return None

    class FakeTx:
        async def run(self, query, params):
            executed.append((query, params))
            return FakeResult()

    class FakeSessionCtx:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute_write(self, fn, query, params):
            return await fn(FakeTx(), query, params)

    class FakeDriver:
        def session(self, database):
            assert database == "neo4j"
            return FakeSessionCtx()

    class FakeAsyncGraphDatabase:
        @staticmethod
        def driver(uri, auth):
            assert uri == "bolt://neo4j:7687"
            assert auth == ("neo4j", "secret")
            return FakeDriver()

    monkeypatch.setattr(graph_mod, "AsyncGraphDatabase", FakeAsyncGraphDatabase)

    store = graph_mod.Neo4jMemoryGraphStore("bolt://neo4j:7687", "neo4j", "secret")
    await store.create_memory_edge(
        MemoryGraphEdge(
            org_id="org-1",
            source_memory_id="mem-a",
            target_memory_id="mem-b",
            edge_type="derived_from",
        )
    )

    query, params = executed[0]
    assert "MERGE (src:Memory" in query
    assert "MERGE (dst:Memory" in query
    assert params["org_id"] == "org-1"
    assert json.loads(params["metadata_json"]) == {}


@pytest.mark.asyncio
async def test_neo4j_store_writes_allowed_typed_memory_relationship(monkeypatch):
    from app.services import neo4j_memory_graph_store as graph_mod

    executed: list[tuple[str, dict]] = []

    class FakeResult:
        async def consume(self):
            return None

    class FakeTx:
        async def run(self, query, params):
            executed.append((query, params))
            return FakeResult()

    class FakeSessionCtx:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute_write(self, fn, query, params):
            return await fn(FakeTx(), query, params)

    class FakeDriver:
        def session(self, database):
            return FakeSessionCtx()

    class FakeAsyncGraphDatabase:
        @staticmethod
        def driver(uri, auth):
            return FakeDriver()

    monkeypatch.setattr(graph_mod, "AsyncGraphDatabase", FakeAsyncGraphDatabase)

    store = graph_mod.Neo4jMemoryGraphStore("bolt://neo4j:7687", "neo4j", "secret")
    await store.create_memory_edge(
        MemoryGraphEdge(
            org_id="org-1",
            source_memory_id="mem-a",
            target_memory_id="mem-b",
            edge_type="conflicts_with",
        )
    )

    query, params = executed[0]
    assert "ConflictCase" in query
    assert "PARTICIPATES_IN" in query
    assert "CONFLICTS_WITH" not in query
    assert params["source_memory_id"] == "mem-a"
    assert params["target_memory_id"] == "mem-b"


@pytest.mark.asyncio
async def test_neo4j_store_rejects_unknown_relationship_type(monkeypatch):
    from app.services import neo4j_memory_graph_store as graph_mod

    class FakeAsyncGraphDatabase:
        @staticmethod
        def driver(uri, auth):
            raise AssertionError("driver should not be used for invalid edge types")

    monkeypatch.setattr(graph_mod, "AsyncGraphDatabase", FakeAsyncGraphDatabase)
    store = object.__new__(graph_mod.Neo4jMemoryGraphStore)
    store._database = "neo4j"
    store._driver = None

    with pytest.raises(ValueError, match="Unsupported memory graph edge_type"):
        await store.create_memory_edge(
            MemoryGraphEdge(
                org_id="org-1",
                source_memory_id="mem-a",
                target_memory_id="mem-b",
                edge_type="not_allowed",
            )
        )


@pytest.mark.asyncio
async def test_neo4j_store_requires_explicit_org_id():
    from app.services import neo4j_memory_graph_store as graph_mod

    store = object.__new__(graph_mod.Neo4jMemoryGraphStore)
    store._database = "neo4j"
    store._driver = None

    with pytest.raises(GraphMemoryError, match="org_id is required"):
        await store.create_memory_edge(
            MemoryGraphEdge(
                org_id="",
                source_memory_id="mem-a",
                target_memory_id="mem-b",
                edge_type="derived_from",
            )
        )


@pytest.mark.asyncio
async def test_neo4j_schema_uses_org_scoped_unique_constraints(monkeypatch):
    from app.services import neo4j_memory_graph_store as graph_mod

    executed: list[str] = []

    class FakeSessionCtx:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def run(self, cypher):
            executed.append(cypher)

    class FakeDriver:
        def session(self, database):
            return FakeSessionCtx()

    class FakeAsyncGraphDatabase:
        @staticmethod
        def driver(uri, auth):
            return FakeDriver()

    monkeypatch.setattr(graph_mod, "AsyncGraphDatabase", FakeAsyncGraphDatabase)

    store = graph_mod.Neo4jMemoryGraphStore("bolt://neo4j:7687", "neo4j", "secret")
    await store.ensure_schema()

    assert any("REQUIRE (m.org_id, m.memory_id) IS UNIQUE" in cypher for cypher in executed)
    assert any("REQUIRE (c.org_id, c.chunk_id) IS UNIQUE" in cypher for cypher in executed)


def test_strict_graph_factory_rejects_mysql_backend(monkeypatch):
    from app.services import memory_graph_factory as factory_mod

    monkeypatch.setattr(factory_mod.settings, "memory_strict_sync", True)
    monkeypatch.setattr(factory_mod.settings, "memory_graph_write_backend", "mysql")
    monkeypatch.setattr(factory_mod.settings, "memory_graph_read_backend", "neo4j")
    monkeypatch.setattr(factory_mod.settings, "neo4j_enabled", True)

    with pytest.raises(GraphMemoryError, match="requires memory_graph_write_backend=neo4j"):
        factory_mod.build_memory_graph_store(FakeSession(), "org-1")
