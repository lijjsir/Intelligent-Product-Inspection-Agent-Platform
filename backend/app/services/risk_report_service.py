"""Task-independent, immutable demo assessment reports with live access checks."""
import copy
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select, or_

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.permissions import require_role
from app.models.quality_risk import QualityRiskAssessment, QualityEvidenceItem, QualityProduct
from app.models.supervision import SupervisionRecord
from app.services.demo_risk_workflow_service import DemoRiskWorkflowService, is_manual_demo, now
from app.services.risk_workflow_context_service import RiskWorkflowContextService
from app.services.demo_sampling_service import DemoSamplingService
from app.services.quality_risk_service import stable_hash
from app.services.risk_lab_service import RiskLabService

KIND = "risk-assessment-reports"
BOUNDARY = "演示研判报告：全部为模拟资料与人工研判，未调用真实模型；不构成正式风险结论、检测报告或执行指令。报告固定生成时版本，后续变化请在平台核对。"


class RiskReportService:
    def __init__(self, db, current):
        self.db, self.current = db, current
        self.demo = RiskWorkflowContextService(db, current)
        self.org_id, self.actor = self.demo.org_id, self.demo.actor

    async def guard(self, write=False):
        actor = await self.demo.guard(write=write)
        if str(self.current.role) != "expert":
            raise ForbiddenError("本轮独立研判报告向专家开放")
        require_role("report_generate" if write else "report_read", self.current.role)
        return actor

    @staticmethod
    def assessment_hash(row):
        if not is_manual_demo(row):
            return stable_hash({key:getattr(row,key) for key in ('id','version','scope','status','trust_status','risk_type','risk_level','probability','evidence_ids','standard_matches','conflicts','missing_inputs','possible_causes','recommendations','model_versions','submitted_by','reviewed_by','reviewed_at','review_comment')})
        return stable_hash({"id": row.id, "version": row.version, "scope": row.scope, "status": row.status,
            "submitted_by": row.submitted_by, "reviewed_by": row.reviewed_by, "reviewed_at": row.reviewed_at,
            "review_comment": row.review_comment, "workflow": (row.model_versions or {}).get("demo_workflow")})

    @staticmethod
    def record_hash(row):
        return stable_hash({"data": row.data, "status": row.status, "version": row.version})

    async def create(self, case_id, payload):
        await self.guard(write=True)
        case, assessment = await self.demo.target(case_id, str(payload.assessment_id))
        if self.demo.is_demo and (not is_manual_demo(assessment) or assessment.status != "demo_reviewed" or assessment.trust_status != "demo_reviewed" or not assessment.reviewed_by or assessment.reviewed_by == assessment.submitted_by):
            raise ConflictError("仅能为当前独立演示复核通过的版本生成报告")
        if self.actor not in {assessment.submitted_by, assessment.reviewed_by}:
            raise ForbiddenError("请由本版编写人或独立复核人生成报告")
        await self.demo.ensure_current(case, assessment)
        validation = await self.demo.validation(case, assessment)
        content = self.demo.content(assessment, case)
        if payload.expected_basis_hash != validation['basis_hash']:
            raise ConflictError("资料版本已变化，请刷新核对后生成")
        records, attachments = [], []
        for rid in sorted(case.source_record_ids or []):
            r = await self.demo.risk.record(rid)
            records.append({"id": r.id, "type": r.record_type, "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
                "content": copy.deepcopy(r.content), "content_hash": r.content_hash, "data_nature": r.data_nature,
                "attachment_ids": r.attachment_ids, "origin": (r.provenance or {}).get("origin_label") or "出处未明确"})
            for aid in r.attachment_ids or []:
                a = await self.demo.risk.accessible_attachment(aid)
                attachments.append({"id": a.id, "name": a.file_name, "sha256": a.sha256 if hasattr(a, "sha256") else a.checksum})
        evidence = list(await self.db.scalars(self.demo.read(select(QualityEvidenceItem).where(
            QualityEvidenceItem.org_id == self.org_id, QualityEvidenceItem.id.in_(case.evidence_ids or []),
            QualityEvidenceItem.deleted_at.is_(None)).order_by(QualityEvidenceItem.id))))
        lab_service = RiskLabService(self.db, self.current)
        lab_service.demo = self.demo
        sampling_service = DemoSamplingService(self.db, self.current)
        sampling_service.demo = sampling_service.collab.demo = self.demo
        labs = await lab_service.list(case.id)
        suggestions = await sampling_service.list(case.id)
        refs = []
        for item in [*labs, *suggestions]:
            row = await self.db.scalar(self.demo.read(select(SupervisionRecord).where(
                SupervisionRecord.id == item["id"], SupervisionRecord.org_id == self.org_id)))
            refs.append({"id": row.id, "kind": row.kind, "hash": self.record_hash(row)})
        for item in suggestions:
            if item["snapshot"]["assessment_id"] == assessment.id:
                _, token = await sampling_service.context(case.id, item["snapshot"]["collaboration_id"])
                refs.append({"id": item["snapshot"]["collaboration_id"], "kind": "collab-context", "hash": token})
        product_id = (case.scope or {}).get("product_id")
        product = await self.db.scalar(select(QualityProduct).where(QualityProduct.id == product_id,
            QualityProduct.org_id == self.org_id)) if product_id else None
        mode = self.demo.mode
        if not self.demo.is_demo:
            content = {**content, 'probability': assessment.probability}
        boundary = BOUNDARY if self.demo.is_demo else '风险研判报告固定已独立复核的事项、证据和建议；不替代检测报告或抽查执行指令。后续来源变化请在平台核对当前有效性。'
        from app.models.user import User
        author = await self.db.get(User, assessment.submitted_by)
        snapshot = {"schema": "demo-risk-report-v1" if self.demo.is_demo else 'risk-report-v1', "execution_mode": mode,
            "llm_called": False if self.demo.is_demo else bool((assessment.model_versions or {}).get('llm_called')),
            "case_id": case.id, "case_code": case.code, "case_title": case.title, "scope": copy.deepcopy(case.scope),
            "object_name": product.name if product else ((case.scope or {}).get('name') or (case.scope or {}).get('product_category') or '对象名称未知') if not self.demo.is_demo else '对象名称未知', "assessment_id": assessment.id,
            "assessment_version": assessment.version, "basis_hash": validation['basis_hash'],
            "assessment_hash": self.assessment_hash(assessment), "conclusion": copy.deepcopy(content),
            "review": {"author_id": assessment.submitted_by, "author_name": (assessment.model_versions.get('demo_workflow') or {}).get('author_name', author.username if author else '专家'),
                "reviewer_id": assessment.reviewed_by, "at": assessment.reviewed_at.isoformat() if assessment.reviewed_at else None,
                "comment": assessment.review_comment, "status": assessment.status},
            "records": records, "attachments": list({a["id"]: a for a in attachments}.values()),
            "evidence": [{"id": e.id, "source_record_id": e.source_record_id, "text": e.text,
                "structured_data": e.structured_data, "nature": e.nature} for e in evidence],
            "laboratory": labs, "sampling": [{k: s[k] for k in ("id", "title", "status", "effective_status", "revision", "content", "snapshot")} for s in suggestions],
            "source_refs": refs, "boundary": boundary}
        if not self.demo.is_demo:
            snapshot['model_call'] = {key:(assessment.model_versions or {}).get(key) for key in (
                'llm_called', 'model_success', 'attempted_calls', 'successful_calls', 'inference_status')}
            from app.services.risk_execution_evidence_service import execution_returns
            entries = await execution_returns(self.db, self.org_id, case.id)
            if entries:
                snapshot['execution_results'] = entries
        token = stable_hash(snapshot)
        existing = await self.db.scalar(self.demo.read(select(SupervisionRecord).where(SupervisionRecord.org_id == self.org_id,
            SupervisionRecord.kind == KIND, SupervisionRecord.code == token)))
        if existing:
            return {**await self.get(existing.id), "reused": True}
        row = SupervisionRecord(id=str(uuid5(NAMESPACE_URL, f"risk-report:{self.org_id}:{token}")), org_id=self.org_id,
            kind=KIND, code=token, name=f"【{'演示' if self.demo.is_demo else ''}研判报告】{case.code} · 第{assessment.version}版", status="demo_frozen" if self.demo.is_demo else 'frozen', version=1,
            created_by=self.actor, data={"snapshot": snapshot, "snapshot_hash": token, "frozen_at": now(),
                "reader_ids": sorted({self.actor, assessment.submitted_by, assessment.reviewed_by})})
        self.db.add(row)
        await self.db.flush()
        return {**await self.get(row.id), "reused": False}

    async def get(self, report_id):
        await self.guard()
        row = await self.db.scalar(self.demo.read(select(SupervisionRecord).where(SupervisionRecord.id == report_id,
            SupervisionRecord.org_id == self.org_id, SupervisionRecord.kind == KIND)))
        if not row:
            raise NotFoundError("研判报告不存在")
        if self.actor not in row.data["reader_ids"]:
            raise ForbiddenError("不在本报告的编写与独立复核范围")
        snapshot = row.data["snapshot"]
        if snapshot.get('execution_mode') != self.demo.mode:
            raise ForbiddenError('报告不属于当前业务环境')
        if stable_hash(snapshot) != row.data["snapshot_hash"]:
            raise ConflictError("报告快照完整性校验失败")
        case = await self.demo.risk.risk_case(snapshot["case_id"])
        # Withdrawal of access must not turn the immutable report into a data leak.
        from app.services.execution_evidence_service import ExecutionEvidenceService
        authorization = ExecutionEvidenceService(self.db, self.current, self.demo.risk.storage)
        for record in snapshot["records"]:
            raw = await self.demo.risk.record(record["id"])
            if not authorization.record_authorized(raw):
                raise ForbiddenError('报告引用资料已不在当前授权范围，不能继续读取原文快照')
        for attachment in snapshot["attachments"]:
            await authorization.attachment(attachment["id"])
        from app.services.risk_execution_evidence_service import RiskExecutionEvidenceService
        execution_access = RiskExecutionEvidenceService(self.db, self.current, self.demo.risk.storage)
        for entry in snapshot.get('execution_results', []):
            await execution_access.authorize(entry['ref'])
        for item in snapshot["sampling"]:
            await DemoSamplingService(self.db, self.current).row(item["id"])
        issues = []
        latest = await self.demo.latest(case)
        assessment = await self.db.scalar(self.demo.read(select(QualityRiskAssessment).where(
            QualityRiskAssessment.id == snapshot["assessment_id"], QualityRiskAssessment.org_id == self.org_id,
            QualityRiskAssessment.deleted_at.is_(None))))
        if not assessment:
            raise NotFoundError("原研判版本已撤回")
        basis, blockers = await self.demo.capture(case)
        issues.extend(b["message"] for b in blockers)
        if stable_hash(basis) != snapshot["basis_hash"] or self.assessment_hash(assessment) != snapshot["assessment_hash"] or not latest or latest.id != assessment.id:
            issues.append("事项依据、复核或研判版本已变化；本报告为生成时历史快照")
        for ref in snapshot["source_refs"]:
            if ref["kind"] == "collab-context":
                try:
                    _, token = await DemoSamplingService(self.db, self.current).context(case.id, ref["id"])
                    if token != ref["hash"]:
                        issues.append("公开协同意见已变化；报告保留生成时意见")
                except (ConflictError, ValidationError):
                    issues.append("原协同对应的研判已更新；报告保留历史意见")
                continue
            original = await self.db.scalar(self.demo.read(select(SupervisionRecord).where(
                SupervisionRecord.id == ref["id"], SupervisionRecord.org_id == self.org_id, SupervisionRecord.kind == ref["kind"])))
            if not original or self.record_hash(original) != ref["hash"]:
                issues.append("验证选择或抽查建议已变化；请重新核对当前版本")
        related = list(await self.db.scalars(self.demo.read(select(SupervisionRecord).where(
            SupervisionRecord.org_id == self.org_id, SupervisionRecord.kind.in_(["risk-lab-verifications", "demo-sampling-suggestions" if self.demo.is_demo else 'risk-sampling-suggestions']),
            or_(SupervisionRecord.data["case_id"].as_string() == case.id,
                SupervisionRecord.data["snapshot"]["case_id"].as_string() == case.id)))))
        expected_ids = {ref["id"] for ref in snapshot["source_refs"] if ref["kind"] != "collab-context"}
        if {r.id for r in related} != expected_ids:
            issues.append("本事项新增了验证选择或抽查建议；报告仍保留原快照")
        result = {"id": row.id, "title": row.name, "status": row.status, "snapshot_hash": row.data["snapshot_hash"],
            "frozen_at": row.data["frozen_at"], "snapshot": copy.deepcopy(snapshot), "source_issues": list(dict.fromkeys(issues)),
            "effective_status": "historical_snapshot" if issues else row.status}
        from app.services.report_renderers.risk_report_content import risk_report_sections
        result["sections"] = risk_report_sections(result)
        return result

    async def list(self, case_id=None):
        await self.guard()
        rows = list(await self.db.scalars(select(SupervisionRecord).where(SupervisionRecord.org_id == self.org_id,
            SupervisionRecord.kind == KIND).order_by(SupervisionRecord.created_at.desc())))
        items = []
        for row in rows:
            if self.actor not in row.data["reader_ids"] or (case_id and row.data["snapshot"]["case_id"] != case_id):
                continue
            try:
                report = await self.get(row.id)
            except (ForbiddenError, NotFoundError):
                continue
            items.append({k: report[k] for k in ("id", "title", "status", "frozen_at", "effective_status", "source_issues")})
        return items
