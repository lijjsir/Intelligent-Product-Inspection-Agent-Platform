from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import func, select

from app.core.config import settings
from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)
from app.core.ids import uuid7
from app.models.quality_risk import (
    PhysicalSample,
    ProductCategory,
    ProductIdentifier,
    QualityDataSource,
    QualityEvidenceItem,
    QualityProduct,
    QualityProductionBatch,
    QualityRiskAssessment,
    QualityRiskCase,
    QualitySourceRecord,
    RiskPolicy,
    StandardExecutionRule,
)
from app.services.business_number_service import BusinessNumberService
from app.services.object_storage import build_object_storage
from app.services.quality_intake_support import QualityIntakeMixin
from app.services.quality_foundation_support import QualityFoundationMixin
from app.services.risk_evidence_validation_service import validate_risk,record_definition,evidence_definition
from app.services.knowledge_source_service import fingerprint

BUSINESS_READ = {"admin", "user", "expert", "platform_operator"}
BUSINESS_WRITE = {"admin", "user", "expert"}
_GEOCODE_CACHE: dict[tuple[float, float], dict] = {}
_GEOCODE_LOCK = asyncio.Lock()
_GEOCODE_LAST_REQUEST_AT = 0.0


def stable_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def clean(value: Any) -> str:
    return str(value or "").strip()


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class QualityRiskService(QualityIntakeMixin, QualityFoundationMixin):
    def __init__(self, db, current):
        self.db = db
        self.current = current
        self.org_id = str(current.org_id)
        self.actor = str(current.user_id)
        self.storage = build_object_storage()

    def require_role(self, allowed: set[str]) -> None:
        if self.current.role not in allowed:
            raise ForbiddenError("当前角色无权执行此操作")

    async def flush_and_refresh(self, row) -> None:
        """Flush writes and load database-generated timestamps before serialization."""
        await self.db.flush()
        await self.db.refresh(row)
        await BusinessNumberService(self.db).assign(row)

    async def reverse_geocode(self, latitude: float, longitude: float) -> dict:
        self.require_role(BUSINESS_READ)
        key = (round(latitude, 5), round(longitude, 5))
        cached = _GEOCODE_CACHE.get(key)
        if cached:
            return cached
        if not settings.reverse_geocode_url:
            raise ServiceUnavailableError("地址解析服务尚未配置")
        global _GEOCODE_LAST_REQUEST_AT
        async with _GEOCODE_LOCK:
            cached = _GEOCODE_CACHE.get(key)
            if cached:
                return cached
            remaining = 1.0 - (time.monotonic() - _GEOCODE_LAST_REQUEST_AT)
            if remaining > 0:
                await asyncio.sleep(remaining)
            try:
                async with httpx.AsyncClient(timeout=settings.reverse_geocode_timeout_sec) as client:
                    response = await client.get(
                        settings.reverse_geocode_url,
                        params={
                            "lat": latitude,
                            "lon": longitude,
                            "format": "jsonv2",
                            "addressdetails": 1,
                            "accept-language": "zh-CN,zh",
                            "zoom": 18,
                        },
                        headers={"User-Agent": settings.reverse_geocode_user_agent},
                    )
                    response.raise_for_status()
                    payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise ServiceUnavailableError("当前位置已取得，但地址解析暂时不可用，请手动选择地区") from exc
            finally:
                _GEOCODE_LAST_REQUEST_AT = time.monotonic()
            address = dict(payload.get("address") or {})
            result = {
                "formatted_address": str(payload.get("display_name") or ""),
                "province": str(address.get("state") or address.get("province") or ""),
                "city": str(
                    address.get("city")
                    or address.get("municipality")
                    or address.get("town")
                    or address.get("county")
                    or ""
                ),
                "district": str(
                    address.get("city_district")
                    or address.get("district")
                    or address.get("county")
                    or address.get("suburb")
                    or ""
                ),
                "provider": "OpenStreetMap Nominatim",
            }
            _GEOCODE_CACHE[key] = result
            return result

    async def product_catalog(self, *, include_inactive: bool = False, with_batches: bool = False) -> dict:
        self.require_role(BUSINESS_READ | {"algorithm_engineer"})
        category_stmt = select(ProductCategory).where(ProductCategory.org_id == self.org_id, ProductCategory.deleted_at.is_(None))
        product_stmt = select(QualityProduct).where(QualityProduct.org_id == self.org_id, QualityProduct.deleted_at.is_(None))
        if not include_inactive:
            category_stmt = category_stmt.where(ProductCategory.is_active.is_(True))
            product_stmt = product_stmt.where(QualityProduct.is_active.is_(True))
        categories = list(await self.db.scalars(category_stmt.order_by(ProductCategory.code)))
        products = list(await self.db.scalars(product_stmt.order_by(QualityProduct.name)))
        await BusinessNumberService(self.db).attach(categories)
        await BusinessNumberService(self.db).attach(products)
        category_map = {x.id: x.name for x in categories}
        from app.models.supervision import SupervisionRecord
        manufacturer_ids = {x.manufacturer_enterprise_id for x in products if x.manufacturer_enterprise_id}
        manufacturers = dict((row.id, row.name) for row in await self.db.scalars(select(SupervisionRecord).where(
            SupervisionRecord.org_id == self.org_id, SupervisionRecord.kind == "enterprises",
            SupervisionRecord.id.in_(manufacturer_ids)))) if manufacturer_ids else {}
        identifiers = list(
            await self.db.scalars(
                select(ProductIdentifier).where(ProductIdentifier.org_id == self.org_id, ProductIdentifier.deleted_at.is_(None))
            )
        )
        by_product: dict[str, list[dict]] = {}
        for item in identifiers:
            by_product.setdefault(item.product_id, []).append(
                {
                    "id": item.id,
                    "identifier_type": item.identifier_type,
                    "identifier_value": item.identifier_value,
                    "source_id": item.source_id,
                }
            )
        batches_by_product: dict[str, list[dict]] = {}
        if with_batches and products:
            batches = list(await self.db.scalars(select(QualityProductionBatch).where(
                QualityProductionBatch.org_id == self.org_id,
                QualityProductionBatch.product_id.in_([item.id for item in products]),
                QualityProductionBatch.deleted_at.is_(None)).order_by(
                    QualityProductionBatch.created_at.desc(), QualityProductionBatch.id.desc())))
            await BusinessNumberService(self.db).attach(batches)
            for batch in batches:
                batches_by_product.setdefault(batch.product_id, []).append(self.batch_response(batch))
        return {
            "categories": [self.category_response(x) for x in categories],
            "products": [{**self.product_response(x, category_map.get(x.category_id), by_product.get(x.id, [])),
                          "manufacturer_enterprise_name": manufacturers.get(x.manufacturer_enterprise_id),
                          **({"batches": batches_by_product.get(x.id, [])} if with_batches else {})} for x in products],
        }

    async def create_category(self, payload) -> dict:
        self.require_role({"admin"})
        name, basis = self.category_definition(payload.name, payload.classification_basis)
        if payload.parent_id:
            raise ValidationError("首版类别采用平级目录，不设置上级类别")
        from app.models.organization import Organization
        # Serialize registration per tenant, including simultaneous first-product saves.
        if not await self.db.scalar(select(Organization.id).where(Organization.id == self.org_id).with_for_update()):
            raise NotFoundError("组织不存在")
        row = await self.db.scalar(select(ProductCategory).where(ProductCategory.org_id == self.org_id,
            ProductCategory.name == name, ProductCategory.deleted_at.is_(None)).order_by(ProductCategory.created_at, ProductCategory.id).with_for_update())
        if row:
            if not row.classification_basis:
                row.classification_basis = basis
            if payload.is_active and not row.is_active:
                row.is_active = True
                await self.flush_and_refresh(row)
            else:
                await self.db.flush()
                await BusinessNumberService(self.db).attach([row])
            return self.category_response(row)
        if payload.code and await self.db.scalar(select(ProductCategory.id).where(ProductCategory.org_id == self.org_id,
            ProductCategory.code == payload.code).with_for_update()):
            raise ConflictError("产品类别编码已存在")
        data = payload.model_dump()
        data["name"] = name
        data["classification_basis"] = basis
        data["code"] = data.get("code") or f"FL-{uuid7().hex}"
        row = ProductCategory(org_id=self.org_id, **data)
        self.db.add(row)
        await self.flush_and_refresh(row)
        return self.category_response(row)

    @staticmethod
    def category_definition(name, basis=None):
        import unicodedata
        name = unicodedata.normalize("NFKC", str(name or "")).strip()
        if not name or len(name) > 128 or not any(char.isalpha() for char in name) or any(unicodedata.category(char) == "Cc" for char in name):
            raise ValidationError("请填写有效的类别名称，不能仅填写编号或符号")
        basis = str(basis or "").strip() or None
        if basis and len(basis) > 2000:
            raise ValidationError("分类依据不能超过2000字")
        return name, basis

    async def update_category(self, category_id: str, payload) -> dict:
        self.require_role({"admin"})
        from app.models.organization import Organization
        await self.db.scalar(select(Organization.id).where(Organization.id == self.org_id).with_for_update())
        row = await self.category(category_id)
        data = payload.model_dump(exclude_unset=True)
        if "name" in data or "classification_basis" in data:
            name, basis = self.category_definition(data.get("name", row.name), data.get("classification_basis", row.classification_basis))
            duplicate = await self.db.scalar(select(ProductCategory.id).where(ProductCategory.org_id == self.org_id,
                ProductCategory.name == name, ProductCategory.id != row.id, ProductCategory.deleted_at.is_(None)).with_for_update())
            if duplicate:
                raise ConflictError("同名类别已存在，请使用已有类别")
            data.update(name=name, classification_basis=basis)
        if data.get("parent_id"):
            raise ValidationError("首版类别采用平级目录，不设置上级类别")
        if data.get("parent_id") == row.id:
            raise ValidationError("产品类别不能成为自己的上级")
        for key, value in data.items():
            setattr(row, key, value)
        await self.flush_and_refresh(row)
        return self.category_response(row)

    async def category(self, category_id: str) -> ProductCategory:
        row = await self.db.scalar(select(ProductCategory).where(ProductCategory.id == category_id, ProductCategory.org_id == self.org_id, ProductCategory.deleted_at.is_(None)).with_for_update(read=True))
        if not row:
            raise NotFoundError("产品类别不存在")
        await BusinessNumberService(self.db).attach([row])
        return row

    async def create_product(self, payload) -> dict:
        self.require_role({"admin"})
        await self.validate_manufacturer(payload.manufacturer_enterprise_id)
        async with self.db.begin_nested():
            category = await self.resolve_product_category(payload.category_id)
            data = payload.model_dump(exclude={"identifiers", "initial_batch"})
            data["category_id"] = category.id
            data["model"] = clean(data.get("model")) or None
            data["brand"] = clean(data.get("brand")) or None
            await self.check_product_duplicate(category.id, data["name"], data["model"], data["brand"], data["manufacturer_enterprise_id"])
            row = QualityProduct(org_id=self.org_id, **data)
            self.db.add(row)
            await self.db.flush()
            await BusinessNumberService(self.db).assign(row)
            identifiers = await self.replace_identifiers(row.id, payload.identifiers)
            if payload.initial_batch and (
                payload.initial_batch.original_batch_no or payload.initial_batch.production_date
            ):
                await self.save_production_batch(row.id, payload.initial_batch)
            await self.db.refresh(row)
            result = self.product_response(row, category.name, identifiers)
        return result

    async def resolve_product_category(self, category_id=None):
        if not category_id:
            raise ValidationError("请选择产品类别")
        row = await self.db.scalar(select(ProductCategory).where(ProductCategory.id == category_id,
            ProductCategory.org_id == self.org_id, ProductCategory.deleted_at.is_(None)).with_for_update())
        if not row or not row.is_active:
            raise ValidationError("产品类别不存在或未启用")
        return row

    async def check_product_duplicate(self, category_id, name, model, brand=None, manufacturer=None, exclude_id=None):
        stmt = select(QualityProduct.id).where(QualityProduct.org_id == self.org_id,
            QualityProduct.category_id == category_id, QualityProduct.name == name,
            QualityProduct.model == model, QualityProduct.brand == brand,
            QualityProduct.manufacturer_enterprise_id == manufacturer, QualityProduct.deleted_at.is_(None))
        if exclude_id:
            stmt = stmt.where(QualityProduct.id != exclude_id)
        duplicate = await self.db.scalar(stmt.with_for_update())
        if duplicate:
            raise ConflictError("该类别下已有名称、品牌、型号和生产企业相同的产品，请查看或编辑已有产品", detail={"existing_product_id": duplicate})

    async def update_product(self, product_id: str, payload) -> dict:
        self.require_role({"admin"})
        async with self.db.begin_nested():
            return await self._update_product(product_id, payload)

    async def _update_product(self, product_id: str, payload) -> dict:
        row = await self.product(product_id)
        data = payload.model_dump(exclude_unset=True, exclude={"identifiers"})
        if data.get("category_id"):
            resolved = await self.resolve_product_category(data["category_id"])
            data["category_id"] = resolved.id
        elif "category_id" in data:
            raise ValidationError("产品类别不能为空")
        if "model" in data:
            data["model"] = clean(data["model"]) or None
        if "brand" in data:
            data["brand"] = clean(data["brand"]) or None
        await self.check_product_duplicate(data.get("category_id") or row.category_id,
            data.get("name") or row.name, data.get("model", row.model), data.get("brand", row.brand),
            data.get("manufacturer_enterprise_id", row.manufacturer_enterprise_id), row.id)
        if "manufacturer_enterprise_id" in data:
            await self.validate_manufacturer(data["manufacturer_enterprise_id"])
        for key, value in data.items():
            setattr(row, key, value)
        identifiers = None
        if payload.identifiers is not None:
            identifiers = await self.replace_identifiers(row.id, payload.identifiers)
        if identifiers is None:
            identifiers = [
                {"id": x.id, "identifier_type": x.identifier_type, "identifier_value": x.identifier_value, "source_id": x.source_id}
                for x in await self.db.scalars(select(ProductIdentifier).where(ProductIdentifier.product_id == row.id, ProductIdentifier.org_id == self.org_id, ProductIdentifier.deleted_at.is_(None)))
            ]
        category = await self.category(row.category_id)
        await self.flush_and_refresh(row)
        return self.product_response(row, category.name, identifiers)

    async def product(self, product_id: str) -> QualityProduct:
        row = await self.db.scalar(select(QualityProduct).where(QualityProduct.id == product_id, QualityProduct.org_id == self.org_id, QualityProduct.deleted_at.is_(None)).with_for_update(read=True))
        if not row:
            raise NotFoundError("产品不存在")
        await BusinessNumberService(self.db).attach([row])
        return row

    async def replace_identifiers(self, product_id: str, identifiers) -> list[dict]:
        existing = list(await self.db.scalars(select(ProductIdentifier).where(ProductIdentifier.product_id == product_id, ProductIdentifier.org_id == self.org_id, ProductIdentifier.deleted_at.is_(None))))
        for row in existing:
            row.deleted_at = utcnow()
        result = []
        for item in identifiers:
            duplicate = await self.db.scalar(select(ProductIdentifier.id).where(ProductIdentifier.org_id == self.org_id, ProductIdentifier.identifier_type == item.identifier_type, ProductIdentifier.identifier_value == item.identifier_value, ProductIdentifier.source_id == item.source_id, ProductIdentifier.deleted_at.is_(None)))
            if duplicate:
                raise ConflictError("产品标识已被其他产品使用")
            row = ProductIdentifier(org_id=self.org_id, product_id=product_id, **item.model_dump())
            self.db.add(row)
            await self.db.flush()
            result.append({"id": row.id, "identifier_type": row.identifier_type, "identifier_value": row.identifier_value, "source_id": row.source_id})
        return result

    async def list_sources(self) -> list[dict]:
        self.require_role(BUSINESS_READ | {"algorithm_engineer", "app_developer"})
        rows = list(await self.db.scalars(select(QualityDataSource).where(QualityDataSource.org_id == self.org_id, QualityDataSource.deleted_at.is_(None)).order_by(QualityDataSource.created_at.desc())))
        await BusinessNumberService(self.db).attach(rows)
        return [self.source_response(x) for x in rows]

    async def create_source(self, payload) -> dict:
        self.require_role({"admin"})
        if await self.db.scalar(select(QualityDataSource.id).where(QualityDataSource.org_id == self.org_id, QualityDataSource.code == payload.code, QualityDataSource.deleted_at.is_(None))):
            raise ConflictError("数据来源编码已存在")
        data = payload.model_dump()
        data["code"] = data.get("code") or f"LY-{uuid7().hex}"
        row = QualityDataSource(org_id=self.org_id, created_by=self.actor, **data)
        self.db.add(row)
        await self.flush_and_refresh(row)
        return self.source_response(row)

    async def update_source(self, source_id: str, payload) -> dict:
        self.require_role({"admin"})
        row = await self.source(source_id)
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(row, key, value)
        await self.flush_and_refresh(row)
        return self.source_response(row)

    async def source(self, source_id: str) -> QualityDataSource:
        row = await self.db.scalar(select(QualityDataSource).where(QualityDataSource.id == source_id, QualityDataSource.org_id == self.org_id, QualityDataSource.deleted_at.is_(None)))
        if not row:
            raise NotFoundError("数据来源不存在")
        await BusinessNumberService(self.db).attach([row])
        return row





    async def record_evidence(self, record_id: str) -> list[dict]:
        self.require_intake()
        await self.record(record_id)
        rows = list(await self.db.scalars(select(QualityEvidenceItem).where(QualityEvidenceItem.org_id == self.org_id, QualityEvidenceItem.source_record_id == record_id, QualityEvidenceItem.deleted_at.is_(None)).order_by(QualityEvidenceItem.created_at)))
        return [self.evidence_response(x) for x in rows]

    async def materialize_evidence(self, record: QualitySourceRecord) -> None:
        text = clean(record.content.get("text") or record.content.get("description") or record.content.get("summary"))
        structured = {k: v for k, v in record.content.items() if k not in {"text", "description", "summary"}}
        items = [(None, text, structured)]
        items.extend((aid, None, {}) for aid in record.attachment_ids)
        for index, (attachment_id, evidence_text, evidence_data) in enumerate(items, 1):
            payload = {"record_id": record.id, "index": index, "text": evidence_text, "data": evidence_data, "attachment_id": attachment_id}
            row = QualityEvidenceItem(
                org_id=self.org_id,
                evidence_code=f"EV-{record.id[-8:].upper()}-{index:02d}",
                source_record_id=record.id,
                evidence_type="attachment" if attachment_id else record.record_type,
                text=evidence_text,
                structured_data=evidence_data,
                attachment_id=attachment_id,
                nature=record.data_nature,
                locator={"source_record_id": record.id, "external_record_id": record.external_record_id},
                content_hash=stable_hash(payload),
            )
            self.db.add(row)
        await self.db.flush()







    async def create_risk_case(self, payload) -> dict:
        self.require_role(BUSINESS_WRITE)
        for record_id in payload.source_record_ids:
            await self.record(record_id)
        record_count = await self.db.scalar(select(func.count()).select_from(QualitySourceRecord).where(QualitySourceRecord.org_id == self.org_id, QualitySourceRecord.id.in_(payload.source_record_ids)))
        if int(record_count or 0) != len(set(payload.source_record_ids)):
            raise ValidationError("风险案件包含不可用来源记录")
        evidence_ids = list(payload.evidence_ids)
        if not evidence_ids:
            evidence_ids = list(await self.db.scalars(select(QualityEvidenceItem.id).where(QualityEvidenceItem.org_id == self.org_id, QualityEvidenceItem.source_record_id.in_(payload.source_record_ids), QualityEvidenceItem.deleted_at.is_(None))))
        row = QualityRiskCase(org_id=self.org_id, code=f"RISK-{str(uuid7())[-12:].upper()}", title=payload.title, scope_type=payload.scope_type, scope=payload.scope, status="collecting", evidence_ids=evidence_ids, source_record_ids=payload.source_record_ids, assigned_to=payload.assigned_to, created_by=self.actor)
        self.db.add(row)
        await self.flush_and_refresh(row)
        return self.risk_case_response(row)

    async def list_risk_cases(self, *, page: int, size: int, status: str | None, keyword: str | None) -> dict:
        self.require_role(BUSINESS_READ)
        stmt = select(QualityRiskCase).where(QualityRiskCase.org_id == self.org_id, QualityRiskCase.deleted_at.is_(None))
        if status:
            stmt = stmt.where(QualityRiskCase.status == status)
        if keyword:
            stmt = stmt.where(QualityRiskCase.title.contains(keyword, autoescape=True))
        total = await self.db.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = list(await self.db.scalars(stmt.order_by(QualityRiskCase.created_at.desc()).offset((page - 1) * size).limit(size)))
        await BusinessNumberService(self.db).attach(rows)
        return {"items": [self.risk_case_response(x) for x in rows], "total": int(total or 0), "page": page, "size": size}

    async def append_risk_sources(self, risk_case_id: str, record_ids: list[str]) -> dict:
        self.require_role(BUSINESS_WRITE)
        await self.lock_demo_intake()
        case = await self.risk_case(risk_case_id, lock=True)
        if self.current.role == "user" and self.actor not in {case.created_by, case.assigned_to}:
            raise ForbiddenError("只能为本人创建或受派的研判事项补充资料")
        for record_id in dict.fromkeys(record_ids):
            await self.record(record_id)
        added = set(record_ids) - set(case.source_record_ids or [])
        evidence = list(await self.db.scalars(select(QualityEvidenceItem.id).where(
                QualityEvidenceItem.org_id == self.org_id,
                QualityEvidenceItem.source_record_id.in_(record_ids),
                QualityEvidenceItem.deleted_at.is_(None),
            )))
        if added or set(evidence) - set(case.evidence_ids or []):
            case.source_record_ids = list(dict.fromkeys([*(case.source_record_ids or []), *record_ids]))
            case.evidence_ids = list(dict.fromkeys([*(case.evidence_ids or []), *evidence]))
            case.status = "awaiting_evidence"
            await self.db.flush()
        return self.risk_case_response(case)

    async def risk_workspace(self, risk_case_id: str) -> dict:
        """Restore a case without regenerating an assessment or widening source access."""
        self.require_role(BUSINESS_READ)
        case = await self.risk_case(risk_case_id)
        records, unavailable = [], []
        for record_id in dict.fromkeys(case.source_record_ids or []):
            try:
                record = await self.record(record_id)
            except (ForbiddenError, NotFoundError):
                unavailable.append(record_id)
                continue
            records.append(self.record_response(record))
        versions = list(await self.db.scalars(
            select(QualityRiskAssessment).where(
                QualityRiskAssessment.org_id == self.org_id,
                QualityRiskAssessment.risk_case_id == case.id,
                QualityRiskAssessment.deleted_at.is_(None),
            ).order_by(QualityRiskAssessment.version.desc())
        ))
        latest = await self.get_assessment(versions[0].id) if versions else None
        result = {
            "case": self.risk_case_response(case),
            "records": records,
            "unavailable_source_ids": unavailable,
            "latest_assessment": latest,
            "assessment_versions": [
                {key: getattr(row, key) for key in (
                    "id", "version", "status", "risk_level", "created_at", "reviewed_at",
                )} for row in versions
            ],
        }
        if settings.quality_demo_enabled and str(self.current.role) in {"admin", "expert"}:
            from app.services.demo_risk_workflow_service import DemoRiskWorkflowService
            result["demo_context"] = await DemoRiskWorkflowService(self.db, self.current, self.storage).context(case)
        if str(self.current.role) == "expert":
            from app.services.risk_workflow_context_service import RiskWorkflowContextService
            try:
                result["workflow_context"] = await RiskWorkflowContextService(self.db, self.current, self.storage).context(case)
            except ForbiddenError as exc:
                # Existing read access survives when optional supervision workflows are disabled.
                result["workflow_context"] = {'enabled':False, 'execution_mode':'demo' if settings.quality_demo_enabled else 'business',
                    'can_author':False, 'eligible':False, 'assessment_id':None, 'basis_hash':'',
                    'blockers':[{'message':exc.message}], 'boundary':exc.message}
        return result

    async def analyze_risk(self, risk_case_id: str, payload) -> dict:
        self.require_role({"user", "expert"})
        if settings.quality_demo_enabled:
            raise ValidationError("演示环境请使用人工演示草稿入口；此操作不会调用真实模型")
        case = await self.risk_case(risk_case_id, lock=True)
        if case.scope.get("execution_mode") == "demo":
            raise ValidationError("演示事项不能进入正式模型研判流程")
        evidence = list(await self.db.scalars(select(QualityEvidenceItem).where(QualityEvidenceItem.org_id == self.org_id, QualityEvidenceItem.id.in_(case.evidence_ids), QualityEvidenceItem.deleted_at.is_(None))))
        observed = [x for x in evidence if x.nature == "observed"]
        records = list(await self.db.scalars(select(QualitySourceRecord).where(QualitySourceRecord.org_id == self.org_id, QualitySourceRecord.id.in_(case.source_record_ids),QualitySourceRecord.deleted_at.is_(None))))
        policy = None
        if payload.policy_id:
            policy = await self.db.scalar(select(RiskPolicy).where(RiskPolicy.id == payload.policy_id, RiskPolicy.org_id == self.org_id, RiskPolicy.status == "published"))
            if not policy:
                raise ValidationError("风险政策不存在或尚未发布")
        explicit_levels = [clean(x.content.get("risk_level")) for x in records if clean(x.content.get("risk_level")) in {"low", "medium", "high", "critical"}]
        level = max(explicit_levels, key=lambda x: {"low": 1, "medium": 2, "high": 3, "critical": 4}[x]) if explicit_levels else "unknown"
        types = [clean(x.content.get("risk_type")) for x in records if clean(x.content.get("risk_type"))]
        causes = [clean(c) for x in records for c in (x.content.get("possible_causes") or []) if clean(c)]
        recommendations = [clean(c) for x in records for c in (x.content.get("recommendations") or []) if clean(c)]
        model_versions = {}
        model_call = None
        opinion_records = [
            x
            for x in records
            if x.record_type in {"consumer_complaint", "public_opinion", "image", "video"}
        ]
        occurred_times = [r.occurred_at for r in opinion_records if r.occurred_at is not None]
        record_times = {r.id: r.occurred_at for r in records}
        if opinion_records:
            try:
                from app.services.supervision_service import SupervisionService

                supervision = SupervisionService(self.db, self.current)
                model_call = await supervision.model_call(case.id)
                output = await supervision.execute_agent_via_manager(
                    {
                        "id": case.id,
                        "kind": "risk-case",
                        "version": 1,
                        "as_of": utcnow().isoformat(),
                        "knowledge_snapshot_id": stable_hash(
                            {"records": [x.content_hash for x in opinion_records]}
                        ),
                        "standard": None,
                        "data": {
                            "product_category": case.scope.get("name")
                            if case.scope_type == "category"
                            else case.scope.get("product_category"),
                            "description": "\n".join(
                                clean(x.content.get("text") or x.content.get("description"))
                                for x in opinion_records
                            ),
                            "occurred_at": max(occurred_times).isoformat() if occurred_times else None,
                            "evidence": [
                                {
                                    "evidence_id": x.id,
                                    "source_type": "image"
                                    if x.evidence_type == "attachment"
                                    else x.evidence_type,
                                    "source_id": x.source_record_id,
                                    "occurred_at": record_times[x.source_record_id].isoformat() if record_times.get(x.source_record_id) else None,
                                    "text": x.text or "多媒体来源证据",
                                    "nature": x.nature,
                                }
                                for x in observed
                            ],
                        },
                    },
                    "public_opinion_monitoring",
                    workflow_run_id=case.id,
                    model_call=model_call,
                )
                agent_level = clean(output.get("risk_level"))
                if agent_level in {"low", "medium", "high", "critical"}:
                    level = agent_level
                signals = [clean(x) for x in output.get("normalized_signals", []) if clean(x)]
                if signals and not types:
                    types = signals
                causes.extend(clean(x) for x in output.get("possible_causes", []) if clean(x))
                recommendations.extend(
                    clean(x) for x in output.get("recommendations", []) if clean(x)
                )
                model_versions = {**dict(output.get("model_versions") or {}), 'analysis_summary':{
                    'summary':str(output.get('summary') or ''),
                    'limitations':list(output.get('limitations') or []),
                }, 'inference_status': output.get('status')}
            except Exception:  # noqa: BLE001 - model/provider failures must degrade to review
                model_versions = {"status": "unavailable_or_manual_review_required"}
        if model_call is not None:
            model_versions.update(getattr(model_call, 'model_versions', {}))
        model_versions.setdefault("llm_called", False)
        model_versions.setdefault("model_success", False)
        execution_context = None
        if payload.inspection_execution_run_id:
            from app.services.inspection_execution_service import InspectionExecutionService

            execution_service = InspectionExecutionService(self.db, self.current)
            execution = await execution_service.get(payload.inspection_execution_run_id)
            execution_issues = await execution_service.validity(execution)
            execution_context = {
                "kind": "inspection_execution",
                "run_id": execution.id,
                "status": execution.status,
                "row_version": execution.row_version,
                "current_source_issues": execution_issues,
                "evaluation": execution.evaluation,
                "source_refs": execution.snapshot.get("source_refs", []),
                "observation_refs": [
                    {
                        "evidence_id": item.get("evidence_id"),
                        "kind": item.get("kind"),
                        "measurement_key": item.get("measurement_key"),
                        "sample_id": item.get("sample_id"),
                    }
                    for item in execution.snapshot.get("observations", [])
                ],
            }
        missing = [] if observed else ["真实来源证据"]
        if any(r.occurred_at is None for r in opinion_records):
            missing.append("部分投诉或舆情来源缺少发生时间，时序关系仍需核对")
        if execution_context:
            if execution_context["status"] != "accepted":
                missing.append("引用的标准执行结果尚未完成独立专业复核")
            if execution_context["current_source_issues"]:
                missing.extend(execution_context["current_source_issues"])
            model_versions["inspection_execution"] = {
                "run_id": execution_context["run_id"],
                "status": execution_context["status"],
                "item_verdict": execution_context["evaluation"].get("item_verdict"),
                "product_verdict": execution_context["evaluation"].get("product_verdict"),
                "risk_level": execution_context["evaluation"].get("risk_level", "unknown"),
            }
        if policy:
            minimum = float((policy.rules.get("evidence_sufficiency") or {}).get("minimum") or 0)
            sufficiency = len(observed) / len(evidence) if evidence else 0.0
            if sufficiency < minimum:
                missing.append(f"证据充分度未达到政策门槛（当前{sufficiency:.0%}，要求{minimum:.0%}）")
        if level == "unknown":
            missing.append("经规则或专家确认的风险等级")
        model_versions["evidence_basis"]={"evidence_ids":[e.id for e in evidence],"records":{r.id:record_definition(r) for r in records},
            "evidence":{e.id:evidence_definition(e) for e in evidence}}
        if policy:model_versions["risk_policy_basis"]={"id":policy.id,"version":policy.version,"rules_hash":fingerprint(policy.rules)}
        latest = await self.db.scalar(select(func.max(QualityRiskAssessment.version)).where(QualityRiskAssessment.org_id == self.org_id, QualityRiskAssessment.risk_case_id == case.id))
        from app.services.standard_execution_context_service import published_standard_context
        category=case.scope.get("name") if case.scope_type=="category" else case.scope.get("product_category")
        standard_matches=await published_standard_context(self.db,self.org_id,product_category=category) if category else []
        unresolved=[{"revision_id":match["revision_id"],"conflict":"适用条件或版本尚需专业确认"} for match in standard_matches if not match.get("applicability")]
        if execution_context:
            standard_matches.append(execution_context)
        assessment = QualityRiskAssessment(org_id=self.org_id, risk_case_id=case.id, version=int(latest or 0) + 1, risk_type=types[0] if types else None, risk_level=level, scope=case.scope, evidence_ids=[x.id for x in observed], standard_matches=[], conflicts=[], missing_inputs=missing, possible_causes=list(dict.fromkeys(causes)), recommendations=list(dict.fromkeys(recommendations)), trust_status="needs_review", probability=None, model_versions=model_versions, policy_version=policy.version if policy else None, knowledge_snapshot_id=stable_hash({"records": [(x.id, x.updated_at) for x in records], "evidence": [x.content_hash for x in evidence], "inspection_execution": execution_context}), status="awaiting_evidence" if missing else "awaiting_review", submitted_by=self.actor)
        assessment.standard_matches=standard_matches;assessment.conflicts=unresolved
        self.db.add(assessment)
        await self.db.flush()
        validation=await validate_risk(self.db,self.current,case,assessment,self.storage,freeze_sources=True)
        basis={**assessment.model_versions["evidence_basis"],"attachment_hashes":{s["attachment_id"]:s["sha256"] for s in validation["sources"] if s.get("attachment_id")}}
        assessment.model_versions={**assessment.model_versions,"evidence_basis":basis,"source_validation":validation}
        if validation["blockers"]:
            assessment.missing_inputs=list(dict.fromkeys([*assessment.missing_inputs,*[b["message"] for b in validation["blockers"]]]))
            assessment.status="awaiting_evidence"
        case.status = assessment.status
        await self.flush_and_refresh(assessment)
        return self.assessment_response(assessment)

    async def review_risk(self, risk_case_id: str, payload) -> dict:
        self.require_role({"expert"})
        if settings.quality_demo_enabled and payload.decision == "accept":
            raise ValidationError("演示环境不能确认正式风险结论；后续演示复核将使用独立状态")
        case = await self.risk_case(risk_case_id, lock=True)
        assessment = await self.db.scalar(select(QualityRiskAssessment).where(QualityRiskAssessment.org_id == self.org_id, QualityRiskAssessment.risk_case_id == case.id).order_by(QualityRiskAssessment.version.desc()).limit(1).with_for_update())
        if not assessment:
            raise ValidationError("请先生成风险研判草稿")
        if (assessment.model_versions or {}).get("execution_mode") == "demo" or case.scope.get("execution_mode") == "demo":
            raise ValidationError("演示版本请使用独立演示复核入口，不能转为正式确认")
        if payload.assessment_id and payload.assessment_id != assessment.id:
            raise ConflictError("研判版本已更新，请刷新并核对最新草稿后复核")
        if assessment.submitted_by == self.actor:
            raise ForbiddenError("不能复核本人提交的风险研判")
        if assessment.status=="accepted":raise ConflictError("已确认研判不能静默覆盖，请重新生成草稿")
        if not payload.comment.strip():raise ValidationError("请填写有效复核意见")
        validation=await validate_risk(self.db,self.current,case,assessment,self.storage)
        if payload.decision == "accept":
            if validation["blockers"]:
                raise ValidationError("真实来源或引用依据未通过核验，不能确认风险研判",detail={"blockers":validation["blockers"]})
            if assessment.risk_level == "unknown" and not payload.risk_level:
                raise ValidationError("通过研判前必须由专家确认风险等级")
            assessment.risk_level = payload.risk_level or assessment.risk_level
            assessment.risk_type = payload.risk_type or assessment.risk_type
            if payload.possible_causes is not None:
                assessment.possible_causes = payload.possible_causes
            if payload.recommendations is not None:
                assessment.recommendations = payload.recommendations
        assessment.reviewed_by = self.actor
        assessment.reviewed_at = utcnow()
        assessment.review_comment = payload.comment
        assessment.model_versions={**assessment.model_versions,"source_validation":validation,
            "review_verification":{"actor_id":self.actor,"decision":payload.decision,"comment":payload.comment,
                "checked_at":validation["checked_at"],"validation":validation}}
        if payload.decision=="accept":
            assessment.missing_inputs=[m for m in assessment.missing_inputs if m!="经规则或专家确认的风险等级"]
        assessment.trust_status = "verified" if payload.decision == "accept" else "needs_evidence"
        assessment.status = "accepted" if payload.decision == "accept" else payload.decision
        case.status = "risk_assessed" if payload.decision == "accept" else "awaiting_evidence"
        await self.flush_and_refresh(assessment)
        return self.assessment_response(assessment)

    async def get_assessment(self, assessment_id: str) -> dict:
        self.require_role(BUSINESS_READ)
        row = await self.db.scalar(select(QualityRiskAssessment).where(QualityRiskAssessment.id == assessment_id, QualityRiskAssessment.org_id == self.org_id, QualityRiskAssessment.deleted_at.is_(None)))
        if not row:
            raise NotFoundError("风险研判不存在")
        case=await self.risk_case(row.risk_case_id)
        from app.services.demo_risk_workflow_service import is_manual_demo, DemoRiskWorkflowService
        if is_manual_demo(row):
            workflow = DemoRiskWorkflowService(self.db, self.current, self.storage)
            await workflow.guard()
            return await workflow.respond(case, row)
        response=self.assessment_response(row)
        response["source_validation"]=await validate_risk(self.db,self.current,case,row,self.storage)
        response["effective_status"]="needs_reassessment" if response["source_validation"]["blockers"] else row.status
        return response

    async def risk_case(self, risk_case_id: str, *, lock: bool = False) -> QualityRiskCase:
        stmt = select(QualityRiskCase).where(QualityRiskCase.id == risk_case_id, QualityRiskCase.org_id == self.org_id, QualityRiskCase.deleted_at.is_(None))
        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        row = await self.db.scalar(stmt)
        if not row:
            raise NotFoundError("风险案件不存在")
        await BusinessNumberService(self.db).attach([row])
        return row

    async def list_policies(self) -> list[dict]:
        self.require_role(BUSINESS_READ)
        rows = list(await self.db.scalars(select(RiskPolicy).where(RiskPolicy.org_id == self.org_id, RiskPolicy.deleted_at.is_(None)).order_by(RiskPolicy.created_at.desc())))
        await BusinessNumberService(self.db).attach(rows)
        return [self.policy_response(x) for x in rows]

    async def create_policy(self, payload) -> dict:
        self.require_role({"admin", "expert"})
        duplicate = await self.db.scalar(
            select(RiskPolicy.id).where(
                RiskPolicy.org_id == self.org_id,
                RiskPolicy.code == payload.code,
                RiskPolicy.version == payload.version,
                RiskPolicy.deleted_at.is_(None),
            )
        )
        if duplicate:
            raise ConflictError("相同政策编码和版本已存在")
        row = RiskPolicy(org_id=self.org_id, code=payload.code or f"GZ-{uuid7().hex}", name=payload.name, version=payload.version, rules=payload.rules, status="draft", created_by=self.actor)
        self.db.add(row)
        await self.flush_and_refresh(row)
        return self.policy_response(row)

    async def publish_policy(self, policy_id: str) -> dict:
        self.require_role({"admin"})
        row = await self.db.scalar(select(RiskPolicy).where(RiskPolicy.id == policy_id, RiskPolicy.org_id == self.org_id, RiskPolicy.deleted_at.is_(None)).with_for_update())
        if not row:
            raise NotFoundError("风险政策不存在")
        previous = list(
            await self.db.scalars(
                select(RiskPolicy).where(
                    RiskPolicy.org_id == self.org_id,
                    RiskPolicy.code == row.code,
                    RiskPolicy.status == "published",
                    RiskPolicy.id != row.id,
                    RiskPolicy.deleted_at.is_(None),
                )
            )
        )
        for item in previous:
            item.status = "superseded"
        row.status = "published"
        row.published_by = self.actor
        row.published_at = utcnow()
        await self.flush_and_refresh(row)
        return self.policy_response(row)

    async def list_standard_rules(self) -> list[dict]:
        self.require_role(BUSINESS_READ | {"app_developer"})
        rows = list(
            await self.db.scalars(
                select(StandardExecutionRule)
                .where(
                    StandardExecutionRule.org_id == self.org_id,
                    StandardExecutionRule.deleted_at.is_(None),
                )
                .order_by(StandardExecutionRule.created_at.desc())
            )
        )
        await BusinessNumberService(self.db).attach(rows)
        return [self.standard_rule_response(x) for x in rows]

    async def create_standard_rule(self, payload) -> dict:
        self.require_role({"admin", "expert"})
        from app.models.inspection_standard_library import InspectionStandardLibrary

        standard = await self.db.scalar(
            select(InspectionStandardLibrary).where(
                InspectionStandardLibrary.id == payload.standard_id,
                InspectionStandardLibrary.is_active.is_(True),
                InspectionStandardLibrary.deleted_at.is_(None),
                (InspectionStandardLibrary.org_id == self.org_id)
                | (InspectionStandardLibrary.org_id.is_(None)),
            )
        )
        if not standard:
            raise ValidationError("检测标准不存在或未启用")
        duplicate = await self.db.scalar(
            select(StandardExecutionRule.id).where(
                StandardExecutionRule.org_id == self.org_id,
                StandardExecutionRule.code == payload.code,
                StandardExecutionRule.version == payload.version,
                StandardExecutionRule.deleted_at.is_(None),
            )
        )
        if duplicate:
            raise ConflictError("相同判定条件编码和版本已存在")
        if payload.category_id:
            await self.category(payload.category_id)
        if payload.product_id:
            product = await self.product(payload.product_id)
            if payload.category_id and product.category_id != payload.category_id:
                raise ValidationError("规则产品不属于所选类别")
        row = StandardExecutionRule(
            org_id=self.org_id,
            created_by=self.actor,
            status="draft",
            **{**payload.model_dump(), "code": payload.code or f"GZ-{uuid7().hex}"},
        )
        self.db.add(row)
        await self.flush_and_refresh(row)
        return self.standard_rule_response(row)

    async def publish_standard_rule(self, rule_id: str) -> dict:
        self.require_role({"admin"})
        row = await self.db.scalar(
            select(StandardExecutionRule)
            .where(
                StandardExecutionRule.id == rule_id,
                StandardExecutionRule.org_id == self.org_id,
                StandardExecutionRule.deleted_at.is_(None),
            )
            .with_for_update()
        )
        if not row:
            raise NotFoundError("标准执行规则不存在")
        if not row.clause_ref or not row.condition:
            raise ValidationError("规则缺少标准条款或执行条件")
        previous = list(
            await self.db.scalars(
                select(StandardExecutionRule).where(
                    StandardExecutionRule.org_id == self.org_id,
                    StandardExecutionRule.code == row.code,
                    StandardExecutionRule.status == "published",
                    StandardExecutionRule.id != row.id,
                    StandardExecutionRule.deleted_at.is_(None),
                )
            )
        )
        for item in previous:
            item.status = "superseded"
        row.status = "published"
        row.reviewed_by = row.reviewed_by or self.actor
        row.published_by = self.actor
        row.published_at = utcnow()
        await self.flush_and_refresh(row)
        return self.standard_rule_response(row)

    async def list_physical_samples(self, sampling_plan_id: str | None = None) -> list[dict]:
        self.require_role(BUSINESS_READ)
        stmt = select(PhysicalSample).where(
            PhysicalSample.org_id == self.org_id,
            PhysicalSample.deleted_at.is_(None),
        )
        if sampling_plan_id:
            stmt = stmt.where(PhysicalSample.sampling_plan_id == sampling_plan_id)
        rows = list(await self.db.scalars(stmt.order_by(PhysicalSample.created_at.desc())))
        await BusinessNumberService(self.db).attach(rows)
        return [self.physical_sample_response(x) for x in rows]

    async def create_physical_sample(self, payload) -> dict:
        self.require_role({"user", "expert"})
        from app.models.organization import Organization
        from app.models.supervision import SupervisionRecord

        organization = await self.db.get(Organization, self.org_id)
        if not organization or not (organization.settings or {}).get(
            "laboratory_validation_enabled", False
        ):
            raise ForbiddenError("当前组织尚未启用实验室验证")
        plan = await self.db.scalar(
            select(SupervisionRecord).where(
                SupervisionRecord.id == payload.sampling_plan_id,
                SupervisionRecord.org_id == self.org_id,
                SupervisionRecord.kind == "sampling-plans",
                SupervisionRecord.status == "approved",
            )
        )
        if not plan:
            raise ValidationError("实物样品必须来自已批准监督抽查计划")
        from app.services.supervision_service import SupervisionService

        await SupervisionService(self.db, self.current).sampling_analysis_contexts(plan)
        if payload.product_id:
            await self.product(payload.product_id)
        row = PhysicalSample(
            org_id=self.org_id,
            sampling_plan_id=payload.sampling_plan_id,
            product_id=payload.product_id,
            production_batch_ref=payload.production_batch_ref,
            external_sample_code=payload.external_sample_code,
            unit_serial_ref=payload.unit_serial_ref,
            sampled_at=payload.sampled_at,
            sampling_location=payload.sampling_location.model_dump(
                mode="json", exclude_none=True
            ),
            custody_status="collected" if payload.sampled_at else "planned",
        )
        self.db.add(row)
        await self.flush_and_refresh(row)
        return self.physical_sample_response(row)




    @staticmethod
    def category_response(x) -> dict:
        return {"display_no": getattr(x, "display_no", None), **{k: getattr(x, k) for k in ("id", "org_id", "code", "name", "classification_basis", "parent_id", "description", "is_active", "created_at", "updated_at")}}

    @staticmethod
    def product_response(x, category_name, identifiers) -> dict:
        return {"display_no": getattr(x, "display_no", None), **{k: getattr(x, k) for k in ("id", "org_id", "category_id", "name", "model", "brand", "manufacturer_enterprise_id", "attributes", "is_active", "created_at", "updated_at")}, "category_name": category_name, "identifiers": identifiers}

    @staticmethod
    def source_response(x) -> dict:
        return {"display_no": getattr(x, "display_no", None), **{k: getattr(x, k) for k in ("id", "org_id", "code", "name", "source_type", "connector_type", "config", "status", "created_by", "created_at", "updated_at")}}

    @staticmethod
    def record_response(x) -> dict:
        return {"display_no": getattr(x, "display_no", None), **{k: getattr(x, k) for k in ("id", "org_id", "source_id", "ingestion_job_id", "external_record_id", "record_type", "occurred_at", "received_at", "content", "content_hash", "enterprise_ref", "product_ref", "location", "attachment_ids", "provenance", "authorization_scope", "data_nature", "normalization_status", "normalization_errors", "created_by", "created_at")}}

    def attachment_response(self, x) -> dict:
        return {"id": x.id, "file_name": x.file_name, "mime_type": x.mime_type, "size_bytes": x.size_bytes, "sha256": x.sha256, "download_url": f"/api/v1/quality-data/attachments/{x.id}/download"}

    @staticmethod
    def evidence_response(x) -> dict:
        return {"display_no": getattr(x, "display_no", None), **{k: getattr(x, k) for k in ("id", "evidence_code", "source_record_id", "evidence_type", "text", "structured_data", "attachment_id", "nature", "locator", "content_hash", "created_at")}}

    @staticmethod
    def ingestion_response(x) -> dict:
        return {"display_no": getattr(x, "display_no", None), **x.raw_payload.get("outcome", {}), "source_columns": x.raw_payload.get("source_columns", []), "mapping": x.mapping, "id": x.id, "source_id": x.source_id, "request_key": x.request_key, "import_batch_code": x.import_batch_code, "status": x.status, "file_name": x.file_name, "total_count": x.total_count, "valid_count": x.valid_count, "error_count": x.error_count, "errors": x.errors, "preview_rows": x.raw_payload.get("rows", [])[:100]}

    @staticmethod
    def risk_case_response(x) -> dict:
        return {"display_no": getattr(x, "display_no", None), **{k: getattr(x, k) for k in ("id", "org_id", "code", "title", "scope_type", "scope", "status", "evidence_ids", "source_record_ids", "assigned_to", "created_by", "created_at", "updated_at")}}

    @staticmethod
    def assessment_response(x) -> dict:
        validation=(x.model_versions or {}).get("source_validation") or {}
        return {"display_no": getattr(x, "display_no", None),"source_validation":validation,
            "effective_status":"needs_reassessment" if validation.get("blockers") else x.status,
            **{k: getattr(x, k) for k in ("id", "org_id", "risk_case_id", "version", "risk_type", "risk_level", "scope", "evidence_ids", "standard_matches", "conflicts", "missing_inputs", "possible_causes", "recommendations", "trust_status", "probability", "model_versions", "policy_version", "knowledge_snapshot_id", "status", "submitted_by", "reviewed_by", "reviewed_at", "review_comment", "created_at")}}

    @staticmethod
    def policy_response(x) -> dict:
        return {"display_no": getattr(x, "display_no", None), **{k: getattr(x, k) for k in ("id", "org_id", "code", "name", "version", "rules", "status", "created_by", "published_by", "published_at", "created_at")}}

    @staticmethod
    def standard_rule_response(x) -> dict:
        return {"display_no": getattr(x, "display_no", None), **{
            k: getattr(x, k)
            for k in (
                "id",
                "org_id",
                "code",
                "name",
                "version",
                "standard_id",
                "clause_ref",
                "page_ref",
                "category_id",
                "product_id",
                "indicator",
                "method",
                "unit",
                "condition",
                "decision_action",
                "review_policy",
                "status",
                "created_by",
                "reviewed_by",
                "published_by",
                "published_at",
                "created_at",
            )
        }}

    @staticmethod
    def physical_sample_response(x) -> dict:
        return {"display_no": getattr(x, "display_no", None), **{
            k: getattr(x, k)
            for k in (
                "id",
                "org_id",
                "sampling_plan_id",
                "product_id",
                "production_batch_ref",
                "external_sample_code",
                "unit_serial_ref",
                "sampled_at",
                "sampling_location",
                "custody_status",
                "created_at",
            )
        }}
