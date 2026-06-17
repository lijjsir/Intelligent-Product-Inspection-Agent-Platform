from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.repositories.rag_space_repo import RagDocumentRepository, RagSpaceRepository
from app.services.inspection_standard_library_service import InspectionStandardLibraryService
from app.services.rag_space_service import RagSpaceService
from infra.database.session import get_session

DEFAULT_SEED_PATH = Path(__file__).with_name("system_rag.seed.jsonl")


def _load_seed_items(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line_no, raw_line in enumerate(file, start=1):
            line = raw_line.strip()
            if not line:
                continue
            item = json.loads(line)
            text = str(item.get("text") or "").strip()
            product_family = str(item.get("product_family") or "").strip().lower()
            if not text or not product_family:
                raise ValueError(f"invalid seed item at line {line_no}: product_family and text are required")
            items.append(item)
    return items


async def _find_system_space(session, *, org_id: str, name: str):
    rows = await RagSpaceRepository(session).list_for_org(org_id=org_id, owner_user_id=None, limit=1000)
    for row in rows:
        if str(row.name) == name and getattr(row, "created_by", None) is None:
            return row
    return None


async def _ensure_system_space(session, *, org_id: str, name: str, description: str):
    existing = await _find_system_space(session, org_id=org_id, name=name)
    if existing is not None:
        return existing
    service = RagSpaceService(session, org_id=org_id, user_id=None)  # created_by=None means system RAG space.
    created = await service.create_space(name=name, description=description)
    return await _find_system_space(session, org_id=org_id, name=str(created.name))


async def _delete_existing_doc_if_needed(
    session,
    *,
    org_id: str,
    rag_space_id: str,
    file_name: str,
    replace_existing: bool,
) -> bool:
    docs = await RagDocumentRepository(session).list_for_space(
        org_id=org_id,
        rag_space_id=rag_space_id,
        owner_user_id=None,
        limit=5000,
    )
    matched = [doc for doc in docs if str(doc.file_name) == file_name]
    if not matched:
        return False
    if not replace_existing:
        return True
    service = RagSpaceService(session, org_id=org_id, user_id=None)
    for doc in matched:
        await service.delete_document(rag_space_id=rag_space_id, file_id=str(doc.id))
    return False


async def _ensure_standard_binding(
    session,
    *,
    org_id: str,
    product_family: str,
    binding_name: str,
    rag_space_id: str,
) -> str:
    service = InspectionStandardLibraryService(session, org_id)
    existing = await service.resolve_active_binding(product_family=product_family)
    if existing:
        rag_space_ids = list(dict.fromkeys([*list(existing.get("rag_space_ids") or []), rag_space_id]))
        await service.update_item(
            str(existing["id"]),
            {
                "name": binding_name or existing.get("name"),
                "product_family": product_family,
                "rag_space_ids": rag_space_ids,
                "is_active": True,
            },
        )
        return str(existing["id"])
    created = await service.create_item(
        {
            "name": binding_name,
            "product_family": product_family,
            "description": "System built-in RAG binding for shared memory and standard retrieval tests.",
            "rag_space_ids": [rag_space_id],
            "is_active": True,
        }
    )
    return str(created["id"])


async def seed_system_rag(*, org_id: str, seed_path: Path, replace_existing: bool) -> dict[str, Any]:
    items = _load_seed_items(seed_path)
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        product_family = str(item["product_family"]).strip().lower()
        space_name = str(item.get("space_name") or f"系统标准库-{product_family}").strip()
        binding_name = str(item.get("binding_name") or f"{product_family} 系统标准库").strip()
        file_name = str(item.get("file_name") or f"{product_family}-system-rag.seed.jsonl").strip()
        grouped[(product_family, space_name, binding_name, file_name)].append(item)

    summary = {
        "org_id": org_id,
        "seed_path": str(seed_path),
        "groups": 0,
        "created_or_reused_spaces": [],
        "indexed_documents": [],
        "skipped_documents": [],
        "bindings": [],
    }

    async with get_session() as session:
        for (product_family, space_name, binding_name, file_name), group_items in grouped.items():
            space = await _ensure_system_space(
                session,
                org_id=org_id,
                name=space_name,
                description=f"系统内置标准 RAG 测试空间：{product_family}",
            )
            if space is None:
                raise RuntimeError(f"failed to create or find system RAG space: {space_name}")
            rag_space_id = str(space.id)
            summary["created_or_reused_spaces"].append({"product_family": product_family, "id": rag_space_id, "name": space_name})

            already_exists = await _delete_existing_doc_if_needed(
                session,
                org_id=org_id,
                rag_space_id=rag_space_id,
                file_name=file_name,
                replace_existing=replace_existing,
            )
            if already_exists:
                summary["skipped_documents"].append({"rag_space_id": rag_space_id, "file_name": file_name})
            else:
                content = "\n".join(
                    json.dumps(
                        {
                            "title": item.get("title") or file_name,
                            "source": item.get("source") or space_name,
                            "text": item.get("text") or "",
                        },
                        ensure_ascii=False,
                    )
                    for item in group_items
                ).encode("utf-8")
                service = RagSpaceService(session, org_id=org_id, user_id=None)
                node = await service.create_generated_document(
                    rag_space_id=rag_space_id,
                    file_name=file_name,
                    content=content,
                    content_type="application/x-ndjson; charset=utf-8",
                )
                summary["indexed_documents"].append(
                    {
                        "product_family": product_family,
                        "rag_space_id": rag_space_id,
                        "file_name": file_name,
                        "node_id": str(node.id),
                        "chunks": len(group_items),
                    }
                )

            binding_id = await _ensure_standard_binding(
                session,
                org_id=org_id,
                product_family=product_family,
                binding_name=binding_name,
                rag_space_id=rag_space_id,
            )
            summary["bindings"].append(
                {
                    "product_family": product_family,
                    "binding_id": binding_id,
                    "binding_name": binding_name,
                    "rag_space_id": rag_space_id,
                }
            )
            summary["groups"] += 1

        await session.commit()

    return summary


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed built-in system RAG spaces and standard bindings for shared memory tests.")
    parser.add_argument("--org-id", default=os.environ.get("PIAP_SYSTEM_RAG_ORG_ID"), help="Target organization id. Can also be set by PIAP_SYSTEM_RAG_ORG_ID.")
    parser.add_argument("--input", default=str(DEFAULT_SEED_PATH), help="Path to system RAG seed JSONL.")
    parser.add_argument("--replace-existing", action="store_true", help="Replace seed documents with the same file_name in the target system RAG space.")
    args = parser.parse_args()

    org_id = str(args.org_id or "").strip()
    if not org_id:
        raise SystemExit("--org-id or PIAP_SYSTEM_RAG_ORG_ID is required")

    result = await seed_system_rag(
        org_id=org_id,
        seed_path=Path(args.input),
        replace_existing=bool(args.replace_existing),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
