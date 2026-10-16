from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.core.datetime import utcnow
from app.core.exceptions import NotFoundError, ServiceUnavailableError, ValidationError
from app.core.ids import uuid7
from app.models.inspection_standard_library import InspectionStandardLibrary, StandardDocument, StandardDocumentChunk
from app.models.standard_admission import StandardDocumentRevision
from app.repositories.inspection_standard_library_repo import (
    InspectionStandardLibraryRepository,
    StandardDocumentChunkRepository,
    StandardDocumentRepository,
)
from app.repositories.inspection_spec_repo import InspectionSpecRepository
from app.repositories.product_master_repo import ProductMasterRepository
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
        self._spec_repo = InspectionSpecRepository(session)
        self._product_repo = ProductMasterRepository(session)
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

    async def list_task_choices(self) -> list[dict[str, Any]]:
        """Only selection and input requirements; no documents or governance settings."""
        rows = await self._repo.list_all(self._org_id)
        choices = []
        for item in rows:
            if not item.is_active:
                continue
            spec = await self._spec_repo.get(self._org_id, str(item.inspection_spec_id)) if item.inspection_spec_id else None
            if (not spec or not spec.is_active) and item.spec_code:
                spec = await self._spec_repo.get_active_spec(self._org_id, item.spec_code)
            if not spec or not spec.is_active:
                continue
            choices.append({"id": item.id, "name": item.name, "spec_code": spec.spec_code,
                            "required_image_count": int(spec.required_image_count or 1),
                            "required_views": list(spec.required_views or []), "is_active": True})
        return choices

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
            documents = await self._document_repo.list_by_library(self._org_id, library_id)
            if any(d.published_revision_id or d.publication_status == "publishing" for d in documents):
                raise ValidationError("库中有已发布或发布中的标准，请先撤回并保留修订记录")
            if documents:
                history=(await self._session.execute(select(StandardDocumentRevision.id).where(
                    StandardDocumentRevision.document_id.in_([d.id for d in documents]),StandardDocumentRevision.org_id==self._org_id,
                    StandardDocumentRevision.publication_status.in_(["published","publishing","suspended","withdrawn"])).limit(1))).scalar_one_or_none()
                if history:
                    raise ValidationError("库中有发布历史，请停用标准库并保留可追溯记录")
            await self._importer.delete_library_points(library_id=library_id)
            await self._chunk_repo.soft_delete_by_library(library_id)
            await self._document_repo.soft_delete_by_library(self._org_id, library_id)
            await self._repo.soft_delete(item)
        except Exception as exc:
            self._raise_if_table_missing(exc)
            raise

    async def scan_library(self, library_id: str) -> dict[str, Any]:
        item = await self._get_library(library_id)
        if not item.pdf_root_dir:
            raise ValidationError("pdf_root_dir is required before scanning")
        scanned = self._importer.scan_directory(item.pdf_root_dir, file_glob=item.file_glob or "*.pdf",
            fallback_domain=item.domain, fallback_product_category=item.product_category)
        before = {d.id for d in await self._document_repo.list_by_library(self._org_id, library_id)}
        result = await self.upload_pdfs(library_id, [(p["file_name"], Path(p["file_path"]).read_bytes(), "application/pdf") for p in scanned]) if scanned else {"documents": []}
        created = sum(d["id"] not in before for d in result["documents"])
        return {"library_id":library_id,"scanned_count":len(scanned),"created_count":created,
            "updated_count":0,"documents":result["documents"]}

    async def upload_pdfs(self, library_id: str, files: list[tuple[str, bytes, str | None]]) -> dict[str, Any]:
        from app.services.standard_admission_service import StandardAdmissionService
        return await StandardAdmissionService(self._session, self._org_id).receive(library_id, files)

    async def _index_document_from_path(self, library: InspectionStandardLibrary, document: StandardDocument, *, file_path: str) -> None:
        """Index a document from a local file path (used for uploaded files)."""
        if document.import_status == "completed":
            return
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
                file_path=file_path,
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
                        "token_count": len(re.findall(r"[A-Za-z0-9_]+|[一-鿿]", text)),
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

    async def index_library(self, library_id: str, *, reindex: bool = False) -> dict[str, Any]:
        from app.services.standard_admission_service import StandardAdmissionService
        item = await self._get_library(library_id)
        documents = await self._document_repo.list_by_library(self._org_id, library_id)
        service = StandardAdmissionService(self._session, self._org_id)
        for document in documents:
            if document.current_revision_id:
                _, rev = await service.revision(document.id, document.current_revision_id)
                if rev.processing_status != "parsed":
                    await service.enqueue(rev, "parse")
        return {"library_id":library_id,"document_count":len(documents),
            "indexed_document_count":sum(d.publication_status == "published" for d in documents),
            "chunk_count":sum(int(d.chunk_count or 0) for d in documents if d.publication_status == "published"),
            "failed_count":sum(d.processing_status == "failed" for d in documents)}

    async def index_document(self, document_id: str, *, reindex: bool = False) -> dict[str, Any]:
        document = await self._document_repo.get(self._org_id, document_id)
        if not document:
            raise NotFoundError("standard document not found")
        if document.current_revision_id:
            from app.services.standard_admission_service import StandardAdmissionService
            service = StandardAdmissionService(self._session, self._org_id)
            _, rev = await service.revision(document.id, document.current_revision_id)
            if rev.processing_status != "parsed":
                await service.enqueue(rev, "parse")
        return {"library_id":document.library_id,"document_count":1,
            "indexed_document_count":int(document.publication_status == "published"),
            "chunk_count":int(document.chunk_count or 0) if document.publication_status == "published" else 0,
            "failed_count":int(document.processing_status == "failed")}

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
        if document.current_revision_id:
            from app.core.exceptions import ConflictError
            raise ConflictError("请在标准详情补充元信息并新建修订，不能覆盖已有版本")
        allowed = {"standard_no", "standard_name", "domain", "product_category", "standard_level", "standard_status", "error_message"}
        normalized = {k: v for k, v in payload.items() if k in allowed and v is not None}
        if normalized:
            await self._document_repo.update(document, normalized)
        return self._serialize_document(document)

    async def delete_document(self, document_id: str) -> None:
        document = await self._document_repo.get(self._org_id, document_id)
        if not document:
            raise NotFoundError("standard document not found")
        if document.published_revision_id or document.publication_status == "publishing":
            raise ValidationError("已发布或发布中的标准请先撤回；保留历史修订")
        if document.current_revision_id:
            history=(await self._session.execute(select(StandardDocumentRevision.id).where(
                StandardDocumentRevision.document_id==document.id,StandardDocumentRevision.org_id==self._org_id,
                StandardDocumentRevision.publication_status.in_(["published","publishing","suspended","withdrawn"])).limit(1))).scalar_one_or_none()
            if history:
                raise ValidationError("标准有发布历史，请使用撤回或停用，保留原文与历史修订")
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
        from app.services.standard_admission_service import StandardAdmissionService
        return await StandardAdmissionService(self._session, self._org_id).search(payload)

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
        if "applicability" in payload:
            from app.schemas.supervision import StandardApplicability
            normalized["applicability"] = StandardApplicability.model_validate(payload["applicability"] or {}).model_dump(mode="json")
        if "name" in payload or not partial:
            name = str(payload.get("name") or "").strip()
            if not name:
                raise ValidationError("name is required")
            normalized["name"] = name
        if "product_family" in payload or not partial:
            product_family = str(
                payload.get("product_family")
                or payload.get("domain")
                or payload.get("name")
                or ""
            ).strip().lower()
            if not product_family:
                product_family = str(payload.get("name") or "").strip().lower()
            if not product_family:
                raise ValidationError("product_family is required")
            normalized["product_family"] = product_family
        if "inspection_spec_id" in payload or not partial:
            inspection_spec_id = str(payload.get("inspection_spec_id") or "").strip()
            if inspection_spec_id:
                spec = await self._spec_repo.get(self._org_id, inspection_spec_id)
                if not spec or not bool(getattr(spec, "is_active", False)):
                    raise ValidationError("inspection spec not found")
                normalized["inspection_spec_id"] = inspection_spec_id
                normalized["spec_code"] = str(spec.spec_code)
            elif not partial:
                normalized["inspection_spec_id"] = None
        if "spec_code" in payload:
            spec_code = str(payload.get("spec_code") or "").strip()
            if spec_code:
                spec = await self._spec_repo.get_active_spec(self._org_id, spec_code)
                if not spec:
                    raise ValidationError("inspection spec code not found")
                normalized["spec_code"] = str(spec.spec_code)
                normalized.setdefault("inspection_spec_id", str(spec.id))
            else:
                normalized["spec_code"] = None
        elif not partial and "spec_code" not in normalized:
            normalized["spec_code"] = None
        if "applicable_product_line_ids" in payload or not partial:
            line_ids = _normalize_id_list(payload.get("applicable_product_line_ids"))
            await self._ensure_product_lines_exist(line_ids)
            normalized["applicable_product_line_ids"] = line_ids
        if "applicable_product_sku_ids" in payload or not partial:
            sku_ids = _normalize_id_list(payload.get("applicable_product_sku_ids"))
            await self._ensure_product_skus_exist(sku_ids)
            normalized["applicable_product_sku_ids"] = sku_ids
        if "applicable_category_ids" in payload or not partial:
            category_ids = _normalize_id_list(payload.get("applicable_category_ids"))
            await self._ensure_product_categories_exist(category_ids)
            normalized["applicable_category_ids"] = category_ids
        if "applicable_product_ids" in payload or not partial:
            product_ids = _normalize_id_list(payload.get("applicable_product_ids"))
            await self._ensure_quality_products_exist(product_ids)
            normalized["applicable_product_ids"] = product_ids
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
                # Auto-create RAG space with same name as standard library
                name = str(payload.get("name") or "").strip()
                if not name:
                    raise ValidationError("name is required to auto-create rag space")
                from app.models.rag_space import RagSpace
                created_space=RagSpace(org_id=self._org_id,created_by=None,name=name[:120],
                    resource_domain="formal_standard",description=f"标准库关联视图：{name}")
                self._session.add(created_space)
                await self._session.flush()
                rag_space_ids = [str(created_space.id)]
            else:
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
        return normalized

    async def _ensure_rag_spaces_exist(self, rag_space_ids: list[str]) -> None:
        rows = await self._rag_repo.list_for_org(org_id=self._org_id, owner_user_id=None, limit=500)
        row_ids = {str(item.id) for item in rows}
        missing = [item for item in rag_space_ids if item not in row_ids]
        if missing:
            raise ValidationError(f"rag spaces not found: {', '.join(missing)}")

    async def _ensure_product_lines_exist(self, line_ids: list[str]) -> None:
        for line_id in line_ids:
            if not await self._product_repo.get_line(self._org_id, line_id):
                raise ValidationError(f"product line not found: {line_id}")

    async def _ensure_product_skus_exist(self, sku_ids: list[str]) -> None:
        for sku_id in sku_ids:
            if not await self._product_repo.get_sku(self._org_id, sku_id):
                raise ValidationError(f"product SKU not found: {sku_id}")

    async def _ensure_product_categories_exist(self, category_ids: list[str]) -> None:
        from app.models.quality_risk import ProductCategory

        for category_id in category_ids:
            row = await self._session.scalar(
                select(ProductCategory.id).where(
                    ProductCategory.id == category_id,
                    ProductCategory.org_id == self._org_id,
                    ProductCategory.deleted_at.is_(None),
                )
            )
            if not row:
                raise ValidationError(f"product category not found: {category_id}")

    async def _ensure_quality_products_exist(self, product_ids: list[str]) -> None:
        from app.models.quality_risk import QualityProduct

        for product_id in product_ids:
            row = await self._session.scalar(
                select(QualityProduct.id).where(
                    QualityProduct.id == product_id,
                    QualityProduct.org_id == self._org_id,
                    QualityProduct.deleted_at.is_(None),
                )
            )
            if not row:
                raise ValidationError(f"product not found: {product_id}")

    async def _serialize(self, item: InspectionStandardLibrary) -> dict[str, Any]:
        admission_docs=await self._document_repo.list_by_library(self._org_id,item.id)
        published_count=sum(bool(doc.published_revision_id) and doc.publication_status=="published" for doc in admission_docs)
        pending_count=sum(doc.review_status!="approved" for doc in admission_docs)
        rows = await self._rag_repo.list_for_org(org_id=self._org_id, owner_user_id=None, limit=500)
        space_map = {str(row.id): row for row in rows}
        spec = None
        if getattr(item, "inspection_spec_id", None):
            spec = await self._spec_repo.get(self._org_id, str(item.inspection_spec_id))
            if spec is not None and not bool(getattr(spec, "is_active", False)):
                spec = None
        if spec is None and getattr(item, "spec_code", None):
            spec = await self._spec_repo.get_active_spec(self._org_id, str(item.spec_code))
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
            "applicability": getattr(item, "applicability", None),
            "inspection_spec_id": getattr(item, "inspection_spec_id", None),
            "spec_code": getattr(item, "spec_code", None) or (str(spec.spec_code) if spec else None),
            "spec_name": str(spec.name) if spec else None,
            "has_quality_threshold": spec is not None,
            "applicable_product_line_ids": list(getattr(item, "applicable_product_line_ids", None) or []),
            "applicable_product_sku_ids": list(getattr(item, "applicable_product_sku_ids", None) or []),
            "applicable_category_ids": list(getattr(item, "applicable_category_ids", None) or []),
            "applicable_product_ids": list(getattr(item, "applicable_product_ids", None) or []),
            "required_image_count": int(spec.required_image_count or 1) if spec else None,
            "required_views": list(getattr(spec, "required_views", None) or []) if spec else [],
            "auto_pass_enabled": bool(spec.auto_pass_enabled) if spec else None,
            "ai_gate_confidence_threshold": float(spec.ai_gate_confidence_threshold) if spec else None,
            "ai_gate_evidence_threshold": float(spec.ai_gate_evidence_threshold) if spec else None,
            "ai_gate_traceability_threshold": float(spec.ai_gate_traceability_threshold) if spec else None,
            "domain": item.domain,
            "product_category": item.product_category,
            "description": item.description,
            "rag_space_ids": list(item.rag_space_ids or []),
            "rag_spaces": rag_spaces,
            "total_document_count": total_document_count,
            "published_document_count": published_count,
            "pending_review_document_count": pending_count,
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
            "current_revision_id": getattr(row,"current_revision_id",None),
            "published_revision_id": getattr(row,"published_revision_id",None),
            "processing_status": getattr(row,"processing_status",None) or "pending",
            "review_status": getattr(row,"review_status",None) or "pending",
            "publication_status": getattr(row,"publication_status",None) or "unpublished",
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


def _normalize_id_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = value.split(",")
    else:
        raw_items = list(value or [])
    return list(dict.fromkeys(str(item).strip() for item in raw_items if str(item).strip()))
