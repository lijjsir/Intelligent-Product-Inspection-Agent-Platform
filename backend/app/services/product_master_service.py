from __future__ import annotations

from typing import Any

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.product import ProductBatch, ProductLine, ProductSku
from app.repositories.product_master_repo import ProductMasterRepository

UNSPECIFIED_BATCH_NO = "UNSPECIFIED"
UNSPECIFIED_BATCH_NAME = "未指定批次"
LEGACY_DESCRIPTION = "Auto-created from legacy inspection task product_id."
LEGACY_DESCRIPTION_ZH = "由历史检测任务的产品编号自动创建。"
LEGACY_BATCH_DESCRIPTION = "Auto-created compatibility batch for tasks without batch_no."
LEGACY_BATCH_DESCRIPTION_ZH = "为没有批次号的历史任务自动创建的兼容批次。"


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _localized_description(value: Any) -> str | None:
    text = _clean_text(value)
    if text == LEGACY_DESCRIPTION:
        return LEGACY_DESCRIPTION_ZH
    if text == LEGACY_BATCH_DESCRIPTION:
        return LEGACY_BATCH_DESCRIPTION_ZH
    return text or None


def _localized_batch_name(name: Any, batch_no: Any) -> str:
    text = _clean_text(name)
    if _clean_text(batch_no) == UNSPECIFIED_BATCH_NO and text.lower() == "unspecified batch":
        return UNSPECIFIED_BATCH_NAME
    return text or _clean_text(batch_no)


class ProductMasterService:
    def __init__(self, session, org_id: str):
        self._session = session
        self._org_id = org_id
        self._repo = ProductMasterRepository(session)

    async def catalog(self, *, include_inactive: bool = True) -> dict[str, list[dict[str, Any]]]:
        lines = await self._repo.list_lines(self._org_id, include_inactive=include_inactive)
        skus = await self._repo.list_skus(self._org_id, include_inactive=include_inactive)
        batches = await self._repo.list_batches(self._org_id, include_inactive=include_inactive)
        line_map = {str(item.id): item for item in lines}
        sku_map = {str(item.id): item for item in skus}
        return {
            "product_lines": [self._serialize_line(item) for item in lines],
            "product_skus": [self._serialize_sku(item, line_map.get(str(item.product_line_id))) for item in skus],
            "product_batches": [
                self._serialize_batch(item, sku_map.get(str(item.product_sku_id)), line_map)
                for item in batches
            ],
        }

    async def create_line(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = self._normalize_line_payload(payload)
        await self._ensure_unique_line_code(data["code"])
        line = await self._repo.create_line(ProductLine(org_id=self._org_id, **data))
        return self._serialize_line(line)

    async def update_line(self, line_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        line = await self._require_line(line_id)
        data = self._normalize_line_payload(payload, partial=True)
        if "code" in data and data["code"] != line.code:
            await self._ensure_unique_line_code(data["code"])
        await self._repo.update(line, data)
        return self._serialize_line(line)

    async def delete_line(self, line_id: str) -> None:
        line = await self._require_line(line_id)
        skus = [item for item in await self._repo.list_skus(self._org_id) if str(item.product_line_id) == str(line.id)]
        if skus:
            raise ConflictError("product line has SKUs; disable or delete SKUs first")
        await self._repo.soft_delete(line)

    async def create_sku(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = await self._normalize_sku_payload(payload)
        await self._ensure_unique_sku_code(data["code"])
        sku = await self._repo.create_sku(ProductSku(org_id=self._org_id, **data))
        line = await self._repo.get_line(self._org_id, str(sku.product_line_id))
        return self._serialize_sku(sku, line)

    async def update_sku(self, sku_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        sku = await self._require_sku(sku_id)
        data = await self._normalize_sku_payload(payload, partial=True)
        if "code" in data and data["code"] != sku.code:
            await self._ensure_unique_sku_code(data["code"])
        await self._repo.update(sku, data)
        line = await self._repo.get_line(self._org_id, str(sku.product_line_id))
        return self._serialize_sku(sku, line)

    async def delete_sku(self, sku_id: str) -> None:
        sku = await self._require_sku(sku_id)
        batches = [item for item in await self._repo.list_batches(self._org_id) if str(item.product_sku_id) == str(sku.id)]
        if batches:
            raise ConflictError("product SKU has batches; disable or delete batches first")
        await self._repo.soft_delete(sku)

    async def create_batch(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = await self._normalize_batch_payload(payload)
        await self._ensure_unique_batch_no(data["product_sku_id"], data["batch_no"])
        batch = await self._repo.create_batch(ProductBatch(org_id=self._org_id, **data))
        sku = await self._repo.get_sku(self._org_id, str(batch.product_sku_id))
        line_map = {str(item.id): item for item in await self._repo.list_lines(self._org_id)}
        return self._serialize_batch(batch, sku, line_map)

    async def update_batch(self, batch_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        batch = await self._require_batch(batch_id)
        data = await self._normalize_batch_payload(payload, partial=True)
        next_sku_id = data.get("product_sku_id", batch.product_sku_id)
        next_batch_no = data.get("batch_no", batch.batch_no)
        if str(next_sku_id) != str(batch.product_sku_id) or next_batch_no != batch.batch_no:
            await self._ensure_unique_batch_no(str(next_sku_id), next_batch_no)
        await self._repo.update(batch, data)
        sku = await self._repo.get_sku(self._org_id, str(batch.product_sku_id))
        line_map = {str(item.id): item for item in await self._repo.list_lines(self._org_id)}
        return self._serialize_batch(batch, sku, line_map)

    async def delete_batch(self, batch_id: str) -> None:
        batch = await self._require_batch(batch_id)
        await self._repo.soft_delete(batch)

    async def require_active_sku_and_batch(self, sku_id: str, batch_id: str) -> tuple[ProductLine, ProductSku, ProductBatch]:
        sku = await self._require_sku(sku_id)
        if not sku.is_active:
            raise ValidationError("product SKU is inactive")
        line = await self._require_line(str(sku.product_line_id))
        if not line.is_active:
            raise ValidationError("product line is inactive")
        batch = await self._require_batch(batch_id)
        if str(batch.product_sku_id) != str(sku.id):
            raise ValidationError("batch does not belong to selected product SKU")
        if not batch.is_active:
            raise ValidationError("batch is inactive")
        return line, sku, batch

    async def ensure_legacy_defaults(self, product_code: str) -> tuple[ProductLine, ProductSku, ProductBatch]:
        code = _clean_text(product_code) or "unknown-product"
        line = await self._repo.get_line_by_code(self._org_id, code)
        if line is None:
            line = await self._repo.create_line(
                ProductLine(
                    org_id=self._org_id,
                    code=code,
                    name=code,
                    description=LEGACY_DESCRIPTION_ZH,
                    is_active=True,
                )
            )
        sku = await self._repo.get_sku_by_code(self._org_id, code)
        if sku is None:
            sku = await self._repo.create_sku(
                ProductSku(
                    org_id=self._org_id,
                    product_line_id=str(line.id),
                    code=code,
                    name=code,
                    description=LEGACY_DESCRIPTION_ZH,
                    is_active=True,
                )
            )
        batch = await self._repo.get_batch_by_sku_and_no(self._org_id, str(sku.id), UNSPECIFIED_BATCH_NO)
        if batch is None:
            batch = await self._repo.create_batch(
                ProductBatch(
                    org_id=self._org_id,
                    product_sku_id=str(sku.id),
                    batch_no=UNSPECIFIED_BATCH_NO,
                    name=UNSPECIFIED_BATCH_NAME,
                    description=LEGACY_BATCH_DESCRIPTION_ZH,
                    is_active=True,
                )
            )
        return line, sku, batch

    async def _require_line(self, line_id: str) -> ProductLine:
        line = await self._repo.get_line(self._org_id, line_id)
        if not line:
            raise NotFoundError("product line not found")
        return line

    async def _require_sku(self, sku_id: str) -> ProductSku:
        sku = await self._repo.get_sku(self._org_id, sku_id)
        if not sku:
            raise NotFoundError("product SKU not found")
        return sku

    async def _require_batch(self, batch_id: str) -> ProductBatch:
        batch = await self._repo.get_batch(self._org_id, batch_id)
        if not batch:
            raise NotFoundError("product batch not found")
        return batch

    async def _ensure_unique_line_code(self, code: str) -> None:
        if await self._repo.get_line_by_code(self._org_id, code):
            raise ConflictError(f"product line code already exists: {code}")

    async def _ensure_unique_sku_code(self, code: str) -> None:
        if await self._repo.get_sku_by_code(self._org_id, code):
            raise ConflictError(f"product SKU code already exists: {code}")

    async def _ensure_unique_batch_no(self, sku_id: str, batch_no: str) -> None:
        if await self._repo.get_batch_by_sku_and_no(self._org_id, sku_id, batch_no):
            raise ConflictError(f"batch already exists for product SKU: {batch_no}")

    def _normalize_line_payload(self, payload: dict[str, Any], *, partial: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if "code" in payload or not partial:
            code = _clean_text(payload.get("code"))
            if not code:
                raise ValidationError("product line code is required")
            data["code"] = code
        if "name" in payload or not partial:
            name = _clean_text(payload.get("name"))
            if not name:
                raise ValidationError("product line name is required")
            data["name"] = name
        if "description" in payload:
            data["description"] = _clean_text(payload.get("description")) or None
        elif not partial:
            data["description"] = None
        if "is_active" in payload:
            data["is_active"] = bool(payload.get("is_active"))
        elif not partial:
            data["is_active"] = True
        return data

    async def _normalize_sku_payload(self, payload: dict[str, Any], *, partial: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if "product_line_id" in payload or not partial:
            line_id = _clean_text(payload.get("product_line_id"))
            if not line_id:
                raise ValidationError("product_line_id is required")
            await self._require_line(line_id)
            data["product_line_id"] = line_id
        if "code" in payload or not partial:
            code = _clean_text(payload.get("code"))
            if not code:
                raise ValidationError("product SKU code is required")
            data["code"] = code
        if "name" in payload or not partial:
            name = _clean_text(payload.get("name"))
            if not name:
                raise ValidationError("product SKU name is required")
            data["name"] = name
        if "description" in payload:
            data["description"] = _clean_text(payload.get("description")) or None
        elif not partial:
            data["description"] = None
        if "is_active" in payload:
            data["is_active"] = bool(payload.get("is_active"))
        elif not partial:
            data["is_active"] = True
        return data

    async def _normalize_batch_payload(self, payload: dict[str, Any], *, partial: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if "product_sku_id" in payload or not partial:
            sku_id = _clean_text(payload.get("product_sku_id"))
            if not sku_id:
                raise ValidationError("product_sku_id is required")
            await self._require_sku(sku_id)
            data["product_sku_id"] = sku_id
        if "batch_no" in payload or not partial:
            batch_no = _clean_text(payload.get("batch_no"))
            if not batch_no:
                raise ValidationError("batch_no is required")
            data["batch_no"] = batch_no
        if "name" in payload or not partial:
            name = _clean_text(payload.get("name")) or data.get("batch_no")
            data["name"] = name
        if "production_date" in payload:
            data["production_date"] = payload.get("production_date")
        elif not partial:
            data["production_date"] = None
        if "description" in payload:
            data["description"] = _clean_text(payload.get("description")) or None
        elif not partial:
            data["description"] = None
        if "is_active" in payload:
            data["is_active"] = bool(payload.get("is_active"))
        elif not partial:
            data["is_active"] = True
        return data

    @staticmethod
    def _serialize_line(item: ProductLine) -> dict[str, Any]:
        return {
            "id": item.id,
            "org_id": item.org_id,
            "code": item.code,
            "name": item.name,
            "description": _localized_description(item.description),
            "is_active": bool(item.is_active),
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    @classmethod
    def _serialize_sku(cls, item: ProductSku, line: ProductLine | None) -> dict[str, Any]:
        return {
            "id": item.id,
            "org_id": item.org_id,
            "product_line_id": item.product_line_id,
            "product_line_code": line.code if line else None,
            "product_line_name": line.name if line else None,
            "code": item.code,
            "name": item.name,
            "description": _localized_description(item.description),
            "is_active": bool(item.is_active),
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    @classmethod
    def _serialize_batch(
        cls,
        item: ProductBatch,
        sku: ProductSku | None,
        line_map: dict[str, ProductLine],
    ) -> dict[str, Any]:
        line = line_map.get(str(sku.product_line_id)) if sku else None
        return {
            "id": item.id,
            "org_id": item.org_id,
            "product_sku_id": item.product_sku_id,
            "product_sku_code": sku.code if sku else None,
            "product_sku_name": sku.name if sku else None,
            "product_line_id": line.id if line else None,
            "product_line_code": line.code if line else None,
            "product_line_name": line.name if line else None,
            "batch_no": item.batch_no,
            "name": _localized_batch_name(item.name, item.batch_no),
            "production_date": item.production_date,
            "description": _localized_description(item.description),
            "is_active": bool(item.is_active),
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }
