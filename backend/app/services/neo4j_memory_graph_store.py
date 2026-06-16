"""Neo4jMemoryGraphStore — Neo4j-backed implementation of MemoryGraphStore."""
from __future__ import annotations

import json
import logging
from typing import Any

from app.errors.memory_errors import GraphMemoryError
from app.services.memory_graph_store import MemoryGraphEdge, MemoryGraphNode, MemoryGraphStore

try:
    from neo4j import AsyncGraphDatabase
except Exception:
    AsyncGraphDatabase = None

logger = logging.getLogger(__name__)

MEMORY_RELATIONSHIP_TYPES = {
    "version_of": "VERSION_OF",
    "derived_from": "DERIVED_FROM",
    "summarized_from": "SUMMARIZED_FROM",
    "cited_as_evidence": "CITED_AS_EVIDENCE",
    "merged_from": "MERGED_FROM",
    "conflicts_with": "CONFLICTS_WITH",
    "planned_from": "PLANNED_FROM",
    "rollback_depends_on": "ROLLBACK_DEPENDS_ON",
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
        if str(edge.edge_type or "").lower() == "conflicts_with":
            conflict_id = str((edge.metadata_json or {}).get("conflict_id") or f"{edge.source_memory_id}:{edge.target_memory_id}")
            await self.create_conflict_case(
                org_id=edge.org_id,
                conflict_id=conflict_id,
                source_memory_id=edge.source_memory_id,
                target_memory_id=edge.target_memory_id,
                conflict_type=str((edge.metadata_json or {}).get("conflict_type") or "memory_contradiction"),
                severity=str((edge.metadata_json or {}).get("severity") or "medium"),
                reason=edge.reason or "",
                metadata_json=edge.metadata_json or {},
            )
            return
        org_id = str(edge.org_id or "").strip()
        if not org_id:
            raise GraphMemoryError(
                "org_id is required for memory graph edge writes.",
                code="GRAPH_MEMORY_EDGE_ORG_REQUIRED",
                detail={
                    "source_memory_id": edge.source_memory_id,
                    "target_memory_id": edge.target_memory_id,
                    "edge_type": edge.edge_type,
                },
            )
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
            r.created_at = coalesce(r.created_at, $created_at),
            r.updated_at = datetime()
        """
        await self._execute(query, {
            "org_id": org_id,
            "source_memory_id": edge.source_memory_id,
            "target_memory_id": edge.target_memory_id,
            "edge_type": edge.edge_type,
            "strength": edge.strength,
            "trace_id": edge.trace_id or "",
            "reason": edge.reason or "",
            "metadata_json": self._json_dumps(edge.metadata_json or {}),
            "created_at": edge.created_at or "",
        })

    async def create_conflict_case(
        self,
        *,
        org_id: str,
        conflict_id: str,
        source_memory_id: str,
        target_memory_id: str,
        conflict_type: str,
        severity: str = "medium",
        reason: str = "",
        metadata_json: dict | None = None,
    ) -> None:
        query = """
        MERGE (case:ConflictCase {org_id: $org_id, conflict_id: $conflict_id})
        SET case.conflict_type = $conflict_type,
            case.severity = $severity,
            case.status = coalesce(case.status, 'open'),
            case.reason = $reason,
            case.metadata_json = $metadata_json,
            case.updated_at = datetime(),
            case.created_at = coalesce(case.created_at, datetime())
        WITH case
        MERGE (a:Memory {org_id: $org_id, memory_id: $source_memory_id})
        MERGE (b:Memory {org_id: $org_id, memory_id: $target_memory_id})
        MERGE (a)-[:PARTICIPATES_IN {org_id: $org_id, conflict_id: $conflict_id}]->(case)
        MERGE (b)-[:PARTICIPATES_IN {org_id: $org_id, conflict_id: $conflict_id}]->(case)
        """
        await self._execute(query, {
            "org_id": org_id,
            "conflict_id": conflict_id,
            "source_memory_id": source_memory_id,
            "target_memory_id": target_memory_id,
            "conflict_type": conflict_type,
            "severity": severity,
            "reason": reason,
            "metadata_json": self._json_dumps(metadata_json or {}),
        })

    async def upsert_domain_context(self, *, org_id: str, memory_id: str, scope: dict[str, Any]) -> None:
        query = """
        MATCH (m:Memory {org_id: $org_id, memory_id: $memory_id})
        FOREACH (_ IN CASE WHEN $product_line <> '' THEN [1] ELSE [] END |
          MERGE (p:ProductLine {org_id: $org_id, product_line_key: $product_line})
          MERGE (m)-[:APPLIES_TO {org_id: $org_id}]->(p)
        )
        FOREACH (_ IN CASE WHEN $standard_version_key <> '' THEN [1] ELSE [] END |
          MERGE (s:StandardVersion {org_id: $org_id, standard_version_key: $standard_version_key})
          SET s.standard_code = $standard_code, s.standard_version = $standard_version
          MERGE (m)-[:BASED_ON {org_id: $org_id}]->(s)
        )
        FOREACH (_ IN CASE WHEN $task_id <> '' THEN [1] ELSE [] END |
          MERGE (t:InspectionTask {org_id: $org_id, task_id: $task_id})
          MERGE (m)-[:OBSERVED_IN {org_id: $org_id}]->(t)
        )
        FOREACH (_ IN CASE WHEN $target_market <> '' THEN [1] ELSE [] END |
          MERGE (market:Market {org_id: $org_id, market_key: $target_market})
          MERGE (m)-[:TARGET_MARKET {org_id: $org_id}]->(market)
        )
        FOREACH (_ IN CASE WHEN $product_category <> '' THEN [1] ELSE [] END |
          MERGE (product:Product {org_id: $org_id, product_key: $product_category})
          MERGE (m)-[:FOR_PRODUCT {org_id: $org_id}]->(product)
        )
        FOREACH (_ IN CASE WHEN $defect_type <> '' THEN [1] ELSE [] END |
          MERGE (defect:DefectType {org_id: $org_id, defect_type_key: $defect_type})
          MERGE (m)-[:MENTIONS_DEFECT {org_id: $org_id}]->(defect)
        )
        FOREACH (_ IN CASE WHEN $inspection_batch_id <> '' THEN [1] ELSE [] END |
          MERGE (batch:InspectionBatch {org_id: $org_id, inspection_batch_id: $inspection_batch_id})
          MERGE (m)-[:OBSERVED_IN_BATCH {org_id: $org_id}]->(batch)
        )
        """
        standard_code = str(scope.get("standard_code") or "")
        standard_version = str(scope.get("standard_version") or "")
        await self._execute(query, {
            "org_id": org_id,
            "memory_id": memory_id,
            "product_line": str(scope.get("product_line") or ""),
            "standard_code": standard_code,
            "standard_version": standard_version,
            "standard_version_key": f"{standard_code}:{standard_version}" if (standard_code or standard_version) else "",
            "task_id": str(scope.get("task_id") or ""),
            "target_market": str(scope.get("target_market") or ""),
            "product_category": str(scope.get("product_category") or ""),
            "defect_type": str(scope.get("defect_type") or ""),
            "inspection_batch_id": str(scope.get("inspection_batch_id") or ""),
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

    async def list_downstream_memories(
        self, *, org_id: str, root_memory_id: str,
        edge_types: list[str], max_depth: int,
    ) -> list[dict]:
        query = """
        MATCH path = (root:Memory {org_id: $org_id, memory_id: $root_memory_id})
                     <-[rels*1..$max_depth]-
                     (downstream:Memory {org_id: $org_id})
        WHERE ALL(r IN rels WHERE r.edge_type IN $edge_types AND coalesce(r.deleted_at, '') = '')
        RETURN
          downstream.memory_id AS memory_id,
          length(path) AS depth,
          [r IN rels | r.edge_type] AS edge_types,
          [r IN rels | coalesce(r.strength, 1.0)] AS strengths,
          [n IN nodes(path) | n.memory_id] AS path_memory_ids
        ORDER BY depth ASC
        LIMIT 500
        """
        records = await self._execute_read(query, {
            "org_id": org_id,
            "root_memory_id": root_memory_id,
            "edge_types": edge_types,
            "max_depth": max_depth,
        })
        return [dict(r) for r in records]

    async def list_upstream_memories(
        self, *, org_id: str, memory_id: str,
        edge_types: list[str] | None = None, max_depth: int = 4,
    ) -> list[dict]:
        et = edge_types or list(MEMORY_RELATIONSHIP_TYPES.keys())
        query = """
        MATCH path = (m:Memory {org_id: $org_id, memory_id: $memory_id})
                     -[rels*1..$max_depth]->
                     (upstream:Memory {org_id: $org_id})
        WHERE ALL(r IN rels WHERE r.edge_type IN $edge_types AND coalesce(r.deleted_at, '') = '')
        RETURN
          upstream.memory_id AS memory_id,
          length(path) AS depth,
          [r IN rels | r.edge_type] AS edge_types,
          [n IN nodes(path) | n.memory_id] AS path_memory_ids
        ORDER BY depth ASC
        LIMIT 500
        """
        records = await self._execute_read(query, {
            "org_id": org_id,
            "memory_id": memory_id,
            "edge_types": et,
            "max_depth": max_depth,
        })
        return [dict(r) for r in records]

    async def list_conflict_edges(
        self, *, org_id: str, memory_id: str | None = None,
        include_resolved: bool = False,
    ) -> list[dict]:
        resolved_filter = "" if include_resolved else "AND coalesce(r.resolved, false) = false"
        mem_filter = ""
        params: dict = {"org_id": org_id}
        if memory_id:
            mem_filter = "AND (a.memory_id = $memory_id OR b.memory_id = $memory_id)"
            params["memory_id"] = memory_id
        query = f"""
        MATCH (a:Memory {{org_id: $org_id}})-[r:CONFLICTS_WITH]->(b:Memory {{org_id: $org_id}})
        WHERE 1=1 {mem_filter} {resolved_filter}
        RETURN
          a.memory_id AS source_memory_id,
          b.memory_id AS target_memory_id,
          r.strength AS strength,
          r.reason AS reason,
          r.metadata_json AS metadata_json,
          r.created_at AS created_at
        ORDER BY r.created_at DESC
        LIMIT 500
        """
        records = await self._execute_read(query, params)
        return [dict(r) for r in records]

    async def soft_delete_memory_edges(
        self, *, org_id: str, memory_id: str,
        edge_types: list[str] | None = None,
    ) -> int:
        et_filter = "AND r.edge_type IN $edge_types" if edge_types else ""
        query = f"""
        MATCH (m:Memory {{org_id: $org_id, memory_id: $memory_id}})-[r]-(:Memory)
        WHERE 1=1 {et_filter}
        SET r.deleted_at = datetime()
        RETURN count(r) AS deleted_count
        """
        records = await self._execute_read(query, {
            "org_id": org_id,
            "memory_id": memory_id,
            "edge_types": edge_types or [],
        })
        return records[0]["deleted_count"] if records else 0

    async def mark_conflict_resolved(
        self, *, org_id: str, source_memory_id: str,
        target_memory_id: str, resolution: str, resolved_by: str,
    ) -> None:
        query = """
        MATCH (a:Memory {org_id: $org_id, memory_id: $source_memory_id})
              -[r:CONFLICTS_WITH]-
              (b:Memory {org_id: $org_id, memory_id: $target_memory_id})
        SET r.resolved = true,
            r.resolution = $resolution,
            r.resolved_by = $resolved_by,
            r.resolved_at = datetime()
        """
        await self._execute(query, {
            "org_id": org_id,
            "source_memory_id": source_memory_id,
            "target_memory_id": target_memory_id,
            "resolution": resolution,
            "resolved_by": resolved_by,
        })

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

    async def verify_connectivity(self) -> None:
        """Strict connectivity check. Raises if Neo4j is unreachable."""
        async with self._driver.session(database=self._database) as session:
            result = await session.run("RETURN 1 AS ok")
            record = await result.single()
            if not record or record["ok"] != 1:
                raise RuntimeError("Neo4j returned invalid health check result")

    async def ensure_schema(self) -> None:
        """Create unique constraints and indexes for all node types."""
        cyphers = [
            "CREATE CONSTRAINT memory_org_memory_id_unique IF NOT EXISTS FOR (m:Memory) REQUIRE (m.org_id, m.memory_id) IS UNIQUE",
            "CREATE INDEX memory_org_id_idx IF NOT EXISTS FOR (m:Memory) ON (m.org_id)",
            "CREATE INDEX memory_status_idx IF NOT EXISTS FOR (m:Memory) ON (m.status)",
            "CREATE INDEX memory_type_idx IF NOT EXISTS FOR (m:Memory) ON (m.memory_type)",
            "CREATE CONSTRAINT rag_chunk_org_chunk_id_unique IF NOT EXISTS FOR (c:RagChunk) REQUIRE (c.org_id, c.chunk_id) IS UNIQUE",
            "CREATE CONSTRAINT agent_run_org_trace_id_unique IF NOT EXISTS FOR (a:AgentRun) REQUIRE (a.org_id, a.trace_id) IS UNIQUE",
            "CREATE CONSTRAINT memory_event_org_event_id_unique IF NOT EXISTS FOR (e:MemoryEvent) REQUIRE (e.org_id, e.event_id) IS UNIQUE",
            "CREATE CONSTRAINT task_org_task_id_unique IF NOT EXISTS FOR (t:Task) REQUIRE (t.org_id, t.task_id) IS UNIQUE",
            "CREATE CONSTRAINT product_line_org_key_unique IF NOT EXISTS FOR (p:ProductLine) REQUIRE (p.org_id, p.product_line_key) IS UNIQUE",
            "CREATE CONSTRAINT standard_version_org_key_unique IF NOT EXISTS FOR (s:StandardVersion) REQUIRE (s.org_id, s.standard_version_key) IS UNIQUE",
            "CREATE CONSTRAINT inspection_task_org_key_unique IF NOT EXISTS FOR (t:InspectionTask) REQUIRE (t.org_id, t.task_id) IS UNIQUE",
            "CREATE CONSTRAINT inspection_batch_org_key_unique IF NOT EXISTS FOR (b:InspectionBatch) REQUIRE (b.org_id, b.inspection_batch_id) IS UNIQUE",
            "CREATE CONSTRAINT product_org_key_unique IF NOT EXISTS FOR (p:Product) REQUIRE (p.org_id, p.product_key) IS UNIQUE",
            "CREATE CONSTRAINT market_org_key_unique IF NOT EXISTS FOR (m:Market) REQUIRE (m.org_id, m.market_key) IS UNIQUE",
            "CREATE CONSTRAINT defect_type_org_key_unique IF NOT EXISTS FOR (d:DefectType) REQUIRE (d.org_id, d.defect_type_key) IS UNIQUE",
            "CREATE CONSTRAINT conflict_case_org_key_unique IF NOT EXISTS FOR (c:ConflictCase) REQUIRE (c.org_id, c.conflict_id) IS UNIQUE",
            "CREATE INDEX conflict_case_status_idx IF NOT EXISTS FOR (c:ConflictCase) ON (c.org_id, c.status)",
        ]

        async with self._driver.session(database=self._database) as session:
            for cypher in cyphers:
                await session.run(cypher)

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
