"""Initialize Neo4j constraints and indexes for the memory graph.

Run: cd backend && PYTHONPATH=. python scripts/init_neo4j_schema.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import settings
from app.services.quality_kg_schema import NODE_TYPES, QKG_NODE_LABELS


def to_snake(value: str) -> str:
    chars: list[str] = []
    for index, char in enumerate(value):
        if char.isupper() and index > 0:
            chars.append("_")
        chars.append(char.lower())
    return "".join(chars)


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
        "CREATE INDEX memory_rel_version_of IF NOT EXISTS FOR ()-[r:VERSION_OF]-() ON (r.org_id, r.source_memory_id, r.target_memory_id)",
        "CREATE INDEX memory_rel_derived_from IF NOT EXISTS FOR ()-[r:DERIVED_FROM]-() ON (r.org_id, r.source_memory_id, r.target_memory_id)",
        "CREATE INDEX memory_rel_cited_as_evidence IF NOT EXISTS FOR ()-[r:CITED_AS_EVIDENCE]-() ON (r.org_id, r.source_memory_id, r.target_memory_id)",
        "CREATE INDEX memory_rel_merged_from IF NOT EXISTS FOR ()-[r:MERGED_FROM]-() ON (r.org_id, r.source_memory_id, r.target_memory_id)",
        "CREATE INDEX memory_rel_conflicts_with IF NOT EXISTS FOR ()-[r:CONFLICTS_WITH]-() ON (r.org_id, r.source_memory_id, r.target_memory_id)",
        "CREATE INDEX memory_rel_participates_in IF NOT EXISTS FOR ()-[r:PARTICIPATES_IN]-() ON (r.org_id, r.conflict_id, r.memory_id)",
        *[
            f"CREATE CONSTRAINT {to_snake(QKG_NODE_LABELS[node_type])}_id IF NOT EXISTS "
            f"FOR (n:{QKG_NODE_LABELS[node_type]}) REQUIRE n.id IS UNIQUE"
            for node_type in NODE_TYPES
        ],
        "CREATE INDEX qkg_product_category_name IF NOT EXISTS FOR (n:QkgProductCategory) ON (n.name)",
        "CREATE INDEX qkg_metric_name IF NOT EXISTS FOR (n:QkgMetric) ON (n.name)",
        "CREATE INDEX qkg_defect_type_name IF NOT EXISTS FOR (n:QkgDefectType) ON (n.name)",
        "CREATE INDEX qkg_action_name IF NOT EXISTS FOR (n:QkgAction) ON (n.name)",
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
