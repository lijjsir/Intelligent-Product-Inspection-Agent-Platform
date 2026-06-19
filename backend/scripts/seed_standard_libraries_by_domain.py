from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from infra.database.session import get_session

from app.models.inspection_standard_library import InspectionStandardLibrary
from app.models.rag_space import RagSpace
from app.repositories.inspection_standard_library_repo import InspectionStandardLibraryRepository
from app.repositories.rag_space_repo import RagSpaceRepository
from app.services.inspection_standard_library_service import InspectionStandardLibraryService
from app.services.standard_library_presets import STANDARD_LIBRARY_PRESETS, StandardLibraryPreset


DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"
AGGREGATE_LIBRARY_NAME = "国家标准基础外观质检库"


def default_base_root() -> Path:
    return Path(__file__).resolve().parents[1] / "standard" / "current"


def _display_path(path: str | Path) -> str:
    return str(path).replace("\\", "/")


def _library_payload(preset: StandardLibraryPreset, *, base_root: Path, rag_space_id: str) -> dict[str, Any]:
    return {
        "name": preset.library_name,
        "product_family": preset.product_family,
        "domain": preset.domain,
        "product_category": preset.product_category,
        "description": f"{preset.domain}国家标准 PDF 标准库",
        "rag_space_ids": [rag_space_id],
        "pdf_root_dir": str((base_root / preset.directory).resolve()),
        "file_glob": "*.pdf",
        "chunk_strategy": "heading_then_size",
        "standard_status": "现行",
        "auto_reindex": False,
        "is_active": True,
    }


def build_dry_run_summary(
    *,
    org_id: str,
    base_root: Path,
    replace_aggregate: bool,
    reindex: bool,
) -> dict[str, Any]:
    root = Path(base_root)
    libraries = [
        {
            "library_name": preset.library_name,
            "domain": preset.domain,
            "product_family": preset.product_family,
            "product_category": preset.product_category,
            "rag_space_name": preset.rag_space_name,
            "pdf_root_dir": _display_path(root / preset.directory),
            "file_names": list(preset.file_names),
            "file_count": len(preset.file_names),
        }
        for preset in STANDARD_LIBRARY_PRESETS
    ]
    return {
        "dry_run": True,
        "org_id": org_id,
        "base_root": _display_path(root),
        "replace_aggregate": replace_aggregate,
        "reindex": reindex,
        "library_count": len(libraries),
        "file_count": sum(item["file_count"] for item in libraries),
        "libraries": libraries,
    }


async def _find_system_rag_space(session, *, org_id: str, name: str) -> RagSpace | None:
    rows = await RagSpaceRepository(session).list_for_org(org_id=org_id, owner_user_id=None, limit=1000)
    for row in rows:
        if row.name == name and row.created_by is None:
            return row
    return None


async def _ensure_system_rag_space(session, *, org_id: str, preset: StandardLibraryPreset) -> RagSpace:
    existing = await _find_system_rag_space(session, org_id=org_id, name=preset.rag_space_name)
    if existing:
        return existing
    return await RagSpaceRepository(session).create(
        org_id=org_id,
        created_by=None,
        name=preset.rag_space_name,
        description=f"{preset.domain}国家标准 PDF RAG 空间",
    )


async def _find_library_by_name(session, *, org_id: str, name: str) -> InspectionStandardLibrary | None:
    rows = await InspectionStandardLibraryRepository(session).list_all(org_id)
    for row in rows:
        if row.name == name:
            return row
    return None


async def _ensure_library(
    service: InspectionStandardLibraryService,
    session,
    *,
    org_id: str,
    preset: StandardLibraryPreset,
    base_root: Path,
    rag_space_id: str,
) -> dict[str, Any]:
    payload = _library_payload(preset, base_root=base_root, rag_space_id=rag_space_id)
    existing = await _find_library_by_name(session, org_id=org_id, name=preset.library_name)
    if existing:
        return await service.update_item(str(existing.id), payload)
    return await service.create_item(payload)


def _validate_scanned_files(*, preset: StandardLibraryPreset, scanned_documents: list[dict[str, Any]]) -> None:
    expected = set(preset.file_names)
    actual = {str(document.get("file_name") or "") for document in scanned_documents}
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        details = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if extra:
            details.append(f"extra: {', '.join(extra)}")
        raise RuntimeError(f"{preset.library_name} PDF set mismatch ({'; '.join(details)})")


def assert_index_result_success(*, library_name: str, index_result: dict[str, Any]) -> None:
    failed_count = int(index_result.get("failed_count") or 0)
    if failed_count:
        indexed_count = int(index_result.get("indexed_document_count") or 0)
        raise RuntimeError(
            f"{library_name} indexing failed for {failed_count} document(s); "
            f"indexed {indexed_count} document(s). The aggregate library was not replaced."
        )


async def seed_standard_libraries_by_domain(
    *,
    org_id: str,
    base_root: Path,
    replace_aggregate: bool = False,
    reindex: bool = False,
) -> dict[str, Any]:
    root = Path(base_root).resolve()
    async with get_session() as session:
        service = InspectionStandardLibraryService(session, org_id=org_id)
        seeded: list[dict[str, Any]] = []
        try:
            for preset in STANDARD_LIBRARY_PRESETS:
                rag_space = await _ensure_system_rag_space(session, org_id=org_id, preset=preset)
                library = await _ensure_library(
                    service,
                    session,
                    org_id=org_id,
                    preset=preset,
                    base_root=root,
                    rag_space_id=str(rag_space.id),
                )
                scan_result = await service.scan_library(str(library["id"]))
                _validate_scanned_files(preset=preset, scanned_documents=list(scan_result.get("documents") or []))
                index_result = await service.index_library(str(library["id"]), reindex=reindex)
                assert_index_result_success(library_name=preset.library_name, index_result=index_result)
                seeded.append(
                    {
                        "library_id": str(library["id"]),
                        "library_name": preset.library_name,
                        "domain": preset.domain,
                        "rag_space_id": str(rag_space.id),
                        "rag_space_name": preset.rag_space_name,
                        "scanned_count": int(scan_result.get("scanned_count") or 0),
                        "indexed_document_count": int(index_result.get("indexed_document_count") or 0),
                        "chunk_count": int(index_result.get("chunk_count") or 0),
                        "failed_count": int(index_result.get("failed_count") or 0),
                    }
                )

            deleted_aggregate_library_id: str | None = None
            if replace_aggregate:
                aggregate = await _find_library_by_name(session, org_id=org_id, name=AGGREGATE_LIBRARY_NAME)
                if aggregate:
                    deleted_aggregate_library_id = str(aggregate.id)
                    await service.delete_item(str(aggregate.id))

            await session.commit()
            return {
                "dry_run": False,
                "org_id": org_id,
                "base_root": str(root),
                "replace_aggregate": replace_aggregate,
                "reindex": reindex,
                "library_count": len(seeded),
                "file_count": sum(item["scanned_count"] for item in seeded),
                "deleted_aggregate_library_id": deleted_aggregate_library_id,
                "libraries": seeded,
            }
        except Exception:
            await session.rollback()
            raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed domain-specific inspection standard libraries and system RAG spaces.")
    parser.add_argument("--org-id", default=DEFAULT_ORG_ID, help="Organization id for the standard libraries.")
    parser.add_argument("--base-root", type=Path, default=default_base_root(), help="Root directory containing domain PDF folders.")
    parser.add_argument("--replace-aggregate", action="store_true", help="Soft-delete the old aggregate standard library after success.")
    parser.add_argument("--reindex", action="store_true", help="Rebuild existing indexed documents.")
    parser.add_argument("--dry-run", action="store_true", help="Print the planned domain grouping without database writes.")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    if args.dry_run:
        result = build_dry_run_summary(
            org_id=args.org_id,
            base_root=args.base_root,
            replace_aggregate=bool(args.replace_aggregate),
            reindex=bool(args.reindex),
        )
    else:
        result = await seed_standard_libraries_by_domain(
            org_id=args.org_id,
            base_root=args.base_root,
            replace_aggregate=bool(args.replace_aggregate),
            reindex=bool(args.reindex),
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
