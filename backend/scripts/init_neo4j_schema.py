"""Initialize Neo4j constraints and indexes for the memory graph.

Run: cd backend && PYTHONPATH=. python scripts/init_neo4j_schema.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import settings


def init_schema():
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_username, settings.neo4j_password),
    )

    constraints = [
        "CREATE CONSTRAINT memory_unique IF NOT EXISTS FOR (m:Memory) REQUIRE (m.org_id, m.memory_id) IS UNIQUE",
        "CREATE INDEX memory_status IF NOT EXISTS FOR (m:Memory) ON (m.org_id, m.status)",
        "CREATE INDEX memory_type IF NOT EXISTS FOR (m:Memory) ON (m.org_id, m.memory_type)",
        "CREATE INDEX memory_scope IF NOT EXISTS FOR (m:Memory) ON (m.org_id, m.scope_key)",
        "CREATE CONSTRAINT rag_chunk_unique IF NOT EXISTS FOR (c:RagChunk) REQUIRE (c.org_id, c.chunk_id) IS UNIQUE",
        "CREATE CONSTRAINT agent_run_unique IF NOT EXISTS FOR (a:AgentRun) REQUIRE (a.org_id, a.trace_id) IS UNIQUE",
        "CREATE CONSTRAINT memory_event_unique IF NOT EXISTS FOR (e:MemoryEvent) REQUIRE (e.org_id, e.event_id) IS UNIQUE",
        "CREATE INDEX memory_rel_version_of IF NOT EXISTS FOR ()-[r:VERSION_OF]-() ON (r.org_id, r.source_memory_id, r.target_memory_id)",
        "CREATE INDEX memory_rel_derived_from IF NOT EXISTS FOR ()-[r:DERIVED_FROM]-() ON (r.org_id, r.source_memory_id, r.target_memory_id)",
        "CREATE INDEX memory_rel_cited_as_evidence IF NOT EXISTS FOR ()-[r:CITED_AS_EVIDENCE]-() ON (r.org_id, r.source_memory_id, r.target_memory_id)",
        "CREATE INDEX memory_rel_merged_from IF NOT EXISTS FOR ()-[r:MERGED_FROM]-() ON (r.org_id, r.source_memory_id, r.target_memory_id)",
        "CREATE INDEX memory_rel_conflicts_with IF NOT EXISTS FOR ()-[r:CONFLICTS_WITH]-() ON (r.org_id, r.source_memory_id, r.target_memory_id)",
    ]

    with driver.session(database=settings.neo4j_database) as session:
        for stmt in constraints:
            try:
                session.run(stmt)
                print(f"OK: {stmt[:80]}...")
            except Exception as exc:
                print(f"SKIP: {stmt[:80]}... ({exc})")

    driver.close()
    print("Neo4j schema initialization complete.")


if __name__ == "__main__":
    init_schema()
