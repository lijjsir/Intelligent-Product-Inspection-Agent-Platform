"""Optional local demo validation; link existing tasks/reports, never execute tasks."""
import copy
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.permissions import require_role
from app.models.quality_risk import QualityRiskAssessment, QualitySourceRecord
from app.models.supervision import SupervisionRecord
from app.models.task import InspectionTask
from app.services.demo_risk_workflow_service import DemoRiskWorkflowService, is_manual_demo
from app.services.risk_workflow_context_service import RiskWorkflowContextService
from app.services.quality_risk_service import stable_hash

KIND = "risk-lab-verifications"
BOUNDARY = "演示验证分支；可跳过，仅关联既有任务和模拟检测资料，不启动设备、模型或检测执行，不代替正式检测报告。"


class RiskLabService:
    def __init__(self, db, current):
        self.db, self.current = db, current
        self.demo = RiskWorkflowContextService(db, current)
        self.org_id, self.actor = self.demo.org_id, self.demo.actor
        self.boundary = BOUNDARY if self.demo.is_demo else '验证分支仅关联已有任务或检测资料，不自动执行检测；结果仅覆盖原任务确认的样品和项目。'

    async def guard(self, write=False):
        actor = await self.demo.guard(write=write)
        if str(self.current.role) != "expert":
            raise ForbiddenError("本轮验证分支由专家工作区访问")
        return actor

    async def task(self, task_id, case):
        require_role("task", self.current.role)
        row = await self.db.scalar(self.demo.read(select(InspectionTask).where(InspectionTask.id == task_id,
            InspectionTask.org_id == self.org_id, InspectionTask.deleted_at.is_(None))))
        if not row:
            raise NotFoundError("检测任务不存在或不在当前组织")
        if self.demo.is_demo and (row.meta_data or {}).get("execution_mode") != "demo":
            raise ValidationError("演示分支只能关联明确标记的演示任务")
        if not self.demo.is_demo and (row.meta_data or {}).get('execution_mode') == 'demo':
            raise ValidationError('正式验证不能关联演示任务')
        if not (case.scope or {}).get("product_id") or row.quality_product_id != case.scope["product_id"]:
            raise ValidationError("检测任务必须明确关联本事项同一产品")
        return row

    def matches(self, case, record):
        product = (case.scope or {}).get("product_id")
        enterprise = (case.scope or {}).get("enterprise_id")
        if product:
            return (record.product_ref or {}).get("product_id") == product
        if enterprise:
            return (record.enterprise_ref or {}).get("enterprise_id", (record.enterprise_ref or {}).get("id")) == enterprise
        return False

    async def options(self, case_id):
        await self.guard()
        case = await self.demo.risk.risk_case(case_id)
        product_id = (case.scope or {}).get('product_id')
        tasks = list(await self.db.scalars(select(InspectionTask).where(InspectionTask.org_id == self.org_id,
            InspectionTask.deleted_at.is_(None), InspectionTask.quality_product_id == product_id))) if product_id else []
        records = list(await self.db.scalars((await self.demo.risk.scoped_records()).where(
            QualitySourceRecord.record_type == "inspection_report", QualitySourceRecord.data_nature == ('synthetic' if self.demo.is_demo else 'observed'))
            .order_by(QualitySourceRecord.created_at.desc())))
        return {"tasks": [{"id": t.id, "label": f"{'演示' if self.demo.is_demo else '检测'}任务 {t.id}", "status": t.status} for t in tasks
                if (case.scope or {}).get("product_id") and ((t.meta_data or {}).get("execution_mode") == "demo") == self.demo.is_demo],
            "records": [{"id": r.id, "label": str((r.content or {}).get("title") or (r.content or {}).get("text") or "检测资料")[:160],
                "already_linked": r.id in (case.source_record_ids or [])} for r in records if self.matches(case, r)], "boundary": self.boundary}

    async def row(self, link_id):
        row = await self.db.scalar(self.demo.read(select(SupervisionRecord).where(SupervisionRecord.id == link_id,
            SupervisionRecord.org_id == self.org_id, SupervisionRecord.kind == KIND)))
        if not row:
            raise NotFoundError("验证关联不存在")
        if row.data.get('execution_mode','demo') != self.demo.mode:
            raise ForbiddenError('验证关联不属于当前业务环境')
        await self.demo.risk.risk_case(row.data["case_id"], lock=self.demo.locked)
        return row

    async def serialize(self, row):
        case = await self.demo.risk.risk_case(row.data["case_id"])
        assessment = await self.db.scalar(self.demo.read(select(QualityRiskAssessment).where(
            QualityRiskAssessment.id == row.data["assessment_id"], QualityRiskAssessment.org_id == self.org_id,
            QualityRiskAssessment.deleted_at.is_(None))))
        if not assessment:
            raise NotFoundError("原研判版本已不可访问")
        latest = await self.demo.latest(case)
        issues = []
        try:
            if row.data.get("task_id"):
                await self.task(row.data["task_id"], case)
        except (NotFoundError, ValidationError, ForbiddenError) as error:
            issues.append(error.message)
        if row.data.get("returned_basis_hash"):
            basis, blockers = await self.demo.capture(case)
            issues.extend(b["message"] for b in blockers)
            if stable_hash(basis) != row.data["returned_basis_hash"]:
                issues.append("回流后事项资料或对象已变化，请在新版研判中重新核对")
        return {"id": row.id, "status": row.status, "revision": row.version, "created_by": row.created_by,
            "is_latest_assessment": bool(latest and latest.id == assessment.id), "issues": list(dict.fromkeys(issues)),
            "boundary": self.boundary, **copy.deepcopy(row.data)}

    async def list(self, case_id):
        await self.guard()
        await self.demo.risk.risk_case(case_id)
        rows = list(await self.db.scalars(self.demo.read(select(SupervisionRecord).where(SupervisionRecord.org_id == self.org_id,
            SupervisionRecord.kind == KIND).order_by(SupervisionRecord.created_at.desc()))))
        return [await self.serialize(r) for r in rows if r.data["case_id"] == case_id and r.data.get('execution_mode','demo') == self.demo.mode]

    async def decide(self, case_id, payload):
        actor = await self.guard(write=True)
        case, assessment = await self.demo.target(case_id, str(payload.assessment_id))
        if self.demo.is_demo and (not is_manual_demo(assessment) or assessment.status != "demo_reviewed"):
            raise ConflictError("请先完成本版独立演示复核")
        await self.demo.ensure_current(case, assessment)
        if (await self.demo.validation(case, assessment))['basis_hash'] != payload.expected_basis_hash:
            raise ConflictError("事项依据已变化，请刷新后选择验证分支")
        if payload.mode == "skip" and payload.task_id:
            raise ValidationError("跳过验证时无需关联检测任务")
        if payload.task_id:
            await self.task(str(payload.task_id), case)
        row = await self.db.scalar(self.demo.read(select(SupervisionRecord).where(SupervisionRecord.org_id == self.org_id,
            SupervisionRecord.kind == KIND, SupervisionRecord.code == assessment.id)))
        values = {"mode": payload.mode, "purpose": payload.purpose, "task_id": str(payload.task_id) if payload.task_id else None}
        if row:
            if all(row.data[k] == v for k, v in values.items()):
                return {**await self.serialize(row), "reused": True}
            if row.created_by != self.actor:
                raise ForbiddenError("只有原编写人可以调整验证选择")
            if row.version != payload.expected_revision or row.data.get("record_ids"):
                raise ConflictError("验证选择已更新或已有资料回流，请保留原记录并在新版研判中处理")
            row.version += 1
            row.data = {**row.data, **values, "events": [*row.data["events"], self.demo.event(actor, "decision_changed", **values)]}
        else:
            if payload.expected_revision is not None:
                raise ConflictError("验证记录不存在，请刷新后重新选择")
            row = SupervisionRecord(id=str(uuid5(NAMESPACE_URL, f"risk-lab:{self.org_id}:{assessment.id}")),
                org_id=self.org_id, kind=KIND, code=assessment.id, name=f"【{'演示' if self.demo.is_demo else '实验室'}验证】{case.code} · 第{assessment.version}版",
                version=1, created_by=self.actor, data={**values, "case_id": case.id, "case_code": case.code,
                    "assessment_id": assessment.id, "assessment_version": assessment.version, "basis_hash": payload.expected_basis_hash,
                    "execution_mode": self.demo.mode, "record_ids": [], "returned_basis_hash": None,
                    "events": [self.demo.event(actor, "decision_created", **values)]})
            self.db.add(row)
        row.status = ('demo_' if self.demo.is_demo else '') + ('skipped' if payload.mode == 'skip' else 'requested')
        await self.db.flush()
        return {**await self.serialize(row), "reused": False}

    async def return_records(self, link_id, payload):
        actor = await self.guard(write=True)
        row = await self.row(link_id)
        ids = sorted({str(rid) for rid in payload.record_ids})
        if row.data.get("record_ids"):
            if sorted(row.data["record_ids"]) == ids and row.data.get("return_note") == payload.note:
                return {**await self.serialize(row), "reused": True}
            raise ConflictError("本次验证资料已固定，新的补证请从原事项继续接入")
        if row.version != payload.expected_revision or row.data["mode"] != "verify":
            raise ConflictError("验证选择已变化或已跳过，请刷新后处理")
        case = await self.demo.risk.risk_case(row.data["case_id"], lock=True)
        if row.data.get("task_id"):
            await self.task(row.data["task_id"], case)
        for rid in ids:
            record = await self.demo.risk.record(rid)
            if record.record_type != "inspection_report" or record.data_nature != ('synthetic' if self.demo.is_demo else 'observed') or not self.matches(case, record):
                raise ValidationError("只能回流当前环境中明确关联同一对象的检测资料，未知或不匹配对象请先整理")
        before, _ = await self.demo.capture(case)
        await self.demo.risk.append_risk_sources(case.id, ids)
        basis, blockers = await self.demo.capture(case)
        if blockers:
            raise ValidationError("回流资料当前不可用，请核对原件和授权", detail={"blockers": blockers})
        row.version += 1
        row.status = "demo_returned" if self.demo.is_demo else 'returned'
        row.data = {**row.data, "record_ids": ids, "return_note": payload.note,
            "added_new_evidence": stable_hash(before) != stable_hash(basis), "returned_basis_hash": stable_hash(basis),
            "events": [*row.data["events"], self.demo.event(actor, "evidence_returned", record_ids=ids, note=payload.note)]}
        await self.db.flush()
        return {**await self.serialize(row), "reused": False}
