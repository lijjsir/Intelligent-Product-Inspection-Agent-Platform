from __future__ import annotations

from typing import Any

from sqlalchemy.exc import OperationalError, ProgrammingError

from app.core.exceptions import NotFoundError, ServiceUnavailableError, ValidationError
from app.core.ids import uuid7
from app.models.inspection_standard_library import InspectionStandardLibrary
from app.repositories.inspection_spec_repo import InspectionSpecRepository
from app.repositories.inspection_standard_library_repo import InspectionStandardLibraryRepository
from app.repositories.product_master_repo import ProductMasterRepository
from app.repositories.rag_space_repo import RagSpaceRepository

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
        self._spec_repo = InspectionSpecRepository(session)
        self._product_repo = ProductMasterRepository(session)
        self._rag_repo = RagSpaceRepository(session)

    async def list_items(self) -> list[dict[str, Any]]:
        try:
            rows = await self._repo.list_all(self._org_id)
            return [await self._serialize(item) for item in rows]
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

    async def get_active_item(self, library_id: str) -> InspectionStandardLibrary | None:
        try:
            return await self._repo.get_active(self._org_id, library_id)
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
            await self._repo.soft_delete(item)
        except Exception as exc:
            self._raise_if_table_missing(exc)
            raise

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

    async def resolve_active_by_spec_code(self, *, spec_code: str | None) -> dict[str, Any] | None:
        code = str(spec_code or "").strip()
        if not code:
            return None
        try:
            item = await self._repo.get_active_by_spec_code(self._org_id, code)
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
            product_family = str(payload.get("product_family") or "").strip().lower()
            if not product_family:
                raise ValidationError("product_family is required")
            normalized["product_family"] = product_family
        if "inspection_spec_id" in payload or not partial:
            inspection_spec_id = str(payload.get("inspection_spec_id") or "").strip()
            if inspection_spec_id:
                spec = await self._spec_repo.get(self._org_id, inspection_spec_id)
                if not spec:
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

    async def _serialize(self, item: InspectionStandardLibrary) -> dict[str, Any]:
        rows = await self._rag_repo.list_for_org(org_id=self._org_id, owner_user_id=None, limit=500)
        space_map = {str(row.id): row for row in rows}
        spec = None
        if getattr(item, "inspection_spec_id", None):
            spec = await self._spec_repo.get(self._org_id, str(item.inspection_spec_id))
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
            "inspection_spec_id": getattr(item, "inspection_spec_id", None),
            "spec_code": getattr(item, "spec_code", None) or (str(spec.spec_code) if spec else None),
            "spec_name": str(spec.name) if spec else None,
            "applicable_product_line_ids": list(getattr(item, "applicable_product_line_ids", None) or []),
            "applicable_product_sku_ids": list(getattr(item, "applicable_product_sku_ids", None) or []),
            "required_image_count": int(spec.required_image_count or 1) if spec else None,
            "required_views": list(getattr(spec, "required_views", None) or []) if spec else [],
            "auto_pass_enabled": bool(spec.auto_pass_enabled) if spec else None,
            "ai_gate_confidence_threshold": float(spec.ai_gate_confidence_threshold) if spec else None,
            "ai_gate_evidence_threshold": float(spec.ai_gate_evidence_threshold) if spec else None,
            "ai_gate_traceability_threshold": float(spec.ai_gate_traceability_threshold) if spec else None,
            "description": item.description,
            "rag_space_ids": list(item.rag_space_ids or []),
            "rag_spaces": rag_spaces,
            "total_document_count": total_document_count,
            "is_active": bool(item.is_active),
            "created_at": item.created_at,
            "updated_at": item.updated_at,
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
