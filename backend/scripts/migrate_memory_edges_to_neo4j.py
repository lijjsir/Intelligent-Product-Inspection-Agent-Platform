"""Migrate existing memory_dependency_edges from MySQL to Neo4j.

Run: cd backend && PYTHONPATH=. python scripts/migrate_memory_edges_to_neo4j.py --org-id ORG_ID [--batch-size 1000] [--verify]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def migrate(org_id: str, batch_size: int = 1000, verify: bool = False):
    from sqlalchemy import text
    from infra.database.session import get_session
    from app.repositories.memory_repo import MemoryDependencyRepository
    from app.services.memory_graph_factory import build_memory_graph_store
    from app.services.memory_graph_store import MemoryGraphEdge

    async with get_session() as session:
        dep_repo = MemoryDependencyRepository(session, org_id)
        graph = build_memory_graph_store(session, org_id)

        edges = await dep_repo.list_all(org_id=org_id)

        migrated = 0
        errors = 0
        for row in edges:
            try:
                edge = MemoryGraphEdge(
                    org_id=org_id,
                    source_memory_id=row.source_memory_id,
                    target_memory_id=row.target_memory_id,
                    edge_type=row.edge_type,
                    strength=float(row.strength) if row.strength else 1.0,
                    trace_id=getattr(row, "trace_id", None),
                    reason=getattr(row, "reason", None),
                    metadata_json=dict(row.metadata_json or {}),
                    created_at=row.created_at.isoformat() if getattr(row, "created_at", None) else "",
                )
                await graph.create_memory_edge(edge)
                migrated += 1
            except Exception as exc:
                logger.warning("Failed to migrate edge %s->%s: %s", row.source_memory_id, row.target_memory_id, exc)
                errors += 1

        logger.info("Migration complete: migrated=%d errors=%d total=%d", migrated, errors, len(edges))

        if verify:
            logger.info("Verifying migration...")
            mysql_count = len(edges)
            logger.info("MySQL edges: %d", mysql_count)
            logger.info("Verification: sample the first 10 edges in Neo4j...")
            # Sample verification
            for row in edges[:10]:
                downstream = await graph.list_downstream_memories(
                    org_id=org_id,
                    root_memory_id=row.target_memory_id,
                    edge_types=[row.edge_type],
                    max_depth=1,
                )
                found = any(e.get("memory_id") == row.source_memory_id for e in downstream)
                status = "OK" if found else "MISSING"
                logger.info("Verify %s-[%s]->%s: %s", row.source_memory_id, row.edge_type, row.target_memory_id, status)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--org-id", type=str, required=True, help="Organization ID to migrate")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--verify", action="store_true", help="Run verification after migration")
    args = parser.parse_args()
    asyncio.run(migrate(org_id=args.org_id, batch_size=args.batch_size, verify=args.verify))
