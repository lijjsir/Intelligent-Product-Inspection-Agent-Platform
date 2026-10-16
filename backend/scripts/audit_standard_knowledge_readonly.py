"""Read-only metadata inventory for the standard/knowledge P0 migration.

No document body, user name, password, URL or token is exported. This script
uses SELECT/metadata inspection only and does not reindex or modify resources.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, select, text

from app.core.config import settings
from app.models.inspection_spec import InspectionSpec, InspectionSpecItem
from app.models.inspection_standard_library import InspectionStandardLibrary, StandardDocument, StandardDocumentChunk
from app.models.quality_risk import StandardExecutionRule
from app.models.rag_space import RagDocument, RagSpace
from infra.database.session import get_session, reset_async_engine_pool


async def audit(session) -> dict:
    connection = await session.connection()
    present = set(await connection.run_sync(lambda conn: inspect(conn).get_table_names()))
    models = [InspectionStandardLibrary, StandardDocument, StandardDocumentChunk,
              InspectionSpec, InspectionSpecItem, StandardExecutionRule, RagSpace, RagDocument]
    missing = [model.__tablename__ for model in models if model.__tablename__ not in present]
    if missing:
        return {"status": "incomplete", "missing_tables": missing}

    async def rows(model):
        stmt = select(model)
        if hasattr(model, "deleted_at"):
            stmt = stmt.where(model.deleted_at.is_(None))
        return list(await session.scalars(stmt))

    libraries = await rows(InspectionStandardLibrary)
    spaces = await rows(RagSpace)
    standards = await rows(StandardDocument)
    chunks = list((await session.execute(select(
        StandardDocumentChunk.document_id, StandardDocumentChunk.qdrant_point_id,
        StandardDocumentChunk.payload_json,
    ).where(StandardDocumentChunk.deleted_at.is_(None)))).all())
    specs = await rows(InspectionSpec)
    rules = await rows(StandardExecutionRule)
    # Read metadata only: no body, object key, URL, or uploader identity.
    rag_files = list((await session.execute(select(
        RagDocument.rag_space_id, RagDocument.checksum_sha256,
        RagDocument.parse_status, RagDocument.index_status,
    ).where(RagDocument.deleted_at.is_(None)))).all())
    spaces_by_id = {str(row.id): row for row in spaces}
    specs_by_id = {str(row.id): row for row in specs}
    docs_by_library = defaultdict(list)
    for row in standards:
        docs_by_library[str(row.library_id)].append(row)
    hashes_by_space = defaultdict(set)
    for space_id, checksum, _, _ in rag_files:
        if checksum:
            hashes_by_space[str(space_id)].add(checksum)
    point_docs = defaultdict(set)
    point_versions = Counter()
    for row in chunks:
        point_docs[str(row.qdrant_point_id)].add(str(row.document_id))
        point_versions[(row.payload_json or {}).get("point_id_version") or "legacy"] += 1

    inventory = []
    for library in libraries:
        bound_ids = [str(x) for x in library.rag_space_ids or []]
        docs = docs_by_library[str(library.id)]
        matching = sum(bool(doc.file_hash and any(
            doc.file_hash in hashes_by_space[space_id] for space_id in bound_ids
        )) for doc in docs)
        spec = specs_by_id.get(str(library.inspection_spec_id))
        inventory.append({
            "library_id": str(library.id), "organization_id": str(library.org_id) if library.org_id else None,
            "name": library.name, "product_family": library.product_family,
            "active": library.is_active, "import_status": library.import_status,
            "standard_document_count": len(docs),
            "standard_numbers": sorted({doc.standard_no for doc in docs}),
            "bound_spaces": [{
                "id": space_id, "exists": space_id in spaces_by_id,
                "system_owned": spaces_by_id[space_id].created_by is None if space_id in spaces_by_id else None,
                "same_organization": str(spaces_by_id[space_id].org_id) == str(library.org_id) if space_id in spaces_by_id else None,
            } for space_id in bound_ids],
            "documents_with_same_hash_in_bound_rag": matching,
            "bound_spec_exists": spec is not None,
            "bound_spec_active": spec.is_active if spec else None,
            "structured_rule_count": sum(str(rule.standard_id) == str(library.id) for rule in rules),
        })

    versions = list(await session.scalars(text("SELECT version_num FROM alembic_version"))) if "alembic_version" in present else []
    return {
        "status": "complete", "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True, "database_revisions": versions,
        "configured_rag_collection": settings.qdrant_collection,
        "counts": {
            "standard_libraries": len(libraries), "standard_documents": len(standards),
            "standard_chunks": len(chunks), "inspection_specs": len(specs),
            "standard_execution_rules": len(rules), "rag_spaces": len(spaces),
            "system_spaces": sum(row.created_by is None for row in spaces),
            "personal_spaces": sum(row.created_by is not None for row in spaces), "rag_documents": len(rag_files),
        },
        "index_id_versions": dict(point_versions),
        "stored_point_ids_shared_by_documents": sum(len(doc_ids) > 1 for doc_ids in point_docs.values()),
        "standard_processing_states": dict(Counter(row.import_status for row in standards)),
        "rag_index_states": dict(Counter(row[3] for row in rag_files)),
        "libraries": inventory,
        "limits": ["Metadata only; no vector service queried or rewritten.",
                   "Recorded current/effective status is not validation of a standard's legal or business applicability.",
                   "Stored point ID duplication indicates a collision risk; it does not alone prove vector data loss."],
    }


async def main(output: str | None):
    try:
        async with get_session() as session:
            report = await audit(session)
    finally:
        await reset_async_engine_pool()
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="Optional JSON metadata report; never modifies database or indexes.")
    args = parser.parse_args()
    asyncio.run(main(args.output))
