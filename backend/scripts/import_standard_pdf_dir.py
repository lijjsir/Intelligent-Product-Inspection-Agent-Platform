from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.core.ids import uuid7
from app.models.inspection_standard_library import InspectionStandardLibrary
from app.repositories.inspection_standard_library_repo import InspectionStandardLibraryRepository
from app.repositories.rag_space_repo import RagSpaceRepository
from app.services.inspection_standard_library_service import InspectionStandardLibraryService
from infra.database.session import get_session


async def _ensure_library(args: argparse.Namespace) -> str:
    async with get_session() as session:
        org_id = args.org_id
        rag_repo = RagSpaceRepository(session)
        spaces = await rag_repo.list_for_org(org_id=org_id, owner_user_id=None, limit=500)
        rag_space = next((space for space in spaces if str(space.id) == args.rag_space or space.name == args.rag_space), None)
        if rag_space is None:
            rag_space = await rag_repo.create(org_id=org_id, created_by=args.user_id, name=args.rag_space, description="国家标准 PDF 批量导入空间")

        repo = InspectionStandardLibraryRepository(session)
        rows = await repo.list_all(org_id)
        existing = next((row for row in rows if row.name == args.library_name), None)
        root = str(Path(args.root).resolve())
        if existing is None:
            existing = InspectionStandardLibrary(
                id=str(uuid7()),
                org_id=org_id,
                name=args.library_name,
                product_family=(args.product_category or args.domain or "standard").lower(),
                domain=args.domain,
                product_category=args.product_category,
                description=args.description,
                rag_space_ids=[str(rag_space.id)],
                qdrant_collection=args.qdrant_collection,
                pdf_root_dir=root,
                file_glob=args.file_glob,
                chunk_strategy=args.chunk_strategy,
                standard_status=args.standard_status,
                is_active=True,
            )
            await repo.create(existing)
        else:
            await repo.update(
                existing,
                {
                    "domain": args.domain or existing.domain,
                    "product_category": args.product_category or existing.product_category,
                    "rag_space_ids": [str(rag_space.id)],
                    "qdrant_collection": args.qdrant_collection,
                    "pdf_root_dir": root,
                    "file_glob": args.file_glob,
                    "chunk_strategy": args.chunk_strategy,
                    "standard_status": args.standard_status,
                    "is_active": True,
                },
            )
        await session.commit()
        return str(existing.id)


async def _run(args: argparse.Namespace) -> None:
    library_id = await _ensure_library(args)
    async with get_session() as session:
        service = InspectionStandardLibraryService(session, args.org_id)
        scan_result = await service.scan_library(library_id)
        index_result = await service.index_library(library_id, reindex=args.reindex)
        await session.commit()
    print(
        "scan={scanned_count} created={created_count} updated={updated_count} "
        "documents={document_count} indexed={indexed_document_count} chunks={chunk_count} failed={failed_count}".format(
            scanned_count=scan_result["scanned_count"],
            created_count=scan_result["created_count"],
            updated_count=scan_result["updated_count"],
            document_count=index_result["document_count"],
            indexed_document_count=index_result["indexed_document_count"],
            chunk_count=index_result["chunk_count"],
            failed_count=index_result["failed_count"],
        )
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import local national-standard PDFs into PIAP standard RAG.")
    parser.add_argument("--root", required=True, help="PDF root directory, for example standard/current")
    parser.add_argument("--library-name", required=True, help="Standard library display name")
    parser.add_argument("--rag-space", required=True, help="RAG space id or name")
    parser.add_argument("--org-id", default="00000000-0000-0000-0000-000000000001")
    parser.add_argument("--user-id", default=None)
    parser.add_argument("--domain", default=None)
    parser.add_argument("--product-category", default=None)
    parser.add_argument("--description", default=None)
    parser.add_argument("--file-glob", default="*.pdf")
    parser.add_argument("--chunk-strategy", default="heading_then_size")
    parser.add_argument("--standard-status", default="现行")
    parser.add_argument("--qdrant-collection", default=None)
    parser.add_argument("--reindex", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(_run(parse_args()))
