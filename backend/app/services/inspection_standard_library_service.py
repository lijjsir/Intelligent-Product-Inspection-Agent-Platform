from __future__ import annotations

import re
from typing import Any

from sqlalchemy.exc import OperationalError, ProgrammingError

from app.core.datetime import utcnow
from app.core.exceptions import NotFoundError, ServiceUnavailableError, ValidationError
from app.core.ids import uuid7
from app.models.inspection_standard_library import InspectionStandardLibrary, StandardDocument, StandardDocumentChunk
from app.repositories.inspection_standard_library_repo import (
    InspectionStandardLibraryRepository,
    StandardDocumentChunkRepository,
    StandardDocumentRepository,
)
from app.repositories.rag_space_repo import RagSpaceRepository
from app.services.standard_pdf_importer import StandardPdfImporter

INSPECTION_STANDARD_LIBRARY_MISSING_MESSAGE = "检测标准库尚未初始化，请先完成数据库迁移。"


def _is_inspection_standard_library_table_missing(exc: Exception) -> bool:
    if not isinstance(exc, (ProgrammingError, OperationalError)):
        return False
    message = str(exc).lower()
    if "doesn't exist" not in message and "does not exist" not in message:
        return False
    return "inspection_standard_libraries" in message


class InspectionStandardLibraryService:
    def __init__(self, session, org_id: str):
        self._session = session
        self._org_id = org_id
        self._repo = InspectionStandardLibraryRepository(session)
        self._document_repo = StandardDocumentRepository(session)
        self._chunk_repo = StandardDocumentChunkRepository(session)
        self._rag_repo = RagSpaceRepository(session)
        self._importer = StandardPdfImporter(org_id=org_id)

    async def list_items(self, *, page: int = 1, size: int = 50) -> dict[str, Any]:
        try:
            safe_page = max(1, int(page or 1))
            safe_size = min(max(1, int(size or 50)), 200)
            rows, total = await self._repo.list_all_paginated(self._org_id, page=safe_page, size=safe_size)
            items = [await self._serialize(item) for item in rows]
            return {"items": items, "total": total, "page": safe_page, "size": safe_size}
        except Exception as exc:
            self._raise_if_table_missing(exc)
            raise

    async def get_item(self, library_id: str) -> dict[str, Any]:
        try:
            item = await self._repo.get(self._org_id, library_id)
            if not item:
                raise NotFoundError("inspection standard library not found")
            return await self._serialize(item)
        except Exception as exc:
            self._raise_if_table_missing(exc)
            raise

    async def create_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            normalized = await self._normalize_payload(payload)
            item = InspectionStandardLibrary(
                id=str(uuid7()),
                org_id=self._org_id,
                **normalized,
            )
            await self._repo.create(item)
            return await self._serialize(item)
        except Exception as exc:
            self._raise_if_table_missing(exc)
            raise

    async def update_item(self, library_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            item = await self._repo.get(self._org_id, library_id)
            if not item:
                raise NotFoundError("inspection standard library not found")
            normalized = await self._normalize_payload(payload, partial=True)
            await self._repo.update(item, normalized)
            return await self._serialize(item)
        except Exception as exc:
            self._raise_if_table_missing(exc)
            raise

    async def delete_item(self, library_id: str) -> None:
        try:
            item = await self._repo.get(self._org_id, library_id)
            if not item:
                raise NotFoundError("inspection standard library not found")
            await self._importer.delete_library_points(library_id=library_id)
            await self._chunk_repo.soft_delete_by_library(library_id)
            await self._document_repo.soft_delete_by_library(self._org_id, library_id)
            await self._repo.soft_delete(item)
        except Exception as exc:
            self._raise_if_table_missing(exc)
            raise

    async def scan_library(self, library_id: str) -> dict[str, Any]:
        try:
            item = await self._get_library(library_id)
            if not item.pdf_root_dir:
                raise ValidationError("pdf_root_dir is required before scanning")
            scanned = self._importer.scan_directory(
                item.pdf_root_dir,
                file_glob=item.file_glob or "*.pdf",
                fallback_domain=item.domain,
                fallback_product_category=item.product_category,
            )
            created_count = 0
            updated_count = 0
            rows: list[StandardDocument] = []
            for payload in scanned:
                meta_payload = {
                    "domain": payload["domain"],
                    "product_category": payload.get("product_category"),
                    "standard_no": payload["standard_no"],
                    "standard_name": payload["standard_name"],
                    "standard_level": payload["standard_level"],
                    "standard_status": payload.get("standard_status") or item.standard_status or "现行",
                    "file_name": payload["file_name"],
                    "file_path": payload["file_path"],
                    "file_hash": payload.get("file_hash"),
                    "file_size": payload.get("file_size"),
                    "qdrant_collection": item.qdrant_collection,
                    "import_status": payload.get("import_status") or "pending",
                    "error_message": None,
                }
                row, created = await self._document_repo.upsert_scanned(
                    org_id=self._org_id,
                    library_id=library_id,
                    payload=meta_payload,
                )
                rows.append(row)
                if created:
                    created_count += 1
                else:
                    updated_count += 1
            item.pdf_count = len(scanned)
            item.document_count = await self._document_repo.count_completed_by_library(self._org_id, library_id)
            item.chunk_count = await self._chunk_repo.count_by_library(library_id)
            item.import_status = "scanned" if scanned else "not_scanned"
            item.last_scanned_at = utcnow()
            item.error_message = None
            await self._session.flush()
            return {
                "library_id": library_id,
                "scanned_count": len(scanned),
                "created_count": created_count,
                "updated_count": updated_count,
                "documents": [self._serialize_document(row) for row in rows],
            }
        except Exception as exc:
            self._raise_if_table_missing(exc)
            raise

    async def index_library(self, library_id: str, *, reindex: bool = False) -> dict[str, Any]:
        try:
            item = await self._get_library(library_id)
            documents = await self._document_repo.list_by_library(self._org_id, library_id)
            if not documents and item.pdf_root_dir:
                await self.scan_library(library_id)
                documents = await self._document_repo.list_by_library(self._org_id, library_id)
            indexed_document_count = 0
            chunk_count = 0
            failed_count = 0
            item.import_status = "indexing"
            await self._session.flush()
            for document in documents:
                if document.import_status == "completed" and not reindex:
                    indexed_document_count += 1
                    chunk_count += int(document.chunk_count or 0)
                    continue
                await self._index_document(item, document, reindex=reindex)
                if document.import_status == "completed":
                    indexed_document_count += 1
                    chunk_count += int(document.chunk_count or 0)
                else:
                    failed_count += 1
            item.pdf_count = len(documents)
            item.document_count = indexed_document_count
            item.chunk_count = await self._chunk_repo.count_by_library(library_id)
            item.last_indexed_at = utcnow() if documents else item.last_indexed_at
            if failed_count and indexed_document_count:
                item.import_status = "partial_failed"
            elif failed_count:
                item.import_status = "failed"
            elif documents:
                item.import_status = "completed"
            else:
                item.import_status = "not_scanned"
            item.error_message = None if not failed_count else f"{failed_count} standard documents failed to index"
            await self._session.flush()
            return {
                "library_id": library_id,
                "document_count": len(documents),
                "indexed_document_count": indexed_document_count,
                "chunk_count": item.chunk_count,
                "failed_count": failed_count,
            }
        except Exception as exc:
            self._raise_if_table_missing(exc)
            raise

    async def index_document(self, document_id: str, *, reindex: bool = False) -> dict[str, Any]:
        document = await self._document_repo.get(self._org_id, document_id)
        if not document:
            raise NotFoundError("standard document not found")
        item = await self._get_library(str(document.library_id))
        await self._index_document(item, document, reindex=reindex)
        return {
            "library_id": str(document.library_id),
            "document_count": 1,
            "indexed_document_count": 1 if document.import_status == "completed" else 0,
            "chunk_count": int(document.chunk_count or 0),
            "failed_count": 0 if document.import_status == "completed" else 1,
        }

    async def list_documents(self, library_id: str, *, page: int = 1, size: int = 50) -> dict[str, Any]:
        await self._get_library(library_id)
        safe_page = max(1, int(page or 1))
        safe_size = min(max(1, int(size or 50)), 200)
        rows, total = await self._document_repo.list_by_library_paginated(self._org_id, library_id, page=safe_page, size=safe_size)
        items = [self._serialize_document(row) for row in rows]
        return {"items": items, "total": total, "page": safe_page, "size": safe_size}

    async def update_document(self, document_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        document = await self._document_repo.get(self._org_id, document_id)
        if not document:
            raise NotFoundError("standard document not found")
        allowed = {"standard_no", "standard_name", "domain", "product_category", "standard_level", "standard_status", "error_message"}
        normalized = {k: v for k, v in payload.items() if k in allowed and v is not None}
        if normalized:
            await self._document_repo.update(document, normalized)
        return self._serialize_document(document)

    async def delete_document(self, document_id: str) -> None:
        document = await self._document_repo.get(self._org_id, document_id)
        if not document:
            raise NotFoundError("standard document not found")
        try:
            await self._importer.delete_document_points(document_id=document_id, library_id=str(document.library_id))
        except Exception:
            pass  # Best-effort Qdrant cleanup
        await self._document_repo.soft_delete(document)

    async def get_document(self, document_id: str) -> dict[str, Any]:
        document = await self._document_repo.get(self._org_id, document_id)
        if not document:
            raise NotFoundError("standard document not found")
        return self._serialize_document(document)

    async def list_chunks(self, document_id: str) -> list[dict[str, Any]]:
        document = await self._document_repo.get(self._org_id, document_id)
        if not document:
            raise NotFoundError("standard document not found")
        rows = await self._chunk_repo.list_by_document(document_id)
        return [self._serialize_chunk(row) for row in rows]

    async def retrieve(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = str(payload.get("query") or "").strip()
        if not query:
            raise ValidationError("query is required")
        top_k = int(payload.get("top_k") or 8)
        # Expand query with defect keywords for better recall
        defect_keywords: list[str] = [str(k).strip() for k in list(payload.get("defect_keywords") or []) if str(k).strip()]
        if defect_keywords:
            expanded_terms = " ".join(defect_keywords)
            query = f"{query} {expanded_terms}"
        filters: list[dict[str, Any]] = []
        base = {"org_id": self._org_id}
        domain = str(payload.get("domain") or "").strip()
        product_category = str(payload.get("product_category") or "").strip()
        if domain and product_category:
            filters.append({**base, "domain": domain, "product_category": product_category})
        if domain:
            filters.append({**base, "domain": domain})
        filters.append(base)

        best_result: dict[str, Any] | None = None
        for payload_filter in filters:
            result = await self._importer.retrieve(query=query, top_k=top_k, payload_filter=payload_filter)
            if result["hits"]:
                best_result = result
                break
            best_result = result
        result = best_result or {"hits": [], "hit_count": 0, "candidate_count": 0, "latency_ms": 0.0}
        hits = [self._serialize_retrieval_hit(hit) for hit in result.get("hits") or []]
        return {
            "hits": hits,
            "hit_count": len(hits),
            "candidate_count": int(result.get("candidate_count") or len(hits)),
            "latency_ms": float(result.get("latency_ms") or 0.0),
        }

    async def resolve_active_binding(self, *, product_family: str | None) -> dict[str, Any] | None:
        family = str(product_family or "").strip().lower()
        if not family:
            return None
        try:
            item = await self._repo.get_by_product_family(self._org_id, family)
            if not item:
                return None
            return await self._serialize(item)
        except Exception as exc:
            if _is_inspection_standard_library_table_missing(exc):
                return None
            raise

    async def _normalize_payload(self, payload: dict[str, Any], partial: bool = False) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        if "name" in payload or not partial:
            name = str(payload.get("name") or "").strip()
            if not name:
                raise ValidationError("name is required")
            normalized["name"] = name
        if "product_family" in payload or not partial:
            product_family = str(
                payload.get("product_family")
                or payload.get("product_category")
                or payload.get("domain")
                or ""
            ).strip().lower()
            if not product_family:
                raise ValidationError("product_family is required")
            normalized["product_family"] = product_family
        for key in ("domain", "product_category", "qdrant_collection", "pdf_root_dir", "file_glob", "chunk_strategy", "standard_status"):
            if key in payload:
                value = str(payload.get(key) or "").strip()
                if key == "file_glob" and not value:
                    value = "*.pdf"
                if key == "chunk_strategy" and not value:
                    value = "heading_then_size"
                if key == "standard_status" and not value:
                    value = "现行"
                normalized[key] = value or None
            elif not partial and key in {"file_glob", "chunk_strategy", "standard_status"}:
                normalized[key] = {"file_glob": "*.pdf", "chunk_strategy": "heading_then_size", "standard_status": "现行"}[key]
        if "description" in payload:
            description = str(payload.get("description") or "").strip()
            normalized["description"] = description or None
        elif not partial:
            normalized["description"] = None
        if "rag_space_ids" in payload or not partial:
            rag_space_ids = [str(item).strip() for item in list(payload.get("rag_space_ids") or []) if str(item).strip()]
            if not rag_space_ids:
                raise ValidationError("at least one rag space is required")
            await self._ensure_rag_spaces_exist(rag_space_ids)
            normalized["rag_space_ids"] = list(dict.fromkeys(rag_space_ids))
        if "is_active" in payload:
            normalized["is_active"] = bool(payload.get("is_active"))
        elif not partial:
            normalized["is_active"] = True
        if "auto_reindex" in payload:
            normalized["auto_reindex"] = bool(payload.get("auto_reindex"))
        elif not partial:
            normalized["auto_reindex"] = False
        if "import_mode" in payload:
            normalized["import_mode"] = str(payload.get("import_mode") or "").strip() or "scan_and_index"
        elif not partial:
            normalized["import_mode"] = "scan_and_index"
        return normalized

    async def _ensure_rag_spaces_exist(self, rag_space_ids: list[str]) -> None:
        rows = await self._rag_repo.list_for_org(org_id=self._org_id, owner_user_id=None, limit=500)
        row_ids = {str(item.id) for item in rows}
        missing = [item for item in rag_space_ids if item not in row_ids]
        if missing:
            raise ValidationError(f"rag spaces not found: {', '.join(missing)}")

    async def _serialize(self, item: InspectionStandardLibrary) -> dict[str, Any]:
        rows = await self._rag_repo.list_for_org(org_id=self._org_id, owner_user_id=None, limit=500)
        space_map = {str(row.id): row for row in rows}
        rag_spaces = []
        total_document_count = 0
        for rag_space_id in list(item.rag_space_ids or []):
            row = space_map.get(str(rag_space_id))
            if not row:
                continue
            document_count = int(getattr(row, "file_count", 0) or 0)
            total_document_count += document_count
            rag_spaces.append(
                {
                    "id": str(row.id),
                    "name": str(row.name),
                    "document_count": document_count,
                    "status": str(getattr(row, "index_status", "") or "") or None,
                }
            )
        return {
            "id": item.id,
            "org_id": item.org_id,
            "name": item.name,
            "product_family": item.product_family,
            "domain": item.domain,
            "product_category": item.product_category,
            "description": item.description,
            "rag_space_ids": list(item.rag_space_ids or []),
            "rag_spaces": rag_spaces,
            "total_document_count": total_document_count,
            "qdrant_collection": item.qdrant_collection,
            "pdf_root_dir": item.pdf_root_dir,
            "file_glob": item.file_glob,
            "chunk_strategy": item.chunk_strategy,
            "standard_status": item.standard_status,
            "auto_reindex": bool(item.auto_reindex),
            "pdf_count": int(item.pdf_count or 0),
            "document_count": int(item.document_count or 0),
            "chunk_count": int(item.chunk_count or 0),
            "import_status": item.import_status,
            "last_scanned_at": item.last_scanned_at,
            "last_indexed_at": item.last_indexed_at,
            "error_message": item.error_message,
            "is_active": bool(item.is_active),
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    async def _get_library(self, library_id: str) -> InspectionStandardLibrary:
        item = await self._repo.get(self._org_id, library_id)
        if not item:
            raise NotFoundError("inspection standard library not found")
        return item

    async def _index_document(self, library: InspectionStandardLibrary, document: StandardDocument, *, reindex: bool) -> None:
        if reindex:
            await self._importer.delete_document_points(document_id=str(document.id), library_id=str(library.id))
        document.import_status = "indexing"
        document.error_message = None
        await self._session.flush()
        meta = {
            "standard_no": document.standard_no,
            "standard_name": document.standard_name,
            "domain": document.domain,
            "product_category": document.product_category,
            "standard_level": document.standard_level,
            "standard_status": document.standard_status,
            "inspection_items": [],
            "image_defect_keywords": [],
        }
        try:
            result = await self._importer.index_document(
                library_id=str(library.id),
                document_id=str(document.id),
                file_path=document.file_path,
                meta=meta,
                rag_space_id=(library.rag_space_ids or [None])[0],
                chunk_strategy=library.chunk_strategy or "heading_then_size",
            )
            accepted = int(result.get("accepted") or 0)
            if accepted <= 0:
                raise ValidationError(f"failed to index document: {document.file_name}")
            chunk_rows = []
            for doc in result["docs"]:
                payload = dict(doc.get("payload") or {})
                text = str(doc.get("text") or "")
                chunk_rows.append(
                    {
                        "chunk_index": int(payload.get("chunk_index") or 1),
                        "page_from": payload.get("page_number"),
                        "page_to": payload.get("page_number"),
                        "section_title": str(doc.get("title") or "")[:255],
                        "chunk_text": text,
                        "payload_json": payload,
                        "qdrant_point_id": str(doc.get("id") or ""),
                        "token_count": len(re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", text)),
                    }
                )
            await self._chunk_repo.replace_for_document(
                document_id=str(document.id),
                library_id=str(library.id),
                rows=chunk_rows,
            )
            document.page_count = int(result.get("page_count") or 0)
            document.chunk_count = accepted
            document.import_status = "completed"
            document.last_indexed_at = utcnow()
            document.error_message = None
        except Exception as exc:
            document.import_status = "failed"
            document.error_message = str(exc)
            document.chunk_count = 0
            await self._chunk_repo.soft_delete_by_document(str(document.id))
        await self._session.flush()

    def _serialize_document(self, row: StandardDocument) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "library_id": str(row.library_id),
            "standard_no": row.standard_no,
            "standard_name": row.standard_name,
            "domain": row.domain,
            "product_category": row.product_category,
            "standard_level": row.standard_level,
            "standard_status": row.standard_status,
            "file_name": row.file_name,
            "file_path": row.file_path,
            "file_hash": row.file_hash,
            "file_size": row.file_size,
            "page_count": row.page_count,
            "chunk_count": int(row.chunk_count or 0),
            "qdrant_collection": row.qdrant_collection,
            "import_status": row.import_status,
            "last_indexed_at": row.last_indexed_at,
            "error_message": row.error_message,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def _serialize_chunk(self, row: StandardDocumentChunk) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "document_id": str(row.document_id),
            "library_id": str(row.library_id),
            "chunk_index": int(row.chunk_index or 0),
            "page_from": row.page_from,
            "page_to": row.page_to,
            "section_title": row.section_title,
            "chunk_text": row.chunk_text,
            "payload_json": row.payload_json,
            "qdrant_point_id": row.qdrant_point_id,
            "token_count": row.token_count,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def _serialize_retrieval_hit(self, hit: dict[str, Any]) -> dict[str, Any]:
        payload = dict(hit.get("payload") or {})
        return {
            "id": str(hit.get("id") or ""),
            "title": str(hit.get("title") or payload.get("title") or ""),
            "source": str(hit.get("source") or payload.get("source") or ""),
            "quote": str(hit.get("quote") or hit.get("text") or payload.get("text") or "")[:500],
            "score": float(hit.get("score") or 0.0),
            "standard_no": hit.get("standard_no") or payload.get("standard_no"),
            "standard_name": hit.get("standard_name") or payload.get("standard_name"),
            "domain": hit.get("domain") or payload.get("domain"),
            "product_category": hit.get("product_category") or payload.get("product_category"),
            "page_number": hit.get("page_number") or payload.get("page_number"),
            "chunk_index": hit.get("chunk_index") or payload.get("chunk_index"),
            "payload": payload,
        }

    @staticmethod
    def _raise_if_table_missing(exc: Exception) -> None:
        if _is_inspection_standard_library_table_missing(exc):
            raise ServiceUnavailableError(INSPECTION_STANDARD_LIBRARY_MISSING_MESSAGE) from exc
