"""Suggestions from reviewed assessments, with protected legacy snapshot reads."""
import copy
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.models.collab import CollabMessage, CollabMessageReceipt
from app.models.meeting import MeetingMessage
from app.models.quality_risk import QualityProduct, ProductCategory, QualityRiskCase, QualityRiskAssessment
from app.models.supervision import SupervisionRecord
from app.schemas.demo_sampling import DemoSamplingContent
from app.services.demo_risk_workflow_service import is_manual_demo, now
from app.services.quality_risk_service import stable_hash
from app.services.risk_collaboration_service import RiskCollaborationService, KIND as COLLAB_KIND
from app.services.risk_workflow_context_service import RiskWorkflowContextService

KIND = "demo-sampling-suggestions"
ASSESSMENT_SCHEMA = 'risk-sampling-assessment-v2'
BOUNDARY = "演示抽查建议，仅用于模拟流程；不进入正式候选、不启动抽查或检测。真实抽样数量、批次、地点、时间和标准适用性仍需核实。"


class DemoSamplingService:
    def __init__(self, db, current):
        self.db, self.current = db, current
        self.collab = RiskCollaborationService(db, current)
        self.demo = RiskWorkflowContextService(db,current)
        self.collab.demo = self.demo  # Only retained for old snapshot authorization.
        self.org_id, self.actor = self.demo.org_id, self.demo.actor
        self.kind = KIND if self.demo.is_demo else 'risk-sampling-suggestions'
        self.draft_status = 'demo_draft' if self.demo.is_demo else 'draft'
        self.confirmed_status = 'demo_confirmed' if self.demo.is_demo else 'confirmed'
        self.boundary = BOUNDARY if self.demo.is_demo else '抽查建议仅提供对象与核查方向；正式计划仍需独立批准，不自动启动抽查或检测。未知执行信息不作推定。'

    async def guard(self, write=False):
        actor=await self.demo.guard(write=write)
        if str(self.current.role)!='expert':raise ForbiddenError('抽查建议由研判专家访问')
        return actor

    async def context(self,case_id,collaboration_id=None):
        if collaboration_id:return await self._legacy_context(case_id,collaboration_id)
        case=await self.demo.risk.risk_case(case_id,lock=self.demo.locked)
        assessment=await self.demo.latest(case)
        if not assessment:raise ConflictError('事项尚无可用研判')
        if self.demo.is_demo and (not is_manual_demo(assessment) or assessment.status!='demo_reviewed' or assessment.trust_status!='demo_reviewed'):
            raise ConflictError('请先完成最新研判的独立演示复核')
        if not assessment.reviewed_by or assessment.reviewed_by==assessment.submitted_by:
            raise ConflictError('研判缺少独立复核记录')
        from app.services.execution_evidence_service import ExecutionEvidenceService
        access=ExecutionEvidenceService(self.db,self.current,self.demo.risk.storage)
        for rid in case.source_record_ids or []:
            record=await self.demo.risk.record(rid)
            if not access.record_authorized(record):raise ForbiddenError('不在来源资料的授权范围')
        await self.demo.ensure_current(case,assessment)
        validation=await self.demo.validation(case,assessment)
        objects=[]
        for kind,model,label in (('product',QualityProduct,'产品'),('enterprise',SupervisionRecord,'企业'),('category',ProductCategory,'产品类别')):
            oid=(case.scope or {}).get(f'{kind}_id')
            if oid:
                obj=await self.db.scalar(self.demo.read(select(model).where(model.id==oid,model.org_id==self.org_id)))
                objects.append({'kind':kind,'label':label,'id':oid,'name':obj.name if obj else '未知'})
        snapshot={'schema':ASSESSMENT_SCHEMA,'case_id':case.id,'case_code':case.code,'case_title':case.title,'scope':copy.deepcopy(case.scope),
            'objects':objects,'assessment_id':assessment.id,'assessment_version':assessment.version,'assessment_hash':self.collab.fingerprint(assessment),
            'basis_hash':validation['basis_hash'],'source_record_ids':sorted(case.source_record_ids or []),'evidence_ids':sorted(case.evidence_ids or []),
            'conclusion':copy.deepcopy(self.demo.content(assessment,case)),'review':{'reviewed_by':assessment.reviewed_by,
                'reviewed_at':assessment.reviewed_at.isoformat() if assessment.reviewed_at else None,'comment':assessment.review_comment},
            'reader_ids':sorted({assessment.submitted_by,assessment.reviewed_by}),'collaboration_id':None,'collaboration_purpose':'',
            'decision_note':'','opinions':[],'source_link':f'/app/risk-assessments?case_id={case.id}&assessment_id={assessment.id}',
            'execution_mode':self.demo.mode,'llm_called':False if self.demo.is_demo else bool((assessment.model_versions or {}).get('llm_called'))}
        if not self.demo.is_demo:
            from app.services.risk_decision_context_service import RiskDecisionContextService
            snapshot['source_ref']=(await RiskDecisionContextService(self.db,self.current,self.demo.risk.storage).accepted(case.id))['source_ref']
        return snapshot,stable_hash(snapshot)

    async def _legacy_context(self, case_id, collaboration_id):
        case = await self.demo.risk.risk_case(case_id, lock=self.demo.locked)
        assessment = await self.demo.latest(case)
        if not assessment:
            raise ConflictError('事项尚无可用研判')
        if self.demo.is_demo and (not is_manual_demo(assessment) or assessment.status != "demo_reviewed" or assessment.trust_status != "demo_reviewed"):
            raise ConflictError("请先完成最新演示研判的独立复核")
        if not assessment.reviewed_by or assessment.reviewed_by == assessment.submitted_by:
            raise ConflictError("研判缺少独立演示复核记录")
        await self.demo.ensure_current(case, assessment)
        # Check native room membership and effective permissions before reading opinions.
        await self.collab.get(collaboration_id)
        link = await self.db.scalar(self.demo.read(select(SupervisionRecord).where(
            SupervisionRecord.id == collaboration_id, SupervisionRecord.org_id == self.org_id,
            SupervisionRecord.kind == COLLAB_KIND)))
        if not link or link.data["case_id"] != case.id or link.data["assessment_id"] != assessment.id:
            raise ConflictError("协同必须关联本事项最新复核版本")
        if link.data["assessment_hash"] != self.collab.fingerprint(assessment):
            raise ConflictError("协同固定的研判内容已变化")
        request = await self.db.scalar(self.demo.read(select(CollabMessage).where(
            CollabMessage.id == link.data["message_id"], CollabMessage.org_id == self.org_id,
            CollabMessage.deleted_at.is_(None))))
        receipt = await self.db.scalar(self.demo.read(select(CollabMessageReceipt).where(
            CollabMessageReceipt.org_id == self.org_id, CollabMessageReceipt.message_id == link.data["message_id"],
            CollabMessageReceipt.recipient_id == link.data["coordinator_id"], CollabMessageReceipt.recipient_type == "user",
            CollabMessageReceipt.deleted_at.is_(None))))
        if not request or not receipt or receipt.action_status != "done":
            raise ConflictError("请先由负责人完成本版协同工作项")
        # Hash the complete public history, not only the newest page. A changed or
        # recalled earlier opinion must invalidate an old suggestion as well.
        messages = await self.db.scalars(self.demo.read(select(MeetingMessage).where(
            MeetingMessage.org_id == self.org_id, MeetingMessage.room_id == link.data["room_id"],
            MeetingMessage.deleted_at.is_(None), MeetingMessage.message_type == "user").order_by(MeetingMessage.seq_no)))
        opinions = [{"id": m.id, "author": m.username, "origin": "meeting", "content":
            "该讨论已撤回" if (m.metadata_json or {}).get("recalled_at") else m.content}
            for m in messages if not (m.metadata_json or {}).get("private_recipient_user_id")
            and not (m.metadata_json or {}).get("agent_sidecar_question")]
        comments = await self.db.scalars(self.demo.read(select(CollabMessage).where(
            CollabMessage.org_id == self.org_id, CollabMessage.thread_id == link.data["thread_id"],
            CollabMessage.reply_to_message_id == request.id, CollabMessage.message_type == "text",
            CollabMessage.deleted_at.is_(None)).order_by(CollabMessage.created_at, CollabMessage.id)))
        opinions += [{"id": m.id, "author": link.data["participant_names"].get(m.sender_id, "专家"),
            "origin": "collab", "content": m.content} for m in comments]
        validation = await self.demo.validation(case, assessment)
        content = self.demo.content(assessment, case)
        objects = []
        for kind, model, label in (("product", QualityProduct, "产品"), ("enterprise", SupervisionRecord, "企业"), ("category", ProductCategory, "产品类别")):
            oid = (case.scope or {}).get(f"{kind}_id")
            if oid:
                obj = await self.db.scalar(self.demo.read(select(model).where(model.id == oid, model.org_id == self.org_id)))
                objects.append({"kind": kind, "label": label, "id": oid, "name": obj.name if obj else "未知"})
        snapshot = {"case_id": case.id, "case_code": case.code, "case_title": case.title,
            "scope": copy.deepcopy(case.scope), "objects": objects, "assessment_id": assessment.id, "assessment_version": assessment.version,
            "assessment_hash": self.collab.fingerprint(assessment), "basis_hash": validation["basis_hash"],
            "source_record_ids": sorted(case.source_record_ids or []), "evidence_ids": sorted(case.evidence_ids or []),
            "conclusion": copy.deepcopy(content), "review": {"reviewed_by": assessment.reviewed_by,
                "reviewed_at": assessment.reviewed_at.isoformat() if assessment.reviewed_at else None,
                "comment": assessment.review_comment},
            "collaboration_id": link.id, "collaboration_purpose": link.data["purpose"],
            "decision_note": (request.metadata_json or {}).get("risk_decision_note", ""), "opinions": opinions,
            "source_link": link.data["source_link"], "execution_mode": self.demo.mode,
            "llm_called": False if self.demo.is_demo else bool((assessment.model_versions or {}).get('llm_called'))}
        if not self.demo.is_demo:
            from app.services.risk_decision_context_service import RiskDecisionContextService
            snapshot['source_ref'] = (await RiskDecisionContextService(self.db,self.current,self.demo.risk.storage).accepted(case.id))['source_ref']
        return snapshot, stable_hash(snapshot)

    async def candidates(self, case_id=None):
        await self.guard()
        query=select(QualityRiskCase).where(QualityRiskCase.org_id==self.org_id,QualityRiskCase.deleted_at.is_(None))
        if case_id:query=query.where(QualityRiskCase.id==case_id)
        cases = list(await self.db.scalars(query))
        items, blockers = [], []
        for case in cases:
            try:
                snapshot, fingerprint = await self.context(case.id)
                items.append({"snapshot": snapshot, "context_hash": fingerprint})
            except (ConflictError, ForbiddenError, NotFoundError, ValidationError) as error:
                blockers.append(str(error.message))
        return {"items": items, "blockers": list(dict.fromkeys(blockers)), "boundary": self.boundary}

    async def page(self, case_id=None, *, candidates=False, size=20, cursor=None, keyword=''):
        from sqlalchemy import String,cast,or_,func
        from app.services.record_scan_page import scan_records
        await self.guard()
        if candidates:
            query=select(QualityRiskCase).where(QualityRiskCase.org_id==self.org_id,QualityRiskCase.deleted_at.is_(None))
            if case_id:query=query.where(QualityRiskCase.id==case_id)
            if keyword.strip():query=query.where(or_(QualityRiskCase.title.contains(keyword.strip(),autoescape=True),QualityRiskCase.code.contains(keyword.strip(),autoescape=True)))
            blockers=[]
            async def candidate(row):
                try:
                    snapshot,token=await self.context(row.id)
                    return {'snapshot':snapshot,'context_hash':token}
                except (ConflictError,ValidationError) as error:blockers.append(error.message);return None
            result=await scan_records(self.db,query,candidate,scope=[self.org_id,self.actor,self.demo.mode,case_id,keyword.strip(),size],
                purpose='risk-sampling-assessment-v2',size=size,cursor=cursor,model=QualityRiskCase)
            return {**result,'blockers':list(dict.fromkeys(blockers)),'boundary':self.boundary}
        query=select(SupervisionRecord).where(SupervisionRecord.org_id==self.org_id,SupervisionRecord.kind==self.kind,
            func.coalesce(SupervisionRecord.data['execution_mode'].as_string(),'demo')==self.demo.mode)
        if case_id:query=query.where(SupervisionRecord.data['snapshot']['case_id'].as_string()==case_id)
        if keyword.strip():query=query.where(or_(SupervisionRecord.name.contains(keyword.strip(),autoescape=True),SupervisionRecord.data['snapshot']['case_code'].as_string().contains(keyword.strip(),autoescape=True)))
        async def item(row):
            await self.row(row.id)
            return await self.serialize(row)
        result=await scan_records(self.db,query,item,scope=[self.org_id,self.actor,self.demo.mode,case_id,False,keyword.strip(),size],purpose='risk-sampling-page-v1',size=size,cursor=cursor)
        return {**result,'blockers':[],'boundary':self.boundary}

    async def row(self, suggestion_id):
        row = await self.db.scalar(self.demo.read(select(SupervisionRecord).where(
            SupervisionRecord.id == suggestion_id, SupervisionRecord.org_id == self.org_id, SupervisionRecord.kind == self.kind)))
        if not row:
            raise NotFoundError("演示抽查建议不存在")
        snapshot=row.data['snapshot']
        if snapshot.get('collaboration_id'):await self.collab.get(snapshot['collaboration_id'])
        else:
            await self.demo.risk.risk_case(snapshot['case_id'])
            assessment=await self.db.scalar(select(QualityRiskAssessment.id).where(QualityRiskAssessment.id==snapshot['assessment_id'],
                QualityRiskAssessment.org_id==self.org_id,QualityRiskAssessment.risk_case_id==snapshot['case_id'],QualityRiskAssessment.deleted_at.is_(None)))
            if not assessment:raise NotFoundError('来源研判版本已不可访问')
            from app.services.execution_evidence_service import ExecutionEvidenceService
            access=ExecutionEvidenceService(self.db,self.current,self.demo.risk.storage)
            for rid in snapshot['source_record_ids']:
                record=await self.demo.risk.record(rid)
                if not access.record_authorized(record):raise ForbiddenError('建议引用资料的访问授权已撤回')
        return row

    async def serialize(self, row):
        snapshot = row.data["snapshot"]
        try:
            _, fingerprint = await self.context(snapshot["case_id"], snapshot["collaboration_id"])
            current = fingerprint == row.data["context_hash"]
            reason = "" if current else ("研判、复核或公开协同意见已变化，请依据当前版本另建建议" if snapshot.get("collaboration_id") else "研判、证据或复核已变化，请依据当前版本另建建议")
        except (ConflictError, ForbiddenError, NotFoundError, ValidationError) as error:
            current, reason = False, error.message
        return {"id": row.id, "code": row.code, "title": row.name, "status": row.status,
            "effective_status": row.status if current else "needs_reassessment", "is_current": current,
            "stale_reason": reason, "revision": row.version, "created_by": row.created_by,
            "created_at": row.created_at, "can_edit": current and not snapshot.get("collaboration_id") and row.status == self.draft_status and row.created_by == self.actor,
            "boundary": self.boundary, **copy.deepcopy(row.data)}

    async def list(self, case_id=None):
        await self.guard()
        rows = list(await self.db.scalars(self.demo.read(select(SupervisionRecord).where(SupervisionRecord.org_id == self.org_id,
            SupervisionRecord.kind == self.kind).order_by(SupervisionRecord.created_at.desc()))))
        result = []
        for row in rows:
            if case_id and row.data["snapshot"]["case_id"] != case_id:
                continue
            try:
                await self.row(row.id)
            except (ForbiddenError, NotFoundError):
                continue
            result.append(await self.serialize(row))
        return result

    async def get(self, suggestion_id):
        await self.guard()
        return await self.serialize(await self.row(suggestion_id))

    async def create(self, case_id, payload):
        actor = await self.guard(write=True)
        snapshot, fingerprint = await self.context(case_id, str(payload.collaboration_id) if payload.collaboration_id else None)
        if snapshot["assessment_id"] != str(payload.assessment_id) or fingerprint != payload.expected_context_hash:
            raise ConflictError("来源上下文已更新，请刷新核对后创建建议")
        existing = await self.db.scalar(self.demo.read(select(SupervisionRecord).where(
            SupervisionRecord.org_id == self.org_id, SupervisionRecord.kind == self.kind, SupervisionRecord.code == fingerprint)))
        if existing:
            return {**await self.serialize(existing), "reused": True}
        row = SupervisionRecord(id=str(uuid5(NAMESPACE_URL, f"demo-sampling:{self.org_id}:{fingerprint}")),
            org_id=self.org_id, kind=self.kind, code=fingerprint, name=f"【{'演示' if self.demo.is_demo else ''}抽查建议】{snapshot['case_code']} · 第{snapshot['assessment_version']}版",
            status=self.draft_status, version=1, created_by=self.actor,
            data={"execution_mode": self.demo.mode, "context_hash": fingerprint, "snapshot": snapshot,
                "content": DemoSamplingContent().model_dump(), "events": [self.demo.event(actor, "created")],
                "confirmed_by": None, "confirmed_at": None})
        self.db.add(row)
        await self.db.flush()
        return {**await self.serialize(row), "reused": False}

    async def mutate(self, suggestion_id, payload, confirm=False):
        actor = await self.guard(write=True)
        row = await self.row(suggestion_id)
        if row.created_by != self.actor:
            raise ForbiddenError("只有建议编写人可以修改或确认")
        if row.version != payload.expected_revision or row.status != self.draft_status:
            raise ConflictError("建议已更新或固定，请刷新查看")
        _, fingerprint = await self.context(row.data["snapshot"]["case_id"], row.data["snapshot"]["collaboration_id"])
        if fingerprint != row.data["context_hash"]:
            raise ConflictError("依据已变化，请保留此记录并根据当前依据另建建议")
        data = copy.deepcopy(row.data)
        if confirm:
            if any(not data["content"][field].strip() for field in ("rationale", "focus", "limitations")):
                raise ValidationError("确认前请保存抽查理由、关注内容和限制条件")
            row.status = self.confirmed_status
            data.update(confirmed_by=self.actor, confirmed_at=now())
        else:
            data["content"] = payload.content.model_dump(mode="json")
        row.version += 1
        data["events"].append(self.demo.event(actor, "confirmed" if confirm else "saved", revision=row.version))
        row.data = data
        await self.db.flush()
        return await self.serialize(row)
