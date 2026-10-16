"""Small product/batch registry used by the administrator's foundation pages."""
from sqlalchemy import String, or_, select
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.quality_risk import (
    EnterpriseProductRelation, PhysicalSample, ProductCategory, ProductIdentifier,
    QualityProduct, QualityProductionBatch, QualityRiskCase, QualityRiskAssessment,
    QualitySourceRecord, RiskPolicy, StandardExecutionRule,
)
from app.models.supervision import SupervisionRecord
from app.services.business_number_service import BusinessNumberService


class QualityFoundationMixin:
    async def product_candidates(self, category_id, name, brand=None, model=None, manufacturer=None, exclude_id=None):
        """Offer possible matches; never merge records merely because information is sparse."""
        self.require_role({"admin"})
        from difflib import SequenceMatcher
        import re
        import unicodedata
        def normalized(value):
            return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", str(value or "")).casefold())
        query_name = normalized(name)
        if len(query_name) < 2:
            return []
        stmt = select(QualityProduct).where(QualityProduct.org_id == self.org_id,
            QualityProduct.category_id == category_id, QualityProduct.deleted_at.is_(None), QualityProduct.is_active.is_(True))
        if exclude_id:
            stmt = stmt.where(QualityProduct.id != exclude_id)
        fragments = {str(name).strip(), str(name).strip()[:2], str(name).strip()[-2:]}
        stmt = stmt.where(or_(*[QualityProduct.name.contains(fragment, autoescape=True) for fragment in fragments if len(fragment) >= 2]))
        rows = list(await self.db.scalars(stmt.order_by(QualityProduct.updated_at.desc()).limit(500)))
        matches = []
        for row in rows:
            incoming = {"brand": brand, "model": model, "manufacturer_enterprise_id": manufacturer}
            if any(value and getattr(row, key) and normalized(value) != normalized(getattr(row, key)) for key, value in incoming.items()):
                continue
            score = SequenceMatcher(None, query_name, normalized(row.name)).ratio()
            if score < .6 and query_name not in normalized(row.name) and normalized(row.name) not in query_name:
                continue
            missing = [label for key, label in [("brand", "品牌"), ("model", "型号"), ("manufacturer_enterprise_id", "生产企业")]
                       if not getattr(row, key)]
            matches.append((score, row, missing))
        matches.sort(key=lambda value: value[0], reverse=True)
        matches = matches[:5]
        await BusinessNumberService(self.db).attach([item[1] for item in matches])
        manufacturer_ids = {item[1].manufacturer_enterprise_id for item in matches if item[1].manufacturer_enterprise_id}
        names = {row.id: row.name for row in await self.db.scalars(select(SupervisionRecord).where(
            SupervisionRecord.org_id == self.org_id, SupervisionRecord.id.in_(manufacturer_ids), SupervisionRecord.kind == "enterprises"))} if manufacturer_ids else {}
        return [{"id": row.id, "display_no": getattr(row, "display_no", None), "name": row.name,
                 "brand": row.brand, "model": row.model, "manufacturer_enterprise_name": names.get(row.manufacturer_enterprise_id),
                 "missing_fields": missing, "reason": "名称相同，请核对是否同一产品" if normalized(row.name) == query_name else "名称接近，请核对是否同一产品"}
                for _, row, missing in matches]

    async def delete_foundation(self, kind, entity_id, product_id=None):
        """Delete unused master data only; never cascade into business evidence or tasks."""
        self.require_role({"admin"})
        models = {"enterprise": SupervisionRecord, "category": ProductCategory,
                  "product": QualityProduct, "batch": QualityProductionBatch}
        model = models[kind]
        stmt = select(model).where(model.id == entity_id, model.org_id == self.org_id)
        if kind == "enterprise":
            stmt = stmt.where(SupervisionRecord.kind == "enterprises")
        else:
            stmt = stmt.where(model.deleted_at.is_(None))
        if kind == "batch":
            stmt = stmt.where(QualityProductionBatch.product_id == product_id)
        row = await self.db.scalar(stmt.with_for_update().execution_options(populate_existing=True))
        if not row:
            raise NotFoundError("记录不存在或已删除")

        from app.models.task import InspectionTask
        from app.models.product import ProductSku
        from app.models.supervision import SupervisionDependency
        quoted_id = f'"{entity_id}"'
        def mentions(column):
            return column.cast(String).contains(quoted_id, autoescape=True)

        checks = [
            ("业务资料", QualitySourceRecord, or_(mentions(QualitySourceRecord.product_ref), mentions(QualitySourceRecord.enterprise_ref))),
            ("风险研判", QualityRiskCase, mentions(QualityRiskCase.scope)),
            ("风险评估", QualityRiskAssessment, mentions(QualityRiskAssessment.scope)),
            ("风险等级配置", RiskPolicy, mentions(RiskPolicy.rules)),
            ("检测判定配置", StandardExecutionRule, or_(StandardExecutionRule.category_id == entity_id, StandardExecutionRule.product_id == entity_id, mentions(StandardExecutionRule.condition))),
            ("质监业务记录", SupervisionRecord, (SupervisionRecord.id != entity_id) & mentions(SupervisionRecord.data)),
            ("业务关联", SupervisionDependency, or_(SupervisionDependency.source_id == entity_id, SupervisionDependency.target_id == entity_id)),
            ("检测任务", InspectionTask, or_(InspectionTask.product_category_id == entity_id,
                InspectionTask.quality_product_id == entity_id, InspectionTask.product_id == entity_id,
                mentions(InspectionTask.meta_data))),
        ]
        if kind == "category":
            checks.extend([
                ("产品", QualityProduct, QualityProduct.category_id == entity_id),
                ("下级类别", ProductCategory, ProductCategory.parent_id == entity_id),
            ])
        elif kind == "product":
            checks.extend([
                ("产品批次，请先删除未使用的批次", QualityProductionBatch, QualityProductionBatch.product_id == entity_id),
                ("企业产品关系", EnterpriseProductRelation, EnterpriseProductRelation.product_id == entity_id),
                ("实物样品", PhysicalSample, PhysicalSample.product_id == entity_id),
            ])
        elif kind == "enterprise":
            checks.extend([
                ("产品", QualityProduct, QualityProduct.manufacturer_enterprise_id == entity_id),
                ("企业产品关系", EnterpriseProductRelation, EnterpriseProductRelation.enterprise_id == entity_id),
                ("历史产品档案", ProductSku, mentions(ProductSku.supervision_data)),
            ])
        elif row.original_batch_no:
            checks.extend([
                ("业务资料", QualitySourceRecord, (QualitySourceRecord.product_ref["product_id"].as_string() == product_id) &
                    (QualitySourceRecord.product_ref["production_batch_ref"].as_string() == row.original_batch_no)),
                ("实物样品", PhysicalSample, (PhysicalSample.product_id == product_id) & (PhysicalSample.production_batch_ref == row.original_batch_no)),
            ])
        for label, target, condition in checks:
            query = select(target.id).where(target.org_id == self.org_id, condition)
            if hasattr(target, "deleted_at"):
                query = query.where(target.deleted_at.is_(None))
            # A current locking read avoids a stale REPEATABLE READ snapshot after the master lock.
            if await self.db.scalar(query.limit(1).with_for_update(read=True)):
                raise ConflictError(f"无法删除：该记录已关联{label}。不会连带删除关联数据。")

        from app.services.audit_service import AuditService
        snapshot = {column.name: getattr(row, column.key) for column in row.__table__.columns}
        await AuditService(self.db).write_outbox({"org_id": self.org_id, "actor_id": self.actor,
            "actor_role": self.current.role, "resource_type": f"quality_{kind}",
            "resource_id": entity_id, "action": "delete", "snapshot": snapshot})
        if kind == "product":
            # Identifiers are owned by this unused product. Business records are never deleted.
            identifiers = list(await self.db.scalars(select(ProductIdentifier).where(
                ProductIdentifier.org_id == self.org_id, ProductIdentifier.product_id == entity_id)))
            for identifier in identifiers:
                await self.db.delete(identifier)
        await self.db.delete(row)
        await self.db.flush()
        return {"deleted": True, "id": entity_id}

    async def validate_manufacturer(self, enterprise_id):
        if not enterprise_id:
            return
        from uuid import UUID
        try:
            enterprise_id = str(UUID(enterprise_id))
        except ValueError as exc:
            raise ValidationError("生产企业引用格式不正确") from exc
        enterprise = await self.db.scalar(select(SupervisionRecord).where(
            SupervisionRecord.id == enterprise_id, SupervisionRecord.org_id == self.org_id,
            SupervisionRecord.kind == "enterprises", SupervisionRecord.status == "active").with_for_update(read=True))
        if not enterprise:
            raise ValidationError("生产企业不存在或不属于当前组织")

    async def production_batch(self, product_id, batch_id, *, lock=False):
        await self.product(product_id)
        stmt = select(QualityProductionBatch).where(
            QualityProductionBatch.id == batch_id, QualityProductionBatch.org_id == self.org_id,
            QualityProductionBatch.product_id == product_id, QualityProductionBatch.deleted_at.is_(None))
        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        else:
            stmt = stmt.with_for_update(read=True)
        row = await self.db.scalar(stmt)
        if not row:
            raise NotFoundError("批次不存在或不属于所选产品")
        await BusinessNumberService(self.db).attach([row])
        return row

    async def product_batches(self, product_id):
        await self.product(product_id)
        rows = list(await self.db.scalars(select(QualityProductionBatch).where(
            QualityProductionBatch.org_id == self.org_id, QualityProductionBatch.product_id == product_id,
            QualityProductionBatch.deleted_at.is_(None)).order_by(QualityProductionBatch.created_at.desc())))
        await BusinessNumberService(self.db).attach(rows)
        return [self.batch_response(row) for row in rows]

    async def save_production_batch(self, product_id, payload, batch_id=None):
        self.require_role({"admin"})
        # Lock the product so two registrations cannot race on its original batch number.
        from app.models.quality_risk import QualityProduct
        product = await self.db.scalar(select(QualityProduct).where(
            QualityProduct.id == product_id, QualityProduct.org_id == self.org_id,
            QualityProduct.deleted_at.is_(None)).with_for_update())
        if not product:
            raise NotFoundError("产品不存在")
        row = await self.production_batch(product_id, batch_id, lock=True) if batch_id else None
        if payload.original_batch_no:
            existing = await self.db.scalar(select(QualityProductionBatch.id).where(
                QualityProductionBatch.org_id == self.org_id, QualityProductionBatch.product_id == product_id,
                QualityProductionBatch.original_batch_no == payload.original_batch_no,
                QualityProductionBatch.deleted_at.is_(None)).with_for_update())
            if existing and existing != batch_id:
                raise ConflictError("该产品已登记此原始批次号，请使用已有批次")
        try:
            async with self.db.begin_nested():
                if row is None:
                    row = QualityProductionBatch(org_id=self.org_id, product_id=product_id, created_by=self.actor)
                    self.db.add(row)
                row.original_batch_no = payload.original_batch_no
                row.production_date = payload.production_date
                await self.flush_and_refresh(row)
        except IntegrityError as exc:
            raise ConflictError("该产品已登记此原始批次号") from exc
        return self.batch_response(row)

    @staticmethod
    def batch_response(row):
        return {"id": row.id, "product_id": row.product_id, "display_no": getattr(row, "display_no", None),
                "original_batch_no": row.original_batch_no, "production_date": row.production_date}

    async def product_links(self, product_id, batch_id=None):
        self.require_role({"admin"})
        await self.product(product_id)
        batch = await self.production_batch(product_id, batch_id) if batch_id else None
        from app.models.task import InspectionTask
        from app.models.result import InspectionResult
        record_stmt = select(QualitySourceRecord).where(
            QualitySourceRecord.org_id == self.org_id, QualitySourceRecord.deleted_at.is_(None),
            QualitySourceRecord.product_ref["product_id"].as_string() == product_id)
        task_stmt = select(InspectionTask).where(
            InspectionTask.org_id == self.org_id, InspectionTask.deleted_at.is_(None),
            InspectionTask.quality_product_id == product_id)
        if batch:
            # An unknown supplier batch number never groups unrelated material by date.
            conditions = [QualitySourceRecord.product_ref["production_batch_id"].as_string() == batch.id]
            if batch.original_batch_no:
                conditions.append(QualitySourceRecord.product_ref["production_batch_ref"].as_string() == batch.original_batch_no)
            record_stmt = record_stmt.where(or_(*conditions))
            task_stmt = task_stmt.where(InspectionTask.meta_data["quality_batch_id"].as_string() == batch.id)
        records = list(await self.db.scalars(record_stmt.order_by(QualitySourceRecord.received_at.desc()).limit(100)))
        tasks = list(await self.db.scalars(task_stmt.order_by(InspectionTask.created_at.desc()).limit(100)))
        await BusinessNumberService(self.db).attach(records)
        await BusinessNumberService(self.db).attach(tasks)
        result_tasks = set(await self.db.scalars(select(InspectionResult.task_id).where(
            InspectionResult.org_id == self.org_id, InspectionResult.task_id.in_([t.id for t in tasks]),
            InspectionResult.deleted_at.is_(None)))) if tasks else set()
        return {"records": [{"id": r.id, "display_no": getattr(r, "display_no", None),
                            "record_type": r.record_type, "origin_label": (r.provenance or {}).get("origin_label"),
                            "received_at": r.received_at} for r in records],
                "tasks": [{"id": t.id, "display_no": getattr(t, "display_no", None), "status": t.status,
                           "has_result": t.id in result_tasks, "created_at": t.created_at} for t in tasks]}
