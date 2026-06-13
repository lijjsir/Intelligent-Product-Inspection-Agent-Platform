"""Neo4jMemoryGraphStore — Neo4j-backed implementation of MemoryGraphStore."""
from __future__ import annotations

import json
import logging
from typing import Any

from app.services.memory_graph_store import MemoryGraphEdge, MemoryGraphNode, MemoryGraphStore

try:
    from neo4j import AsyncGraphDatabase
except Exception:
    AsyncGraphDatabase = None

logger = logging.getLogger(__name__)

MEMORY_RELATIONSHIP_TYPES = {
    "version_of": "VERSION_OF",
    "derived_from": "DERIVED_FROM",
    "cited_as_evidence": "CITED_AS_EVIDENCE",
    "merged_from": "MERGED_FROM",
    "conflicts_with": "CONFLICTS_WITH",
}


class Neo4jMemoryGraphStore(MemoryGraphStore):
    """Neo4j implementation for memory relationship graph."""

    def __init__(self, uri: str, username: str, password: str, database: str = "neo4j"):
        if AsyncGraphDatabase is None:
            raise RuntimeError("neo4j driver is not installed")
        self._database = database
        self._driver = AsyncGraphDatabase.driver(uri, auth=(username, password))

    async def upsert_memory_node(self, node: MemoryGraphNode) -> None:
        query = """
        MERGE (m:Memory {org_id: $org_id, memory_id: $memory_id})
        SET m.memory_type = $memory_type,
            m.status = $status,
            m.trust_score = $trust_score,
            m.confidence = $confidence,
            m.scope_key = $scope_key,
            m.created_at = coalesce(m.created_at, $created_at),
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
            "created_at": node.created_at or "",
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
        relationship_type = self._memory_relationship_type(edge.edge_type)
        query = f"""
        MERGE (src:Memory {{org_id: $org_id, memory_id: $source_memory_id}})
        MERGE (dst:Memory {{org_id: $org_id, memory_id: $target_memory_id}})
        MERGE (src)-[r:{relationship_type} {{
            org_id: $org_id,
            edge_type: $edge_type,
            source_memory_id: $source_memory_id,
            target_memory_id: $target_memory_id
        }}]->(dst)
        SET r.strength = $strength,
            r.trace_id = $trace_id,
            r.reason = $reason,
            r.metadata_json = $metadata_json,
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
            "metadata_json": self._json_dumps(edge.metadata_json or {}),
        })

    async def create_memory_rag_edge(self, memory_id: str, chunk_id: str, edge_type: str,
                                      confidence: float = 1.0, org_id: str = "") -> None:
        query = """
        MERGE (m:Memory {org_id: $org_id, memory_id: $memory_id})
        MERGE (c:RagChunk {org_id: $org_id, chunk_id: $chunk_id})
        MERGE (m)-[r:MEMORY_EDGE {
            org_id: $org_id,
            edge_type: $edge_type,
            source_memory_id: $memory_id,
            target_memory_id: $chunk_id
        }]->(c)
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
        relationship_pattern = self._relationship_pattern(edge_types)
        if edge_types:
            query = f"""
            MATCH path = (root:Memory {{org_id: $org_id, memory_id: $root_memory_id}})
                         <-[rels:{relationship_pattern}*1..{int(max_depth)}]-
                         (target:Memory)
            WHERE ALL(r IN rels WHERE r.edge_type IN $edge_types)
            RETURN path
            LIMIT 500
            """
        else:
            query = f"""
            MATCH path = (root:Memory {{org_id: $org_id, memory_id: $root_memory_id}})
                         <-[rels:{relationship_pattern}*1..{int(max_depth)}]-
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
        OPTIONAL MATCH (m)-[r]->(target)
        WHERE type(r) IN $relationship_types
        RETURN m, r, target
        LIMIT 200
        """
        records = await self._execute_read(query, {
            "org_id": org_id,
            "memory_id": memory_id,
            "relationship_types": list(MEMORY_RELATIONSHIP_TYPES.values()),
        })
        return [dict(r) for r in records]

    async def find_conflict_chain(self, org_id: str, memory_id: str) -> list[dict]:
        query = """
        MATCH (m:Memory {org_id: $org_id, memory_id: $memory_id})
              -[r:CONFLICTS_WITH {edge_type: 'conflicts_with'}]->
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
        MERGE (m:Memory {org_id: $org_id, memory_id: $memory_id})
        MERGE (e)-[r:MEMORY_EDGE {
            org_id: $org_id,
            edge_type: $edge_type,
            source_memory_id: $event_id,
            target_memory_id: $memory_id
        }]->(m)
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
        MERGE (m:Memory {org_id: $org_id, memory_id: $memory_id})
        MERGE (a)-[r:MEMORY_EDGE {
            org_id: $org_id,
            edge_type: $edge_type,
            source_memory_id: $trace_id,
            target_memory_id: $memory_id
        }]->(m)
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
        async def _run(tx, q, p):
            result = await tx.run(q, p)
            await result.consume()

        async with self._driver.session(database=self._database) as session:
            await session.execute_write(_run, query, params)

    async def _execute_read(self, query: str, params: dict[str, Any]) -> list[Any]:
        async def _run(tx, q, p):
            result = await tx.run(q, p)
            return [record async for record in result]

        async with self._driver.session(database=self._database) as session:
            return await session.execute_read(_run, query, params)

    @staticmethod
    def _json_dumps(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _memory_relationship_type(edge_type: str) -> str:
        relationship_type = MEMORY_RELATIONSHIP_TYPES.get(str(edge_type or "").strip().lower())
        if not relationship_type:
            raise ValueError(f"Unsupported memory graph edge_type: {edge_type}")
        return relationship_type

    @classmethod
    def _relationship_pattern(cls, edge_types: list[str] | None) -> str:
        requested = edge_types or list(MEMORY_RELATIONSHIP_TYPES.keys())
        relationship_types = [cls._memory_relationship_type(edge_type) for edge_type in requested]
        return "|".join(dict.fromkeys(relationship_types))
