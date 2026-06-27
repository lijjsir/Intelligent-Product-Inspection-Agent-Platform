from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from infra.database.session import get_session, reset_async_engine_pool

from app.models.inspection_standard_library import InspectionStandardLibrary
from app.models.rag_space import RagSpace
from app.repositories.inspection_standard_library_repo import InspectionStandardLibraryRepository
from app.repositories.rag_space_repo import RagDocumentRepository, RagNodeRepository, RagSpaceRepository
from app.services.inspection_standard_library_service import InspectionStandardLibraryService
from app.services.standard_library_thresholds import (
    standard_library_spec_code,
    standard_library_spec_items,
    standard_library_spec_payload,
)
from app.services.standard_library_presets import STANDARD_LIBRARY_PRESETS, StandardLibraryPreset
from app.models.inspection_spec import InspectionSpec, InspectionSpecItem
from app.core.ids import uuid7


DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"
AGGREGATE_LIBRARY_NAME = "国家标准基础外观质检库"


def default_base_root() -> Path:
    return Path(__file__).resolve().parents[1] / "standard" / "current"


def _display_path(path: str | Path) -> str:
    return str(path).replace("\\", "/")


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _library_payload(preset: StandardLibraryPreset, *, base_root: Path, rag_space_id: str) -> dict[str, Any]:
    return {
        "name": preset.library_name,
        "product_family": preset.product_family,
        "spec_code": standard_library_spec_code(preset.product_family),
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


async def _ensure_quality_threshold(session, *, org_id: str, preset: StandardLibraryPreset) -> InspectionSpec:
    from sqlalchemy import select

    spec_code = standard_library_spec_code(preset.product_family)
    existing = (
        await session.execute(
            select(InspectionSpec).where(
                InspectionSpec.org_id == org_id,
                InspectionSpec.spec_code == spec_code,
                InspectionSpec.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing:
        existing.name = standard_library_spec_payload(
            spec_id=str(existing.id),
            org_id=org_id,
            domain=preset.domain,
            product_family=preset.product_family,
        )["name"]
        existing.product_id = preset.product_family
        existing.product_family = preset.product_family
        existing.applicable_skus = [preset.product_family]
        existing.required_views = ["overview"]
        existing.required_image_count = 1
        existing.auto_pass_enabled = True
        existing.is_active = True
        return existing

    spec_id = str(uuid7())
    spec = InspectionSpec(
        **standard_library_spec_payload(
            spec_id=spec_id,
            org_id=org_id,
            domain=preset.domain,
            product_family=preset.product_family,
        )
    )
    session.add(spec)
    for item in standard_library_spec_items(
        spec_id=spec_id,
        item_id=str(uuid7()),
        product_family=preset.product_family,
    ):
        session.add(InspectionSpecItem(**item))
    await session.flush()
    return spec


def build_dry_run_summary(
    *,
    org_id: str,
    base_root: Path,
    replace_aggregate: bool,
    reindex: bool,
    scan_only: bool = False,
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
        "scan_only": scan_only,
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
    spec = await _ensure_quality_threshold(session, org_id=org_id, preset=preset)
    payload = _library_payload(preset, base_root=base_root, rag_space_id=rag_space_id)
    payload["inspection_spec_id"] = str(spec.id)
    payload["spec_code"] = str(spec.spec_code)
    existing = await _find_library_by_name(session, org_id=org_id, name=preset.library_name)
    if existing:
        return await service.update_item(str(existing.id), payload)
    return await service.create_item(payload)


async def _ensure_rag_folder(
    session,
    *,
    org_id: str,
    rag_space_id: str,
    name: str,
) -> Any:
    node_repo = RagNodeRepository(session)
    existing = await node_repo.find_sibling(
        org_id=org_id,
        rag_space_id=rag_space_id,
        parent_id=None,
        name=name,
        owner_user_id=None,
    )
    if existing:
        return existing
    return await node_repo.create(
        org_id=org_id,
        rag_space_id=rag_space_id,
        created_by=None,
        parent_id=None,
        node_type="folder",
        name=name,
        full_path=name,
        depth=0,
        sort_order=0,
        status="ready",
    )


async def _ensure_rag_file_document(
    session,
    *,
    org_id: str,
    rag_space_id: str,
    parent_node: Any,
    document: dict[str, Any],
) -> bool:
    node_repo = RagNodeRepository(session)
    document_repo = RagDocumentRepository(session)
    file_name = str(document.get("file_name") or "").strip()
    file_path = Path(str(document.get("file_path") or ""))
    existing = await node_repo.find_sibling(
        org_id=org_id,
        rag_space_id=rag_space_id,
        parent_id=str(parent_node.id),
        name=file_name,
        owner_user_id=None,
    )
    if existing:
        return False
    node = await node_repo.create(
        org_id=org_id,
        rag_space_id=rag_space_id,
        created_by=None,
        parent_id=str(parent_node.id),
        node_type="file",
        name=file_name,
        full_path=f"{parent_node.full_path}/{file_name}",
        depth=int(parent_node.depth or 0) + 1,
        sort_order=0,
        status="ready",
    )
    await document_repo.create(
        org_id=org_id,
        rag_space_id=rag_space_id,
        node_id=str(node.id),
        uploaded_by=None,
        file_name=file_name,
        content_type="application/pdf",
        file_url=str(file_path),
        size_bytes=int(document.get("file_size") or (file_path.stat().st_size if file_path.exists() else 0)),
        checksum_sha256=str(document.get("file_hash") or (_sha256_file(file_path) if file_path.exists() else "")),
        storage_backend="local",
        bucket="standard",
        object_key=_display_path(file_path),
        parse_status="parsed",
        index_status="ready",
        chunk_count=int(document.get("chunk_count") or 0),
    )
    return True


async def sync_scanned_documents_to_rag_space_tree(
    session,
    *,
    org_id: str,
    rag_space_id: str,
    preset: StandardLibraryPreset,
    scanned_documents: list[dict[str, Any]],
) -> dict[str, int]:
    folder = await _ensure_rag_folder(
        session,
        org_id=org_id,
        rag_space_id=rag_space_id,
        name=preset.domain,
    )
    created_files = 0
    for document in scanned_documents:
        if await _ensure_rag_file_document(
            session,
            org_id=org_id,
            rag_space_id=rag_space_id,
            parent_node=folder,
            document=document,
        ):
            created_files += 1
    node_repo = RagNodeRepository(session)
    space_repo = RagSpaceRepository(session)
    await node_repo.recalculate_children_counts(org_id=org_id, rag_space_id=rag_space_id, owner_user_id=None)
    await space_repo.recalculate_counters(org_id=org_id, rag_space_id=rag_space_id, owner_user_id=None)
    return {"created_files": created_files}


async def sync_indexed_documents_to_rag_space_tree(
    session,
    *,
    org_id: str,
    rag_space_id: str,
    indexed_documents: list[dict[str, Any]],
) -> dict[str, int]:
    document_repo = RagDocumentRepository(session)
    updated_files = 0
    for document in indexed_documents:
        file_name = str(document.get("file_name") or "").strip()
        if not file_name:
            continue
        rag_document = await document_repo.get_by_file_name(
            org_id=org_id,
            rag_space_id=rag_space_id,
            file_name=file_name,
            owner_user_id=None,
        )
        if rag_document is None:
            continue
        rag_document.chunk_count = int(document.get("chunk_count") or 0)
        rag_document.parse_status = "parsed"
        rag_document.index_status = "ready" if int(document.get("chunk_count") or 0) > 0 else "failed"
        rag_document.error_message = document.get("error_message")
        updated_files += 1
    await RagSpaceRepository(session).recalculate_counters(org_id=org_id, rag_space_id=rag_space_id, owner_user_id=None)
    return {"updated_files": updated_files}


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
    scan_only: bool = False,
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
                scanned_documents = list(scan_result.get("documents") or [])
                _validate_scanned_files(preset=preset, scanned_documents=scanned_documents)
                rag_tree_result = await sync_scanned_documents_to_rag_space_tree(
                    session,
                    org_id=org_id,
                    rag_space_id=str(rag_space.id),
                    preset=preset,
                    scanned_documents=scanned_documents,
                )
                index_result: dict[str, Any]
                if scan_only:
                    index_result = {
                        "indexed_document_count": 0,
                        "chunk_count": 0,
                        "failed_count": 0,
                    }
                else:
                    index_result = await service.index_library(str(library["id"]), reindex=reindex)
                    assert_index_result_success(library_name=preset.library_name, index_result=index_result)
                    indexed_documents = list((await service.list_documents(str(library["id"]), page=1, size=5000)).get("items") or [])
                    rag_tree_result.update(
                        await sync_indexed_documents_to_rag_space_tree(
                            session,
                            org_id=org_id,
                            rag_space_id=str(rag_space.id),
                            indexed_documents=indexed_documents,
                        )
                    )
                seeded.append(
                    {
                        "library_id": str(library["id"]),
                        "library_name": preset.library_name,
                        "domain": preset.domain,
                        "rag_space_id": str(rag_space.id),
                        "rag_space_name": preset.rag_space_name,
                        "scanned_count": int(scan_result.get("scanned_count") or 0),
                        "rag_file_count": int(rag_tree_result.get("created_files") or 0),
                        "rag_updated_file_count": int(rag_tree_result.get("updated_files") or 0),
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
                "scan_only": scan_only,
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
    parser.add_argument("--scan-only", action="store_true", help="Register PDF documents without OCR parsing or vector indexing.")
    parser.add_argument("--dry-run", action="store_true", help="Print the planned domain grouping without database writes.")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    try:
        if args.dry_run:
            result = build_dry_run_summary(
                org_id=args.org_id,
                base_root=args.base_root,
                replace_aggregate=bool(args.replace_aggregate),
                reindex=bool(args.reindex),
                scan_only=bool(args.scan_only),
            )
        else:
            result = await seed_standard_libraries_by_domain(
                org_id=args.org_id,
                base_root=args.base_root,
                replace_aggregate=bool(args.replace_aggregate),
                reindex=bool(args.reindex),
                scan_only=bool(args.scan_only),
            )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    finally:
        await reset_async_engine_pool()


if __name__ == "__main__":
    asyncio.run(main())
