"""Migrate existing memory_dependency_edges from MySQL to Neo4j.

Run: cd backend && PYTHONPATH=. python scripts/migrate_memory_edges_to_neo4j.py [--batch-size 1000]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def migrate(batch_size: int = 1000):
    from neo4j import GraphDatabase
    from sqlalchemy import text
    from infra.database.session import get_session

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_username, settings.neo4j_password),
    )

    total_migrated = 0
    offset = 0

    while True:
        async with get_session() as session:
            result = await session.execute(
                text("""
                    SELECT org_id, source_memory_id, target_memory_id, edge_type,
                           strength, source_event_id, target_event_id,
                           scope_json, metadata_json, deleted_at
                    FROM memory_dependency_edges
                    WHERE deleted_at IS NULL
                    ORDER BY created_at
                    LIMIT :limit OFFSET :offset
                """),
                {"limit": batch_size, "offset": offset},
            )
            rows = result.fetchall()

        if not rows:
            break

        batch = []
        for row in rows:
            batch.append({
                "org_id": row.org_id,
                "source_memory_id": row.source_memory_id,
                "target_memory_id": row.target_memory_id,
                "edge_type": row.edge_type,
                "strength": float(row.strength) if row.strength else 1.0,
                "source_event_id": row.source_event_id,
                "target_event_id": row.target_event_id,
                "scope_json": row.scope_json,
                "metadata_json": row.metadata_json,
                "deleted_at": str(row.deleted_at) if row.deleted_at else None,
            })

        cypher = """
        UNWIND $edges AS edge
        MERGE (src:Memory {org_id: edge.org_id, memory_id: edge.source_memory_id})
        MERGE (dst:Memory {org_id: edge.org_id, memory_id: edge.target_memory_id})
        MERGE (src)-[r:MEMORY_EDGE {edge_type: edge.edge_type}]->(dst)
        SET r.strength = edge.strength,
            r.source_event_id = edge.source_event_id,
            r.target_event_id = edge.target_event_id,
            r.scope_json = edge.scope_json,
            r.metadata_json = edge.metadata_json,
            r.deleted_at = edge.deleted_at,
            r.updated_at = datetime()
        """

        with driver.session(database=settings.neo4j_database) as neo_session:
            neo_session.run(cypher, {"edges": batch})

        total_migrated += len(rows)
        offset += batch_size
        logger.info("Migrated %d edges (total: %d)", len(rows), total_migrated)

    driver.close()
    logger.info("Migration complete. Total edges: %d", total_migrated)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args()
    asyncio.run(migrate(batch_size=args.batch_size))
