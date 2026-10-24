"""Current, independently reviewed risk versions for monitoring and sampling consumers."""
from sqlalchemy import select

from app.core.exceptions import NotFoundError, ValidationError
from app.models.quality_risk import (
    ProductCategory,
    QualityProduct,
    QualityRiskAssessment,
    QualityRiskCase,
    QualitySourceRecord,
)
from app.services.knowledge_source_service import fingerprint
from app.services.risk_evidence_validation_service import validate_risk


class RiskDecisionContextService:
    def __init__(self, session, current, storage=None):
        self.session, self.current, self.storage = session, current, storage

    async def accepted(self, case_id, *, expected=None, allow_historical=False):
        case = await self.session.scalar(select(QualityRiskCase).where(
            QualityRiskCase.id == case_id, QualityRiskCase.org_id == self.current.org_id,
            QualityRiskCase.deleted_at.is_(None)).execution_options(populate_existing=True))
        if not case:
            raise NotFoundError("风险案件不存在或不在授权组织范围")
        from app.services.risk_purpose_policy import HISTORICAL, purpose, require_current_purpose
        if not allow_historical:
            require_current_purpose(case)
        assessment = await self.session.scalar(select(QualityRiskAssessment).where(
            QualityRiskAssessment.org_id == self.current.org_id,
            QualityRiskAssessment.risk_case_id == case.id, QualityRiskAssessment.deleted_at.is_(None))
            .order_by(QualityRiskAssessment.version.desc()).limit(1).execution_options(populate_existing=True))
        if not assessment or case.status != "risk_assessed" or assessment.status != "accepted":
            if allow_historical and purpose(case.scope) == HISTORICAL:
                raise ValidationError("历史复盘须由另一位专家复核本版后，才能生成复盘报告")
            raise ValidationError("候选必须来自当前已独立复核的风险研判")
        review = (assessment.model_versions or {}).get("review_verification") or {}
        if purpose(case.scope) == HISTORICAL and (not review.get("historical_scope_confirmed") or
                (assessment.conflicts and not (review.get("conflict_resolution") or "").strip())):
            raise ValidationError("历史复盘缺少原件范围确认或冲突核对意见")
        if (assessment.trust_status != "verified" or not assessment.reviewed_by
                or assessment.reviewed_by == assessment.submitted_by or not assessment.reviewed_at
                or review.get("actor_id") != assessment.reviewed_by or review.get("decision") != "accept"
                or assessment.risk_level not in {"low", "medium", "high", "critical"}):
            raise ValidationError("风险研判缺少有效的独立复核凭据，请重新生成并复核")
        validation = await validate_risk(self.session, self.current, case, assessment, self.storage)
        if validation["blockers"]:
            raise ValidationError("风险来源已失效或需要重新核验，不能继续使用本版结论",
                detail={"case_id": case.id, "blockers": validation["blockers"]})
        fields = ["id", "version", "scope", "risk_type", "risk_level", "probability", "evidence_ids",
            "standard_matches", "conflicts", "missing_inputs", "possible_causes", "recommendations",
            "model_versions", "policy_version", "knowledge_snapshot_id", "submitted_by", "reviewed_by",
            "reviewed_at", "review_comment", "status", "trust_status"]
        ref = {"kind": "quality_risk_case", "case_id": case.id, "assessment_id": assessment.id,
            "version": assessment.version, "source_hash": fingerprint({
                "scope": case.scope, "source_record_ids": case.source_record_ids,
                "created_by": case.created_by, "assigned_to": case.assigned_to,
                "assessment": {key: getattr(assessment, key) for key in fields}})}
        source_ids = {s["source_record_id"] for s in validation["sources"] if s.get("source_record_id")}
        records = list(await self.session.scalars(select(QualitySourceRecord).where(
            QualitySourceRecord.org_id == self.current.org_id, QualitySourceRecord.id.in_(source_ids),
            QualitySourceRecord.deleted_at.is_(None)).order_by(QualitySourceRecord.occurred_at.desc(), QualitySourceRecord.received_at.desc(), QualitySourceRecord.id.desc())))
        source = next((r for r in records if r.occurred_at), records[0] if records else None)
        category = case.scope.get("product_category") or case.scope.get("category_name")
        if not category and case.scope_type == "category":
            category = case.scope.get("name")
        category_id = case.scope.get("category_id")
        if not category_id and case.scope.get("product_id"):
            product = await self.session.scalar(select(QualityProduct).where(
                QualityProduct.id == case.scope["product_id"], QualityProduct.org_id == self.current.org_id,
                QualityProduct.deleted_at.is_(None)))
            category_id = product.category_id if product else None
        if not category and category_id:
            row = await self.session.scalar(select(ProductCategory).where(ProductCategory.id == category_id,
                ProductCategory.org_id == self.current.org_id, ProductCategory.deleted_at.is_(None)))
            category = row.name if row else None
        ref["source_hash"] = fingerprint({"risk_definition": ref["source_hash"], "product_category": category})
        if expected is not None and ref != expected:
            raise ValidationError("风险研判版本或对象已变化，请更新候选并重新分析抽查方案")
        return {"id": case.id, "kind": "quality_risk_case", "version": assessment.version,
            "code": case.code, "name": case.title, "status": "risk_assessed",
            "created_by": case.created_by, "assigned_to": case.assigned_to, "scope": case.scope,
            "source_ref": ref, "uncertainties": validation["uncertainties"],
            "data": {**case.scope, "product_category": category,
                "occurred_at": source.occurred_at.isoformat() if source and source.occurred_at else None,
                "complaint_region_id": (source.location or {}).get("district_code") if source else None,
                "sampling_region_id": None,
                "enterprise_id": ((source.enterprise_ref or {}).get("enterprise_id")
                    or (source.enterprise_ref or {}).get("name")) if source else None,
                "evidence": [{"source_type": r.record_type, "nature": r.data_nature} for r in records],
                "analysis": {"risk_level": assessment.risk_level, "probability": assessment.probability}}}

    async def eligible(self):
        ids = list(await self.session.scalars(select(QualityRiskCase.id).where(
            QualityRiskCase.org_id == self.current.org_id, QualityRiskCase.status == "risk_assessed",
            QualityRiskCase.deleted_at.is_(None)).order_by(QualityRiskCase.id)))
        contexts, excluded = [], []
        for case_id in ids:
            try:
                contexts.append(await self.accepted(case_id))
            except (NotFoundError, ValidationError) as exc:
                excluded.append({"case_id": case_id, "reason": exc.message})
        return contexts, excluded

    async def verify_refs(self, refs):
        contexts = []
        seen = set()
        for ref in refs:
            if (not isinstance(ref, dict) or ref.get("kind") != "quality_risk_case"
                    or not ref.get("case_id") or ref["case_id"] in seen):
                raise ValidationError("抽查风险来源引用缺失或重复，请重新分析")
            seen.add(ref["case_id"])
            contexts.append(await self.accepted(ref["case_id"], expected=ref))
        return contexts
