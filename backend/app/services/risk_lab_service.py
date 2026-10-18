"""Optional local demo validation; link existing tasks/reports, never execute tasks."""
import copy
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select, func, or_

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.permissions import require_role
from app.models.quality_risk import QualityRiskAssessment, QualitySourceRecord
from app.models.supervision import SupervisionRecord
from app.models.task import InspectionTask
from app.services.demo_risk_workflow_service import DemoRiskWorkflowService, is_manual_demo
from app.services.risk_workflow_context_service import RiskWorkflowContextService
from app.services.quality_risk_service import stable_hash
from app.services.risk_execution_evidence_service import RiskExecutionEvidenceService, execution_returns
from app.core.ids import uuid7
from app.models.inspection_execution import InspectionExecutionRun

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
        tasks = await self.option_page(case_id, 'tasks', size=100)
        records = await self.option_page(case_id, 'records', size=100)
        return {'tasks':tasks['items'], 'records':records['items'], 'boundary':self.boundary,
            'truncated':{'tasks':tasks['total'] > 100, 'records':records['total'] > 100}}

    async def option_page(self, case_id, kind, *, page=1, size=20, keyword='', selected_ids=()):
        await self.guard()
        if kind not in {'tasks','records'} or page < 1 or not 1 <= size <= 100:
            raise ValidationError('选择列表分页参数无效')
        try:
            selected_ids = list(dict.fromkeys(str(UUID(str(value))) for value in selected_ids))
        except (ValueError, TypeError, AttributeError):
            raise ValidationError('已选记录编号无效') from None
        if len(selected_ids) > 20:
            raise ValidationError('一次最多核对 20 个已选记录')
        case = await self.demo.risk.risk_case(case_id)
        product_id = (case.scope or {}).get('product_id')
        keyword = keyword.strip()
        if kind == 'tasks':
            model = InspectionTask
            mode = model.meta_data['execution_mode'].as_string()
            query = select(model).where(model.org_id == self.org_id, model.deleted_at.is_(None),
                model.quality_product_id == product_id, mode == 'demo' if self.demo.is_demo else func.coalesce(mode, '') != 'demo')
            if not product_id: query = query.where(False)
            search = [model.spec_code.contains(keyword, autoescape=True), model.meta_data['task_name'].as_string().contains(keyword, autoescape=True),
                model.meta_data['product_name'].as_string().contains(keyword, autoescape=True)]
            part = keyword.replace('-', '').lower()
            if len(part) >= 4 and all(c in '0123456789abcdef' for c in part):
                search.append(func.lower(func.hex(model.id)).contains(part, autoescape=True))
        else:
            model = QualitySourceRecord
            query = (await self.demo.risk.scoped_records()).where(model.record_type == 'inspection_report',
                model.data_nature == ('synthetic' if self.demo.is_demo else 'observed'),
                or_(model.created_by == self.actor, model.authorization_scope.in_(['organization','business','public'])))
            if product_id:
                query = query.where(model.product_ref['product_id'].as_string() == product_id)
            elif (case.scope or {}).get('enterprise_id'):
                query = query.where(func.coalesce(model.enterprise_ref['enterprise_id'].as_string(), model.enterprise_ref['id'].as_string()) == case.scope['enterprise_id'])
            else: query = query.where(False)
            search = [model.content['title'].as_string().contains(keyword, autoescape=True),
                model.content['text'].as_string().contains(keyword, autoescape=True), model.external_record_id.contains(keyword, autoescape=True)]
        def serialize(row):
            if kind == 'tasks':
                return {'id':row.id, 'label':f"{'演示' if self.demo.is_demo else '检测'}任务 · {row.spec_code} · {row.id}", 'status':row.status}
            return {'id':row.id, 'label':str((row.content or {}).get('title') or (row.content or {}).get('text') or '检测资料')[:160],
                'already_linked':row.id in (case.source_record_ids or [])}
        chosen = list(await self.db.scalars(query.where(model.id.in_(selected_ids)))) if selected_ids else []
        if keyword: query = query.where(or_(*search))
        total = await self.db.scalar(select(func.count()).select_from(query.subquery()))
        rows = await self.db.scalars(query.order_by(model.created_at.desc(), model.id.desc()).offset((page-1)*size).limit(size))
        return {'items':[serialize(r) for r in rows], 'total':int(total or 0), 'page':page, 'size':size,
            'selected':[serialize(r) for r in chosen], 'unavailable_selected_ids':sorted(set(selected_ids)-{r.id for r in chosen})}

    async def row(self, link_id):
        query = select(SupervisionRecord).where(SupervisionRecord.id == link_id,
            SupervisionRecord.org_id == self.org_id, SupervisionRecord.kind == KIND)
        row = await self.db.scalar(query.execution_options(populate_existing=True))
        if not row:
            raise NotFoundError("验证关联不存在")
        if row.data.get('execution_mode','demo') != self.demo.mode:
            raise ForbiddenError('验证关联不属于当前业务环境')
        await self.demo.risk.risk_case(row.data["case_id"], lock=self.demo.locked)
        if self.demo.locked:
            row = await self.db.scalar(self.demo.read(query))
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
        data = copy.deepcopy(row.data)
        if data.get('execution_returns'):
            service = RiskExecutionEvidenceService(self.db, self.current, self.demo.risk.storage)
            redacted = False
            for entry in data['execution_returns']:
                entry['issues'] = []
                try:
                    await service.authorize(entry['ref'])
                except (ForbiddenError, NotFoundError) as error:
                    entry.update(summary=None, note='原报告已不可访问，仅保留关联与撤回操作记录', withdrawal_note=None)
                    entry['issues'].append(error.message)
                    redacted = True
                else:
                    if not entry.get('withdrawn_at'):
                        try:
                            await service.resolve(case, entry['ref'])
                        except (ForbiddenError, NotFoundError, ValidationError, ConflictError) as error:
                            entry['issues'].append(error.message)
                issues.extend(entry['issues'])
            if redacted:
                data['events'] = [{k:v for k,v in event.items() if k != 'note'} for event in data['events']]
        return {"id": row.id, "status": row.status, "revision": row.version, "created_by": row.created_by,
            "is_latest_assessment": bool(latest and latest.id == assessment.id), "issues": list(dict.fromkeys(issues)),
            "boundary": self.boundary, **data}

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
            if row.version != payload.expected_revision or row.data.get("record_ids") or row.data.get('execution_returns'):
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

    async def execution_candidates(self, link_id, *, page=1, size=20):
        await self.guard()
        if self.demo.is_demo:
            raise ValidationError('演示环境不接入正式检测结果，请使用模拟资料回流')
        row = await self.row(link_id)
        case = await self.demo.risk.risk_case(row.data['case_id'])
        if row.data['mode'] != 'verify' or not row.data.get('task_id'):
            raise ValidationError('请先为验证分支关联已有的同产品检测任务')
        task = await self.task(row.data['task_id'], case)
        service = RiskExecutionEvidenceService(self.db, self.current, self.demo.risk.storage)
        service.permissions()
        query = select(InspectionExecutionRun).where(InspectionExecutionRun.org_id == self.org_id,
            InspectionExecutionRun.task_id == task.id, InspectionExecutionRun.status == 'accepted')
        total = await self.db.scalar(select(func.count()).select_from(query.subquery()))
        runs = await self.db.scalars(query.order_by(InspectionExecutionRun.created_at.desc(), InspectionExecutionRun.id.desc())
            .offset((page-1)*size).limit(size).execution_options(populate_existing=True))
        returned = await execution_returns(self.db, self.org_id, case.id)
        items = []
        for run in runs:
            item = {'id':run.id, 'row_version':run.row_version, 'reviewed_at':run.reviewed_at,
                'eligible':False, 'issues':[], 'summary':None, 'definition_hash':None,
                'already_returned':any(e['ref']['run_id'] == run.id for e in returned)}
            try:
                ref = await service.checked(case, run)
                item.update(eligible=True, definition_hash=ref['definition_hash'], summary=service.summary(run))
            except (ForbiddenError, NotFoundError, ValidationError, ConflictError) as error:
                item['issues'].append(error.message)
            items.append(item)
        return {'items':items, 'total':total, 'page':page, 'size':size}

    async def return_execution(self, link_id, payload):
        actor = await self.guard(write=True)
        if self.demo.is_demo:
            raise ValidationError('演示环境不能回流正式检测结果')
        row = await self.row(link_id)
        case = await self.demo.risk.risk_case(row.data['case_id'], lock=True)
        if row.data['mode'] != 'verify' or not row.data.get('task_id'):
            raise ConflictError('验证选择已变化或尚未关联检测任务')
        task = await self.task(row.data['task_id'], case)
        service = RiskExecutionEvidenceService(self.db, self.current, self.demo.risk.storage)
        service.permissions()
        run = await service.native.get(str(payload.run_id), lock=True)
        if run.task_id != task.id:
            raise ValidationError('检测结果不属于本次关联的检测任务')
        ref = await service.checked(case, run)
        if ref['definition_hash'] != payload.expected_run_hash:
            raise ConflictError('检测结果或复核已变化，请刷新后重新选择')
        entries = await execution_returns(self.db, self.org_id, case.id, lock=True)
        old = next((e for e in entries if e['ref']['run_id'] == run.id), None)
        if old:
            if old['ref'] != ref:
                raise ConflictError('原回流结果已变化，请先明确撤回旧引用')
            if old['note'] != payload.note:
                raise ConflictError('该结果已回流，原说明已固定，请使用原关联查看记录')
            return {**await self.serialize(await self.row(old['link_id'])), 'reused':True, 'return_id':old['id']}
        if row.version != payload.expected_revision:
            raise ConflictError('验证关联已更新，请刷新后重试')
        entry = {'id':str(uuid7()), 'ref':ref, 'summary':service.summary(run), 'note':payload.note,
            'returned_by':self.actor, 'returned_at':self.demo.event(actor, 'execution_returned')['at'], 'withdrawn_at':None}
        row.version += 1
        row.status = 'returned'
        row.data = {**row.data, 'execution_returns':[*row.data.get('execution_returns', []), entry],
            'events':[*row.data['events'], self.demo.event(actor, 'execution_returned', return_id=entry['id'], run_id=run.id, note=payload.note)]}
        case.status = 'awaiting_evidence'
        await self.db.flush()
        return {**await self.serialize(row), 'reused':False, 'return_id':entry['id']}

    async def withdraw_execution(self, link_id, return_id, payload):
        actor = await self.guard(write=True)
        if self.demo.is_demo:
            raise ValidationError('演示环境不操作正式检测结果回流')
        row = await self.row(link_id)
        case = await self.demo.risk.risk_case(row.data['case_id'], lock=True)
        entries = copy.deepcopy(row.data.get('execution_returns', []))
        entry = next((e for e in entries if e['id'] == return_id), None)
        if not entry:
            raise NotFoundError('检测结果回流记录不存在')
        if self.actor not in {entry['returned_by'], row.created_by}:
            raise ForbiddenError('请由验证编写人或本次回流人撤回引用')
        if entry.get('withdrawn_at'):
            return {**await self.serialize(row), 'reused':True}
        if row.version != payload.expected_revision:
            raise ConflictError('验证关联已更新，请刷新后撤回')
        entry.update(withdrawn_at=self.demo.event(actor, 'execution_withdrawn')['at'], withdrawn_by=self.actor,
            withdrawal_note=payload.note)
        row.version += 1
        row.status = 'returned' if row.data.get('record_ids') or any(not e.get('withdrawn_at') for e in entries) else 'reference_withdrawn'
        row.data = {**row.data, 'execution_returns':entries, 'events':[*row.data['events'],
            self.demo.event(actor, 'execution_withdrawn', return_id=entry['id'], note=payload.note)]}
        case.status = 'awaiting_evidence'
        await self.db.flush()
        return {**await self.serialize(row), 'reused':False}

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
