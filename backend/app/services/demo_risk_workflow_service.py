"""Manual drafts and independent version review within the guarded demo only.

Assessment versions freeze the intake set; draft edits use a separate revision
counter. Once submitted, content is immutable. All decisions are demo-specific.
"""
import copy
from datetime import datetime

from sqlalchemy import select

from app.core.config import settings
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.permissions import require_role
from app.core.quality_demo import DEMO_ORG_SLUG
from app.models.organization import Organization
from app.models.quality_risk import (QualityDataSource, QualityEvidenceItem, QualityProduct,
    ProductCategory, QualityRiskAssessment, QualitySourceRecord)
from app.models.supervision import SupervisionRecord
from app.models.user import User
from app.schemas.demo_risk_workflow import DemoDraftContent
from app.services.execution_evidence_service import ExecutionEvidenceService
from app.services.quality_risk_service import QualityRiskService, stable_hash
from app.services.risk_evidence_validation_service import record_definition, evidence_definition
from app.services.supervision_service import SupervisionService

BOUNDARY = "演示人工研判与复核，仅用于流程验收；全部模拟资料，不构成正式风险结论，发生概率保持未知。"
MARKER = "manual-demo-v1"


def is_manual_demo(row):
    return (row.model_versions or {}).get("demo_workflow", {}).get("schema") == MARKER


def now():
    return datetime.utcnow().isoformat() + "Z"


class DemoRiskWorkflowService:
    allowed_natures = {"synthetic"}
    nature_description = "演示研判只能引用明确标为模拟的资料和证据"
    def __init__(self, db, current, storage=None):
        self.db, self.current = db, current
        self.risk = QualityRiskService(db, current)
        if storage is not None:
            self.risk.storage = storage
        self.org_id, self.actor = str(current.org_id), str(current.user_id)
        self.locked = False

    async def guard(self, write=False):
        if not settings.quality_demo_enabled:
            raise ForbiddenError("演示研判仅在服务端启用的本地隔离演示环境开放")
        svc = SupervisionService(self.db, self.current)
        await svc.permissions()
        svc.require_role({"expert"} if write else {"expert", "admin"})
        require_role("quality", self.current.role)
        require_role("quality_material_read_business", self.current.role)
        await svc.require_enabled()
        stmt = select(Organization).where(Organization.id == self.org_id).execution_options(populate_existing=True)
        org = await self.db.scalar(stmt.with_for_update() if write else stmt)
        if not org or org.slug != DEMO_ORG_SLUG or (org.settings or {}).get("execution_mode") != "demo":
            raise ForbiddenError("当前组织不是指定的隔离演示组织")
        self.locked = self.locked or write
        return await self.db.get(User, self.actor)

    def read(self, stmt):
        stmt = stmt.execution_options(populate_existing=True)
        return stmt.with_for_update() if self.locked else stmt

    async def latest(self, case):
        return await self.db.scalar(self.read(select(QualityRiskAssessment).where(
            QualityRiskAssessment.org_id == self.org_id, QualityRiskAssessment.risk_case_id == case.id,
            QualityRiskAssessment.deleted_at.is_(None)).order_by(QualityRiskAssessment.version.desc()).limit(1)))

    async def capture(self, case):
        """Current authorized synthetic records, fragments, objects and file bytes."""
        issues = []
        def issue(code, message):
            issues.append({"code": code, "message": message})
        records = list(await self.db.scalars(self.read(select(QualitySourceRecord).where(
            QualitySourceRecord.org_id == self.org_id, QualitySourceRecord.id.in_(case.source_record_ids or []),
            QualitySourceRecord.deleted_at.is_(None)).order_by(QualitySourceRecord.id))))
        if not records or set(case.source_record_ids or []) != {r.id for r in records}:
            issue("demo_source_missing", "事项含已撤回、丢失或跨组织的资料，请先核对来源")
        sources = list(await self.db.scalars(self.read(select(QualityDataSource).where(
            QualityDataSource.org_id == self.org_id, QualityDataSource.id.in_({r.source_id for r in records})))))
        source_map = {s.id: s for s in sources}
        authorization = ExecutionEvidenceService(self.db, self.current, self.risk.storage)
        for r in records:
            if r.data_nature not in self.allowed_natures:
                issue("invalid_source_nature", self.nature_description)
            if not authorization.record_authorized(r):
                issue("demo_source_authorization", "来源未授权给当前研判范围")
            s = source_map.get(r.source_id)
            if not s or s.deleted_at is not None or s.status != "active":
                issue("demo_source_inactive", "资料来源已撤回或停用")
        evidence = list(await self.db.scalars(self.read(select(QualityEvidenceItem).where(
            QualityEvidenceItem.org_id == self.org_id, QualityEvidenceItem.source_record_id.in_({r.id for r in records}),
            QualityEvidenceItem.deleted_at.is_(None)).order_by(QualityEvidenceItem.id))))
        if set(case.evidence_ids or []) - {e.id for e in evidence}:
            issue("demo_evidence_missing", "关联证据已撤回或不属于当前来源集合")
        if any(e.nature not in self.allowed_natures for e in evidence):
            issue("invalid_evidence_nature", self.nature_description)
        attachments = {}
        for aid in sorted({a for r in records for a in (r.attachment_ids or [])}):
            try:
                row, _, context = await authorization.file(aid)
                attachments[aid] = {"sha256": context["sha256"], "size_bytes": row.size_bytes, "bucket": row.bucket, "object_key": row.object_key}
            except (NotFoundError, ValidationError, ForbiddenError):
                attachments[aid] = {"unavailable": True}
                issue("demo_attachment_unavailable", "关联附件无法读取或原件校验不一致")
        objects = {}
        for kind in ("product", "enterprise", "category"):
            oid = (case.scope or {}).get(f"{kind}_id")
            if not oid:
                continue
            model = {"product": QualityProduct, "enterprise": SupervisionRecord, "category": ProductCategory}[kind]
            conditions = [model.id == oid, model.org_id == self.org_id]
            if kind == "enterprise":
                conditions += [model.kind == "enterprises", model.status == "active"]
            else:
                conditions += [model.deleted_at.is_(None), model.is_active.is_(True)]
            obj = await self.db.scalar(self.read(select(model).where(*conditions)))
            objects[kind] = {"id": oid, "available": obj is not None}
            if not obj:
                issue("demo_object_unavailable", "事项关联的对象档案已停用、撤回或不在组织范围")
        basis = {"scope_type": case.scope_type, "scope": case.scope,
            "case_record_ids": sorted(case.source_record_ids or []), "case_evidence_ids": sorted(case.evidence_ids or []),
            "records": {r.id: stable_hash({"definition": record_definition(r), "source_id": r.source_id,
                "authorization_scope": r.authorization_scope, "created_by": r.created_by}) for r in records},
            "sources": {s.id: {"status": s.status, "deleted": s.deleted_at is not None} for s in sources},
            "evidence": {e.id: evidence_definition(e) for e in evidence}, "attachments": attachments, "objects": objects}
        return basis, issues

    async def validation(self, case, row, captured=None):
        basis, issues = captured or await self.capture(case)
        frozen = (row.model_versions or {}).get("demo_workflow", {}).get("basis_hash")
        if not frozen or frozen != stable_hash(basis):
            issues = [*issues, {"code": "demo_basis_changed", "message": "资料、附件、对象或证据集合已变化，请创建新版草稿并重新提交复核"}]
        return {"checked_at": now(), "blockers": issues, "is_current": not issues,
                "boundary": BOUNDARY, "basis_hash": stable_hash(basis)}

    async def context(self, case):
        await self.guard()
        basis, issues = await self.capture(case)
        return {"enabled": True, "execution_mode": "demo", "basis_hash": stable_hash(basis),
                "blockers": issues, "boundary": BOUNDARY, "can_author": str(self.current.role) == "expert"}

    async def respond(self, case, row):
        data = self.risk.assessment_response(row)
        validation = await self.validation(case, row)
        wf = copy.deepcopy(row.model_versions["demo_workflow"])
        # Fingerprints remain in server storage; the UI needs only a token and
        # the authored content/history, never storage keys or connector config.
        wf.pop("basis", None)
        data["model_versions"] = {k: v for k, v in data["model_versions"].items() if k != "demo_workflow"}
        data.update(demo_workflow=wf, demo_validation=validation,
                    effective_status=row.status if validation["is_current"] else "needs_reassessment")
        return data

    def event(self, actor, action, **details):
        return {"action": action, "actor_id": self.actor, "actor_name": actor.username, "at": now(), **details}

    async def create(self, case_id, payload):
        actor = await self.guard(write=True)
        case = await self.risk.risk_case(case_id, lock=True)
        latest = await self.latest(case)
        # A retry of a previous operation must not create yet another version.
        versions = list(await self.db.scalars(self.read(select(QualityRiskAssessment).where(
            QualityRiskAssessment.org_id == self.org_id, QualityRiskAssessment.risk_case_id == case.id))))
        for row in versions:
            wf = (row.model_versions or {}).get("demo_workflow", {})
            if wf.get("request_key") == str(payload.request_key):
                if row.deleted_at is not None:
                    raise ConflictError("此请求对应的演示草稿已撤回，请刷新后创建新版本")
                if row.submitted_by != self.actor or wf.get("base_assessment_id") != (str(payload.base_assessment_id) if payload.base_assessment_id else None):
                    raise ConflictError("创建请求编号已使用，请刷新后重新操作")
                return await self.respond(case, row)
        if (latest.id if latest else None) != (str(payload.base_assessment_id) if payload.base_assessment_id else None):
            raise ConflictError("研判已有新版本，请刷新后再创建草稿")
        basis, issues = await self.capture(case)
        if payload.expected_basis_hash != stable_hash(basis):
            raise ConflictError("事项资料已变化，请刷新核对后创建草稿")
        if issues:
            raise ValidationError("当前资料不能用于演示研判", detail={"blockers": issues})
        if latest and is_manual_demo(latest) and latest.status in {"demo_draft", "demo_submitted"}:
            if latest.submitted_by != self.actor:
                raise ForbiddenError("当前版本由另一位专家编写，不能替其新建或覆盖草稿")
            if (await self.validation(case, latest, (basis, issues)))["is_current"]:
                raise ConflictError("当前草稿尚未结束，请先编辑或完成独立复核")
        content = (latest.model_versions or {}).get("demo_workflow", {}).get("content", {}) if latest else {}
        content = DemoDraftContent.model_validate(content).model_dump(mode="json")
        content["cited_record_ids"] = [rid for rid in content["cited_record_ids"] if rid in basis["records"]]
        next_version = max([r.version for r in versions], default=0) + 1
        row = QualityRiskAssessment(org_id=self.org_id, risk_case_id=case.id, version=next_version,
            scope=copy.deepcopy(case.scope), risk_type=content["risk_type"], risk_level=content["risk_level"], evidence_ids=list(basis["evidence"]),
            standard_matches=[], conflicts=[], missing_inputs=content["missing_inputs"], possible_causes=[], recommendations=content["recommendations"],
            trust_status="demo_unverified", probability=None, status="demo_draft", submitted_by=self.actor,
            model_versions={"execution_mode": "demo", "llm_called": False, "authoring_mode": "manual",
                "demo_workflow": {"schema": MARKER, "revision": 1, "request_key": str(payload.request_key),
                    "base_assessment_id": latest.id if latest else None, "basis_hash": stable_hash(basis), "basis": basis,
                    "content": content, "boundary": BOUNDARY, "author_name": actor.username,
                    "events": [self.event(actor, "created", version=next_version)]}})
        self.db.add(row)
        case.status = "demo_draft"
        await self.risk.flush_and_refresh(row)
        return await self.respond(case, row)

    async def target(self, case_id, assessment_id):
        case = await self.risk.risk_case(case_id, lock=True)
        latest = await self.latest(case)
        if not latest or latest.id != assessment_id:
            raise ConflictError("研判版本已更新，当前操作只能针对最新版本")
        if not is_manual_demo(latest):
            raise ValidationError("请先创建独立的演示人工草稿")
        return case, latest

    @staticmethod
    def revision(row, expected):
        wf = row.model_versions["demo_workflow"]
        if wf["revision"] != expected:
            raise ConflictError("草稿已被更新，请刷新核对最新内容后再操作")
        return copy.deepcopy(wf)

    async def ensure_current(self, case, row):
        validation = await self.validation(case, row)
        if not validation["is_current"]:
            raise ConflictError("依据已变化或不可用，请创建新版草稿后重新提交", detail={"blockers": validation["blockers"]})

    async def save(self, case_id, assessment_id, payload):
        actor = await self.guard(write=True)
        case, row = await self.target(case_id, assessment_id)
        if row.submitted_by != self.actor:
            raise ForbiddenError("只有本版编写人可以保存草稿")
        if row.status != "demo_draft":
            raise ConflictError("已提交或复核的内容不能修改，请创建新版")
        wf = self.revision(row, payload.expected_revision)
        await self.ensure_current(case, row)
        content = payload.content.model_dump(mode="json")
        if set(content["cited_record_ids"]) - set(case.source_record_ids or []):
            raise ValidationError("引用资料必须属于当前事项，跨组织或未关联资料不能引用")
        wf["content"] = content
        wf["revision"] += 1
        wf["events"].append(self.event(actor, "saved", revision=wf["revision"]))
        row.risk_type, row.risk_level = content["risk_type"], content["risk_level"]
        row.missing_inputs, row.recommendations = content["missing_inputs"], content["recommendations"]
        row.model_versions = {**row.model_versions, "demo_workflow": wf}
        await self.risk.flush_and_refresh(row)
        return await self.respond(case, row)

    async def submit(self, case_id, assessment_id, payload):
        actor = await self.guard(write=True)
        case, row = await self.target(case_id, assessment_id)
        if row.submitted_by != self.actor:
            raise ForbiddenError("只有本版编写人可以提交")
        if row.status != "demo_draft":
            raise ConflictError("本版本已提交或已复核，不能重复提交")
        wf = self.revision(row, payload.expected_revision)
        await self.ensure_current(case, row)
        c = wf["content"]
        if not all(c.get(key) for key in ("summary", "reasoning", "limitations", "cited_record_ids", "missing_inputs")):
            raise ValidationError("提交前请填写演示结论、判断依据、证据缺口与限制，并引用至少一条原始资料")
        wf["revision"] += 1
        wf["submitted_at"] = now()
        wf["events"].append(self.event(actor, "submitted", revision=wf["revision"], content_hash=stable_hash(c), basis_hash=wf["basis_hash"]))
        row.model_versions = {**row.model_versions, "demo_workflow": wf}
        row.status, row.trust_status, case.status = "demo_submitted", "demo_pending_review", "demo_submitted"
        await self.risk.flush_and_refresh(row)
        return await self.respond(case, row)

    async def review(self, case_id, assessment_id, payload):
        actor = await self.guard(write=True)
        case, row = await self.target(case_id, assessment_id)
        if row.submitted_by == self.actor:
            raise ForbiddenError("不能复核本人提交的演示研判，请由另一位专家操作")
        if row.status != "demo_submitted":
            raise ConflictError("只能复核已提交且尚未复核的指定版本")
        wf = self.revision(row, payload.expected_revision)
        # Stale drafts can be returned for evidence, but never approved.
        if payload.decision == "approve":
            await self.ensure_current(case, row)
        wf["revision"] += 1
        wf["events"].append(self.event(actor, "reviewed", decision=payload.decision, comment=payload.comment, revision=wf["revision"]))
        row.model_versions = {**row.model_versions, "demo_workflow": wf}
        row.reviewed_by, row.reviewed_at, row.review_comment = self.actor, datetime.utcnow(), payload.comment
        row.status = {"approve": "demo_reviewed", "revise": "demo_revise", "request_evidence": "demo_request_evidence"}[payload.decision]
        row.trust_status = "demo_reviewed" if payload.decision == "approve" else "demo_needs_revision"
        case.status = row.status if payload.decision == "approve" else "awaiting_evidence"
        await self.risk.flush_and_refresh(row)
        return await self.respond(case, row)
