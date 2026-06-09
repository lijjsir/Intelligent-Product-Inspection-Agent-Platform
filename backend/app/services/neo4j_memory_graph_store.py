"""Neo4jMemoryGraphStore — Neo4j-backed implementation of MemoryGraphStore."""
from __future__ import annotations

import logging
from typing import Any

from app.services.memory_graph_store import MemoryGraphEdge, MemoryGraphNode, MemoryGraphStore

try:
    from neo4j import GraphDatabase
except Exception:
    GraphDatabase = None

logger = logging.getLogger(__name__)


class Neo4jMemoryGraphStore(MemoryGraphStore):
    """Neo4j implementation for memory relationship graph."""

    def __init__(self, uri: str, username: str, password: str, database: str = "neo4j"):
        if GraphDatabase is None:
            raise RuntimeError("neo4j driver is not installed")
        self._database = database
        self._driver = GraphDatabase.driver(uri, auth=(username, password))

    async def upsert_memory_node(self, node: MemoryGraphNode) -> None:
        query = """
        MERGE (m:Memory {org_id: $org_id, memory_id: $memory_id})
        SET m.memory_type = $memory_type,
            m.status = $status,
            m.trust_score = $trust_score,
            m.confidence = $confidence,
            m.scope_key = $scope_key,
            m.updated_at = $updated_at
        """
        await self._execute(query, {
            "org_id": node.org_id,
            "memory_id": node.memory_id,
            "memory_type": node.memory_type,
            "status": node.status,
            "trust_score": node.trust_score,
            "confidence": node.confidence,
            "scope_key": node.scope_key,
            "updated_at": node.updated_at or "",
        })

    async def upsert_rag_chunk_node(self, org_id: str, chunk_id: str, rag_space_id: str = "",
                                     document_id: str = "", title: str = "", page_number: int = 0) -> None:
        query = """
        MERGE (c:RagChunk {org_id: $org_id, chunk_id: $chunk_id})
        SET c.rag_space_id = $rag_space_id,
            c.document_id = $document_id,
            c.title = $title,
            c.page_number = $page_number
        """
        await self._execute(query, {
            "org_id": org_id,
            "chunk_id": chunk_id,
            "rag_space_id": rag_space_id,
            "document_id": document_id,
            "title": title,
            "page_number": page_number,
        })

    async def create_memory_edge(self, edge: MemoryGraphEdge) -> None:
        query = """
        MATCH (src:Memory {org_id: $org_id, memory_id: $source_memory_id})
        MATCH (dst:Memory {org_id: $org_id, memory_id: $target_memory_id})
        MERGE (src)-[r:MEMORY_EDGE {edge_type: $edge_type}]->(dst)
        SET r.strength = $strength,
            r.trace_id = $trace_id,
            r.reason = $reason,
            r.updated_at = datetime()
        """
        org_id = (edge.metadata_json or {}).get("org_id", "") or ""
        await self._execute(query, {
            "org_id": org_id,
            "source_memory_id": edge.source_memory_id,
            "target_memory_id": edge.target_memory_id,
            "edge_type": edge.edge_type,
            "strength": edge.strength,
            "trace_id": edge.trace_id or "",
            "reason": edge.reason or "",
        })

    async def create_memory_rag_edge(self, memory_id: str, chunk_id: str, edge_type: str,
                                      confidence: float = 1.0, org_id: str = "") -> None:
        query = """
        MATCH (m:Memory {org_id: $org_id, memory_id: $memory_id})
        MATCH (c:RagChunk {org_id: $org_id, chunk_id: $chunk_id})
        MERGE (m)-[r:MEMORY_EDGE {edge_type: $edge_type}]->(c)
        SET r.confidence = $confidence,
            r.updated_at = datetime()
        """
        await self._execute(query, {
            "org_id": org_id,
            "memory_id": memory_id,
            "chunk_id": chunk_id,
            "edge_type": edge_type,
            "confidence": confidence,
        })

    async def build_propagation_graph(self, org_id: str, root_memory_id: str,
                                       edge_types: list[str] | None = None,
                                       max_depth: int = 4) -> list[dict]:
        if edge_types:
            query = f"""
            MATCH path = (root:Memory {{org_id: $org_id, memory_id: $root_memory_id}})
                         -[rels:MEMORY_EDGE*1..{int(max_depth)}]->
                         (target:Memory)
            WHERE ALL(r IN rels WHERE r.edge_type IN $edge_types)
            RETURN path
            LIMIT 500
            """
        else:
            query = f"""
            MATCH path = (root:Memory {{org_id: $org_id, memory_id: $root_memory_id}})
                         -[rels:MEMORY_EDGE*1..{int(max_depth)}]->
                         (target:Memory)
            RETURN path
            LIMIT 500
            """

        records = await self._execute_read(query, {
            "org_id": org_id,
            "root_memory_id": root_memory_id,
            "edge_types": edge_types or [],
        })
        return [dict(r) for r in records]

    async def trace_provenance(self, org_id: str, memory_id: str) -> list[dict]:
        query = """
        MATCH (m:Memory {org_id: $org_id, memory_id: $memory_id})
        OPTIONAL MATCH (m)-[r:MEMORY_EDGE]->(target)
        RETURN m, r, target
        LIMIT 200
        """
        records = await self._execute_read(query, {
            "org_id": org_id,
            "memory_id": memory_id,
        })
        return [dict(r) for r in records]

    async def find_conflict_chain(self, org_id: str, memory_id: str) -> list[dict]:
        query = """
        MATCH (m:Memory {org_id: $org_id, memory_id: $memory_id})
              -[r:MEMORY_EDGE {edge_type: 'conflicts_with'}]->
              (target)
        RETURN m.memory_id AS source_memory_id,
               target.memory_id AS target_memory_id,
               r.edge_type AS edge_type,
               r.strength AS strength
        LIMIT 200
        """
        records = await self._execute_read(query, {
            "org_id": org_id,
            "memory_id": memory_id,
        })
        return [dict(r) for r in records]

    async def create_event_memory_edge(self, org_id: str, event_id: str, memory_id: str,
                                        edge_type: str, trace_id: str = "") -> None:
        query = """
        MERGE (e:MemoryEvent {org_id: $org_id, event_id: $event_id})
        SET e.trace_id = $trace_id
        WITH e
        MATCH (m:Memory {org_id: $org_id, memory_id: $memory_id})
        MERGE (e)-[r:MEMORY_EDGE {edge_type: $edge_type}]->(m)
        SET r.updated_at = datetime()
        """
        await self._execute(query, {
            "org_id": org_id,
            "event_id": event_id,
            "memory_id": memory_id,
            "edge_type": edge_type,
            "trace_id": trace_id,
        })

    async def create_agent_memory_edge(self, org_id: str, trace_id: str, memory_id: str,
                                        edge_type: str, agent_id: str = "", task_id: str = "") -> None:
        query = """
        MERGE (a:AgentRun {org_id: $org_id, trace_id: $trace_id})
        SET a.agent_id = $agent_id,
            a.task_id = $task_id
        WITH a
        MATCH (m:Memory {org_id: $org_id, memory_id: $memory_id})
        MERGE (a)-[r:MEMORY_EDGE {edge_type: $edge_type}]->(m)
        SET r.updated_at = datetime()
        """
        await self._execute(query, {
            "org_id": org_id,
            "trace_id": trace_id,
            "memory_id": memory_id,
            "edge_type": edge_type,
            "agent_id": agent_id,
            "task_id": task_id,
        })

    async def health_check(self) -> bool:
        try:
            await self._execute("RETURN 1", {})
            return True
        except Exception:
            return False

    async def _execute(self, query: str, params: dict[str, Any]) -> None:
        def _run(tx, q, p):
            tx.run(q, p)

        async with self._driver.session(database=self._database) as session:
            await session.execute_write(_run, query, params)

    async def _execute_read(self, query: str, params: dict[str, Any]) -> list[Any]:
        def _run(tx, q, p):
            result = tx.run(q, p)
            return list(result)

        async with self._driver.session(database=self._database) as session:
            return await session.execute_read(_run, query, params)
