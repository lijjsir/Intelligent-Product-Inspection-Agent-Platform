"""MemoryGraphFactory — creates the appropriate MemoryGraphStore backend."""
from __future__ import annotations

import logging

from app.core.config import settings
from app.errors.memory_errors import GraphMemoryError
from app.services.memory_graph_store import MemoryGraphStore, MySQLMemoryGraphStore

logger = logging.getLogger(__name__)


class DualWriteMemoryGraphStore(MemoryGraphStore):
    """Writes to both MySQL and Neo4j, reads from the configured read backend."""

    def __init__(self, mysql_store: MySQLMemoryGraphStore, neo4j_store: MemoryGraphStore,
                 read_backend: str = "mysql"):
        self._mysql = mysql_store
        self._neo4j = neo4j_store
        self._read_backend = read_backend

    @property
    def _reader(self) -> MemoryGraphStore:
        return self._neo4j if self._read_backend == "neo4j" else self._mysql

    async def upsert_memory_node(self, node):
        await self._mysql.upsert_memory_node(node)
        await self._neo4j.upsert_memory_node(node)

    async def upsert_rag_chunk_node(self, *args, **kwargs):
        await self._neo4j.upsert_rag_chunk_node(*args, **kwargs)

    async def create_memory_edge(self, edge):
        await self._mysql.create_memory_edge(edge)
        await self._neo4j.create_memory_edge(edge)

    async def create_memory_rag_edge(self, *args, **kwargs):
        await self._neo4j.create_memory_rag_edge(*args, **kwargs)

    async def build_propagation_graph(self, *args, **kwargs):
        return await self._reader.build_propagation_graph(*args, **kwargs)

    async def trace_provenance(self, *args, **kwargs):
        return await self._reader.trace_provenance(*args, **kwargs)

    async def find_conflict_chain(self, *args, **kwargs):
        return await self._reader.find_conflict_chain(*args, **kwargs)

    async def create_event_memory_edge(self, *args, **kwargs):
        await self._neo4j.create_event_memory_edge(*args, **kwargs)

    async def create_agent_memory_edge(self, *args, **kwargs):
        await self._neo4j.create_agent_memory_edge(*args, **kwargs)

    async def health_check(self) -> bool:
        return await self._neo4j.health_check()

    async def list_downstream_memories(self, *args, **kwargs):
        return await self._reader.list_downstream_memories(*args, **kwargs)

    async def list_upstream_memories(self, *args, **kwargs):
        return await self._reader.list_upstream_memories(*args, **kwargs)

    async def list_conflict_edges(self, *args, **kwargs):
        return await self._reader.list_conflict_edges(*args, **kwargs)

    async def soft_delete_memory_edges(self, *args, **kwargs):
        mysql_result = await self._mysql.soft_delete_memory_edges(*args, **kwargs)
        neo4j_result = await self._neo4j.soft_delete_memory_edges(*args, **kwargs)
        return neo4j_result

    async def mark_conflict_resolved(self, *args, **kwargs):
        await self._reader.mark_conflict_resolved(*args, **kwargs)


def build_memory_graph_store(session, org_id: str) -> MemoryGraphStore:
    """Factory: research memory graph requires Neo4j only."""
    write_backend = settings.memory_graph_write_backend
    read_backend = settings.memory_graph_read_backend

    if not settings.neo4j_enabled:
        raise GraphMemoryError(
            "Research memory graph requires neo4j_enabled=True.",
            code="NEO4J_REQUIRED_DISABLED",
            detail={"neo4j_enabled": settings.neo4j_enabled},
        )
    if write_backend != "neo4j":
        raise GraphMemoryError(
            "Research memory graph requires memory_graph_write_backend=neo4j.",
            code="GRAPH_MEMORY_BACKEND_INVALID",
            detail={"write_backend": write_backend, "read_backend": read_backend},
        )
    if read_backend != "neo4j":
        raise GraphMemoryError(
            "Research memory graph requires memory_graph_read_backend=neo4j.",
            code="GRAPH_MEMORY_BACKEND_INVALID",
            detail={"write_backend": write_backend, "read_backend": read_backend},
        )

    from app.services.neo4j_memory_graph_store import Neo4jMemoryGraphStore

    return Neo4jMemoryGraphStore(
        uri=settings.neo4j_uri,
        username=settings.neo4j_username,
        password=settings.neo4j_password,
        database=settings.neo4j_database,
    )
