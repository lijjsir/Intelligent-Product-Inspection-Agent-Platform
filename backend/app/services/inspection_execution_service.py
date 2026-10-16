import copy
from datetime import date
from sqlalchemy import select,func
from app.core.datetime import utcnow
from app.core.ids import uuid7
from app.core.exceptions import ConflictError,ForbiddenError,NotFoundError,ValidationError
from app.core.permissions import has_permission
from app.models.inspection_execution import InspectionExecutionRun,InspectionExecutionAction,InspectionPolicyPublication
from app.models.inspection_standard_library import StandardDocument,InspectionStandardLibrary
from app.models.standard_admission import StandardDocumentRevision
from app.models.inspection_spec import InspectionSpec,SpecChangeLog
from app.models.supervision import MeasurementRecord,SupervisionRecord
from app.models.quality_risk import QualityAttachment,QualitySourceRecord
from app.models.task import InspectionTask
from app.repositories.rag_space_repo import RagSpaceRepository
from app.services.knowledge_source_service import fingerprint
from app.services.inspection_requirement_engine import evaluate_plan
from app.services.execution_evidence_service import ExecutionEvidenceService,blocker
from app.services.inspection_execution_context_service import InspectionExecutionContextService,valid_uuid
from app.services.inspection_execution_policy_service import evaluate_policy_inputs


class InspectionExecutionService:
    def __init__(self,session,current,storage=None):
        self.session,self.current=session,current;self.org_id=current.org_id;self.storage=storage

    async def task(self,task_id,*,lock=False):
        q=select(InspectionTask).where(InspectionTask.id==task_id,InspectionTask.org_id==self.org_id,InspectionTask.deleted_at.is_(None))
        if str(self.current.role)=="user":q=q.where(InspectionTask.created_by==self.current.user_id)
        if str(self.current.role) not in {"user","expert"}:raise ForbiddenError("检测执行与结果由任务发起者或授权专家处理")
        if lock:q=q.with_for_update().execution_options(populate_existing=True)
        task=(await self.session.execute(q)).scalar_one_or_none()
        if not task:raise NotFoundError("任务不在当前授权范围")
        return task

    async def bindings(self,refs,product_category,production_date):
        try:date.fromisoformat(production_date)
        except (TypeError,ValueError):raise ValidationError("需提供有效的实际生产日期，不能自动套用最新版标准") from None
        rules=[];sources=[];issues=[];seen=set()
        for ref in refs:
            key=(ref["revision_id"],ref["candidate_id"])
            if key in seen:continue
            seen.add(key)
            q=select(StandardDocumentRevision,StandardDocument,InspectionStandardLibrary).join(StandardDocument,
                StandardDocument.id==StandardDocumentRevision.document_id).join(InspectionStandardLibrary,
                InspectionStandardLibrary.id==StandardDocument.library_id).where(StandardDocumentRevision.id==ref["revision_id"],
                StandardDocumentRevision.org_id==self.org_id,StandardDocument.org_id==self.org_id,InspectionStandardLibrary.org_id==self.org_id,
                StandardDocument.deleted_at.is_(None),InspectionStandardLibrary.deleted_at.is_(None),InspectionStandardLibrary.is_active.is_(True))
            row=(await self.session.execute(q)).first()
            if not row:raise NotFoundError("标准修订不在当前组织范围")
            revision,document,library=row
            if revision.publication_status!="published" or revision.review_status!="approved" or document.published_revision_id!=revision.id:
                issues.append("标准修订尚未发布、已经撤回或已被暂停")
            meta=revision.snapshot
            if meta.get("product_category")!=product_category:issues.append("产品类别与所选标准范围不匹配")
            lower=meta.get("production_from") or meta.get("effective_from");upper=meta.get("production_to") or meta.get("effective_to")
            if not lower or not meta.get("scope_notes"):issues.append("标准适用日期、范围或过渡条件尚未核对")
            elif production_date<lower or (upper and production_date>upper):issues.append("生产日期不在已核对的适用区间内")
            if meta.get("standard_status") in {"被代替","废止"} and not upper:issues.append("历史标准缺少适用截止或过渡范围")
            candidate=next((c for c in revision.candidates_json or [] if c["id"]==ref["candidate_id"]),None)
            if not candidate:raise NotFoundError("标准检测要求不存在")
            if candidate.get("status")!="confirmed" or not candidate.get("reviewed_by"):issues.append("检测项目要求尚未独立确认")
            if candidate.get("candidate_type") not in {"inspection_requirement","method_condition"}:issues.append("条款用途尚未专业确认，或只是参考正文，不能进入检测执行")
            rule=copy.deepcopy(candidate);rule.update(revision_id=revision.id,standard_no=meta["standard_no"])
            rules.append(rule)
            sources.append({"revision_id":revision.id,"candidate_id":candidate["id"],"document_id":document.id,
                "library_id":library.id,"file_hash":revision.file_hash,"definition_hash":fingerprint({"snapshot":meta,"candidate":candidate}),
                "standard_no":meta["standard_no"],"clause_no":candidate.get("clause_no"),"page_number":candidate.get("page_number")})
        return rules,sources,list(dict.fromkeys(issues))

    async def observation(self,reference,task,session_id):
        if reference["kind"]=="measurement_record":
            row=(await self.session.execute(select(MeasurementRecord).where(MeasurementRecord.id==reference["id"],
                MeasurementRecord.org_id==self.org_id))).scalar_one_or_none()
            if not row or not session_id or row.session_id!=session_id:raise NotFoundError("测量记录未绑定本次会话")
            session=(await self.session.execute(select(SupervisionRecord).where(SupervisionRecord.id==session_id,
                SupervisionRecord.org_id==self.org_id,SupervisionRecord.kind=="inspection-sessions"))).scalar_one_or_none()
            if not session or session.data.get("task_id")!=task.id:raise ForbiddenError("会话不属于本次任务")
            data=dict(row.data)
            if data.get("item")!=reference["measurement_key"] or str(row.sample_id)!=reference["sample_id"]:
                raise ValidationError("测量字段或样品与来源记录不一致")
            obs={"evidence_id":row.id,"kind":"measurement_record","source_version":fingerprint(data),"session_id":session_id,
                "sample_id":str(row.sample_id),"measurement_key":data["item"],"value":data.get("value"),"unit":data.get("unit"),
                "method":data.get("method"),"conditions":data.get("conditions") or {},"uncertainty":data.get("uncertainty"),
                "quality_flag":data.get("quality_flag"),"validation_status":row.validation_status or "unverified",
                "device_id":str(row.device_id),"calibration_version":row.calibration_version,"event_id":row.event_id}
            _,context=await ExecutionEvidenceService(self.session,self.current,self.storage).measurement(obs,task.id,session_id)
            return {**obs,"observation_identity":context.get("observation_identity"),"source_context":context}
        attachment=(await self.session.execute(select(QualityAttachment).where(QualityAttachment.id==reference["id"],
            QualityAttachment.org_id==self.org_id,QualityAttachment.deleted_at.is_(None)))).scalar_one_or_none()
        if not attachment or attachment.mime_type!="application/pdf":raise NotFoundError("需引用实际PDF检测报告附件")
        task_links=((task.meta_data or {}).get("execution_inputs") or {}).get("report_links",[])
        linked=any(link["attachment_id"]==attachment.id for link in task_links)
        if attachment.uploaded_by!=self.current.user_id and not (linked and attachment.uploaded_by==task.created_by and
                has_permission("inspection_execution_review",self.current.role)):
            records=(await self.session.execute(select(QualitySourceRecord).where(QualitySourceRecord.org_id==self.org_id,
                QualitySourceRecord.deleted_at.is_(None)))).scalars().all()
            permitted=has_permission("quality_material_read_business",self.current.role) and any(attachment.id in (r.attachment_ids or []) and r.authorization_scope!="private" for r in records)
            if not permitted:raise NotFoundError("报告未授权给当前业务范围")
        if reference.get("value") is None or not reference.get("report_page") or not reference.get("report_item"):
            raise ValidationError("报告转录值须记录原文页码、项目及数值")
        original_sample=next((s for link in task_links if link["attachment_id"]==attachment.id for s in link.get("samples",[]) if s["id"]==reference["sample_id"]),None)
        obs={"evidence_id":f"{attachment.id}:p{reference['report_page']}:{reference['measurement_key']}:{reference['sample_id']}",
            "kind":"report_attachment","attachment_id":attachment.id,"source_version":attachment.sha256,"file_name":attachment.file_name,
            "sample_id":reference["sample_id"],"measurement_key":reference["measurement_key"],"value":reference["value"],
            "sample_label":original_sample["label"] if original_sample else reference["sample_id"],
            "unit":reference["unit"],"method":reference["method"],"conditions":reference.get("conditions") or {},
            "uncertainty":reference.get("uncertainty"),"report_page":reference["report_page"],"report_item":reference["report_item"],
            "quality_flag":"valid","validation_status":"reported","transcription_verified":False}
        context=await ExecutionEvidenceService(self.session,self.current,self.storage,review_owner=task.created_by,
            review_attachment_ids=[attachment.id] if linked else []).report(obs)
        return {**obs,"observation_identity":context["observation_identity"],"source_context":context}

    async def policies(self):
        rows=(await self.session.execute(select(InspectionPolicyPublication).where(InspectionPolicyPublication.org_id==self.org_id)
            .order_by(InspectionPolicyPublication.created_at.desc()).limit(200))).scalars().all()
        return [{k:getattr(r,k) for k in ["id","spec_id","snapshot","status","published_by","created_at"]} for r in rows]

    async def publish_policy(self,spec_id,payload):
        if not has_permission("inspection_spec",self.current.role):raise ForbiddenError("执行策略发布需要治理权限")
        spec=(await self.session.execute(select(InspectionSpec).where(InspectionSpec.id==spec_id,
            InspectionSpec.org_id==self.org_id,InspectionSpec.deleted_at.is_(None)).with_for_update())).scalar_one_or_none()
        if not spec:raise NotFoundError("只允许发布本组织的检测与复核策略")
        if not spec.is_active:raise ValidationError("停用策略不能发布")
        identity_payload={k:v for k,v in payload.items() if not (k in {"required_image_count","required_views"} and v is None)
            and not (k=="input_modes" and v==["image","measurement","mixed","report"])}
        raw=fingerprint({"spec_id":spec_id,"payload":identity_payload})
        old=(await self.session.execute(select(InspectionPolicyPublication).where(InspectionPolicyPublication.org_id==self.org_id,
            InspectionPolicyPublication.request_key==payload["request_key"]))).scalar_one_or_none()
        if old:
            if old.payload_hash!=raw:raise ConflictError("相同操作编号不能发布不同策略")
            return {"id":old.id,"snapshot":old.snapshot,"status":old.status}
        from app.services.execution_evidence_service import parsed_time
        if parsed_time(spec.updated_at)!=parsed_time(payload["expected_updated_at"]):raise ConflictError("策略已修改，请刷新后发布")
        publication_no=int(await self.session.scalar(select(func.count()).select_from(InspectionPolicyPublication).where(
            InspectionPolicyPublication.org_id==self.org_id,InspectionPolicyPublication.spec_id==spec.id)) or 0)+1
        snapshot={"name":spec.name,"spec_code":spec.spec_code,"version":spec.version,"source_updated_at":str(spec.updated_at),
            "publication_no":publication_no,"effective_from":str(spec.effective_from) if spec.effective_from else None,
            "effective_to":str(spec.effective_to) if spec.effective_to else None,
            "required_image_count":spec.required_image_count if payload.get("required_image_count") is None else payload["required_image_count"],
            "required_views":spec.required_views or [] if payload.get("required_views") is None else list(dict.fromkeys(v.strip() for v in payload["required_views"] if v.strip())),
            "input_modes":payload.get("input_modes",["image","measurement","mixed","report"]),"image_requirements_apply_to":["image","mixed"],
            "scope":{"quality_product_id":valid_uuid(spec.product_id),"product_family":spec.product_family,"applicable_skus":spec.applicable_skus or []},
            "required_fields":payload["required_fields"],"review_on_fail":payload["review_on_fail"],
            "review_on_report_transcription":True,"require_independent_review":True,"product_limits":"from_confirmed_standard_requirements",
            "legacy_calibration_thresholds":{"confidence":str(spec.ai_gate_confidence_threshold),"evidence":str(spec.ai_gate_evidence_threshold),
                "traceability":str(spec.ai_gate_traceability_threshold)},"reason":payload["reason"]}
        row=InspectionPolicyPublication(org_id=self.org_id,spec_id=spec.id,request_key=payload["request_key"],payload_hash=raw,
            snapshot=snapshot,published_by=self.current.user_id)
        self.session.add(row);await self.session.flush()
        self.session.add(SpecChangeLog(id=str(uuid7()),spec_row_id=spec.id,changed_by=self.current.user_id,version=spec.version,
            change_summary="检测与复核策略发布",snapshot={"publication_id":row.id,"policy":snapshot}))
        return {"id":row.id,"snapshot":snapshot,"status":row.status}

    async def withdraw_policy(self,policy_id,payload):
        if not has_permission("inspection_spec",self.current.role):raise ForbiddenError("执行策略撤回需要治理权限")
        policy=(await self.session.execute(select(InspectionPolicyPublication).where(InspectionPolicyPublication.id==policy_id,
            InspectionPolicyPublication.org_id==self.org_id).with_for_update())).scalar_one_or_none()
        if not policy:raise NotFoundError("策略发布版本不存在")
        if policy.status=="withdrawn":return {"id":policy.id,"status":policy.status}
        policy.status="withdrawn"
        self.session.add(SpecChangeLog(id=str(uuid7()),spec_row_id=policy.spec_id,changed_by=self.current.user_id,
            version=policy.snapshot["version"],change_summary=payload["reason"],snapshot={"publication_id":policy.id,"action":"withdraw"}))
        await self.session.flush();return {"id":policy.id,"status":policy.status}

    async def create(self,payload):
        task=await self.task(payload["task_id"],lock=True)
        if task.status in {"signed","archived"}:raise ConflictError("已归档任务请建立新任务，历史结果不静默改写")
        raw=fingerprint({k:v for k,v in payload.items() if not (k=="context_hash" and v is None) and not (k=="image_view_assignments" and not v)})
        old=(await self.session.execute(select(InspectionExecutionRun).where(InspectionExecutionRun.org_id==self.org_id,
            InspectionExecutionRun.request_key==payload["request_key"]))).scalar_one_or_none()
        if old:
            if old.payload_hash!=raw:raise ConflictError("相同运行编号携带了不同输入")
            return await self.serialize(old)
        context_service=InspectionExecutionContextService(self.session,self.current,self.storage)
        context=await context_service.context(task)
        selection_issues=await context_service.validate_selection(task,payload,context)
        rules,sources,issues=await self.bindings(payload["requirements"],payload["product_category"],payload["production_date"])
        issues.extend(selection_issues)
        policy={"name":"保守复核默认策略","require_independent_review":True,"review_on_fail":True,"review_on_report_transcription":True}
        if payload.get("policy_id"):
            p=(await self.session.execute(select(InspectionPolicyPublication).where(InspectionPolicyPublication.id==payload["policy_id"],
                InspectionPolicyPublication.org_id==self.org_id,InspectionPolicyPublication.status=="published"))).scalar_one_or_none()
            if not p:raise NotFoundError("所选策略未发布或不属于当前组织")
            if context_service.policy_issues(p,context["task_scope"]):raise ValidationError("策略不适用于当前任务",detail={"issues":context_service.policy_issues(p,context["task_scope"])})
            policy=copy.deepcopy(p.snapshot);policy["publication_id"]=p.id
        elif any(not p["issues"] for p in context["policies"]):
            raise ValidationError("本任务已有已发布适用策略，请明确选择执行版本")
        observations=[]
        for ref in payload["observations"]:
            obs=await self.observation(ref,task,payload.get("session_id"))
            if obs["sample_id"] not in payload["sample_ids"]:raise ValidationError("观测样品未列入本次任务范围")
            observations.append(obs)
        policy_inputs=evaluate_policy_inputs(task,context["task_scope"],payload,policy)
        issues.extend(policy_inputs["issues"])
        validation=await ExecutionEvidenceService(self.session,self.current,self.storage,review_owner=task.created_by,
            review_attachment_ids=[r["attachment_id"] for r in context["reports"] if not r["issues"]]).validate(observations,task.id,payload.get("session_id"))
        issues.extend(b["message"] for b in validation["blockers"])
        evaluation=evaluate_plan(rules,payload["sample_ids"],observations,source_issues=issues,policy=policy)
        row=InspectionExecutionRun(org_id=self.org_id,task_id=task.id,session_id=payload.get("session_id"),request_key=payload["request_key"],
            payload_hash=raw,created_by=self.current.user_id,snapshot={"product_category":payload["product_category"],"production_date":payload["production_date"],
                "rules":rules,"source_refs":sources,"sample_ids":payload["sample_ids"],"observations":observations,"policy":policy,
                "task_context":{"scope":context["task_scope"],"context_hash":context["context_hash"],"selected_samples":[s for s in context["samples"] if s["id"] in payload["sample_ids"]],
                    "report_links":[r for r in context["reports"] if any(o.get("attachment_id")==r["attachment_id"] for o in observations)]},
                "policy_inputs":policy_inputs,
                "review_authorization":{"owner":task.created_by,"attachment_ids":[o["attachment_id"] for o in observations if o["kind"]=="report_attachment"],
                    "scope":"this_execution_independent_review"},
                "source_validation":validation},evaluation=evaluation)
        self.session.add(row);await self.session.flush();return await self.serialize(row)

    async def get(self,run_id,*,lock=False):
        q=select(InspectionExecutionRun).where(InspectionExecutionRun.id==run_id,InspectionExecutionRun.org_id==self.org_id)
        if lock:q=q.with_for_update().execution_options(populate_existing=True)
        run=(await self.session.execute(q)).scalar_one_or_none()
        if not run:raise NotFoundError("执行记录不存在")
        await self.task(run.task_id)
        return run

    async def list(self,task_id):
        await self.task(task_id)
        rows=(await self.session.execute(select(InspectionExecutionRun).where(InspectionExecutionRun.org_id==self.org_id,
            InspectionExecutionRun.task_id==task_id).order_by(InspectionExecutionRun.created_at.desc()))).scalars().all()
        return [await self.serialize(row) for row in rows]

    async def verification(self,run):
        refs=[{"revision_id":s["revision_id"],"candidate_id":s["candidate_id"]} for s in run.snapshot["source_refs"]]
        try:_,sources,issues=await self.bindings(refs,run.snapshot["product_category"],run.snapshot["production_date"])
        except (NotFoundError,ValidationError):sources=[];issues=["标准来源已停用、撤回或不可获得；历史快照保留供核对"]
        if not refs or not run.snapshot.get("rules"):issues.append("缺少本次执行的已确认标准要求与来源")
        if {s["definition_hash"] for s in sources}!={s["definition_hash"] for s in run.snapshot["source_refs"]}:issues.append("检测要求定义发生变化")
        authorization=run.snapshot.get("review_authorization") or {}
        task=await self.task(run.task_id)
        validator=ExecutionEvidenceService(self.session,self.current,self.storage,
            review_owner=authorization.get("owner") if authorization.get("owner") in {run.created_by,task.created_by} else None,
            review_attachment_ids=authorization.get("attachment_ids",[]))
        validation=await validator.validate(run.snapshot["observations"],run.task_id,run.session_id)
        validation["blockers"].extend(blocker("standard_source",m) for m in issues)
        if run.snapshot.get("task_context"):
            context_service=InspectionExecutionContextService(self.session,self.current,self.storage)
            task=await self.task(run.task_id)
            context=await context_service.context(task)
            frozen=run.snapshot["task_context"]
            if fingerprint(context["task_scope"])!=fingerprint(frozen["scope"]):
                validation["blockers"].append(blocker("task_scope_changed","任务产品、批次或日期与冻结对象不一致"))
            current_samples={s['id']:s for s in context['samples']}
            for sample in frozen.get('selected_samples',[]):
                current_sample=current_samples.get(sample['id'])
                if not current_sample or current_sample['issues']:
                    validation['blockers'].append(blocker('sample_scope_changed','样品关联、采样登记、产品或批次范围缺失/不匹配'))
            for link in frozen.get("report_links",[]):
                try:await context_service.source_report(task,link,context["task_scope"])
                except (NotFoundError,ValidationError) as exc:validation["blockers"].append(blocker("task_report_changed",exc.message))
            current_inputs=evaluate_policy_inputs(task,context["task_scope"],{"product_category":run.snapshot["product_category"],
                "production_date":run.snapshot["production_date"],"sample_ids":run.snapshot["sample_ids"],"session_id":run.session_id,
                "image_view_assignments":[{"image_hash":i["image_hash"],"view":i["view"]} for i in run.snapshot["policy_inputs"]["images"] if i["view"]]},run.snapshot["policy"])
            if fingerprint(current_inputs)!=fingerprint(run.snapshot["policy_inputs"]):validation["blockers"].append(blocker("policy_input_changed","任务输入或策略必填材料与冻结版本不一致"))
        if run.snapshot["policy"].get("publication_id"):
            p=await self.session.get(InspectionPolicyPublication,run.snapshot["policy"]["publication_id"])
            if not p or p.org_id!=self.org_id or p.status!="published":validation["blockers"].append(blocker("policy_withdrawn","采信与复核策略已撤回"))
            elif fingerprint(p.snapshot)!=fingerprint({k:v for k,v in run.snapshot["policy"].items() if k!="publication_id"}):
                validation["blockers"].append(blocker("policy_changed","已绑定策略内容与冻结版本不一致"))
        observations=copy.deepcopy(run.snapshot["observations"])
        for obs,source in zip(observations,validation["sources"]):
            obs["observation_identity"]=source.get("observation_identity") or obs.get("evidence_id")
        evaluation=evaluate_plan(run.snapshot.get("rules",[]),run.snapshot.get("sample_ids",[]),observations,
            source_issues=[b["message"] for b in validation["blockers"]],policy=run.snapshot["policy"])
        validation["blockers"].extend(blocker("execution_coverage",m) for m in evaluation["missing_inputs"]
            if m not in [b["message"] for b in validation["blockers"]])
        if run.status=="accepted":
            action=await self.session.scalar(select(InspectionExecutionAction).where(InspectionExecutionAction.org_id==self.org_id,
                InspectionExecutionAction.run_id==run.id,InspectionExecutionAction.action=="accept").order_by(InspectionExecutionAction.created_at.desc()).limit(1))
            if not action or not action.verification_snapshot or action.actor_id!=run.reviewed_by or action.actor_id==run.created_by:
                validation["blockers"].append(blocker("review_provenance","历史确认缺少完整的独立复核凭据，请创建新记录重新核验"))
            else:
                confirmed=set(action.verification_snapshot.get("verified_evidence_ids",[]))
                required={o["evidence_id"] for o in run.snapshot["observations"] if o["kind"]=="report_attachment"}
                if confirmed!=required or (required and not action.verification_snapshot.get("report_values_verified")):
                    validation["blockers"].append(blocker("report_review_provenance","历史确认缺少逐项报告核对凭据"))
                for source in validation["sources"]:
                    if source["evidence_id"] in confirmed:source["transcription_verified"]=True
                validation["independent_review"]={"action_id":action.id,"actor_id":action.actor_id,"reviewed_at":str(action.created_at)}
        validation["current_evaluation"]=evaluation
        return validation

    async def validity(self,run):
        validation=await self.verification(run)
        return list(dict.fromkeys(b["message"] for b in validation["blockers"]))

    async def serialize(self,row):
        validation=await self.verification(row)
        current_issues=list(dict.fromkeys(b["message"] for b in validation["blockers"]))
        actions=(await self.session.scalars(select(InspectionExecutionAction).where(InspectionExecutionAction.org_id==self.org_id,
            InspectionExecutionAction.run_id==row.id).order_by(InspectionExecutionAction.created_at))).all()
        return {**{key:getattr(row,key) for key in ["id","task_id","session_id","snapshot","evaluation","status","row_version","created_by","reviewed_by","created_at","reviewed_at"]},
            "current_source_issues":current_issues,"source_validation":validation,
            "review_history":[{k:getattr(a,k) for k in ["id","actor_id","action","reason","evidence_refs","verification_snapshot","created_at"]} for a in actions],
            "effective_status":"needs_reassessment" if current_issues else row.status}

    async def report_file(self,run_id,attachment_id):
        run=await self.get(run_id)
        if not any(o.get("attachment_id")==attachment_id for o in run.snapshot["observations"]):raise NotFoundError("报告不在本次执行范围")
        authorization=run.snapshot.get("review_authorization") or {}
        task=await self.task(run.task_id)
        return await ExecutionEvidenceService(self.session,self.current,self.storage,
            review_owner=authorization.get("owner") if authorization.get("owner") in {run.created_by,task.created_by} else None,
            review_attachment_ids=authorization.get("attachment_ids",[])).file(attachment_id,pdf=True)

    async def review(self,run_id,payload):
        if str(self.current.role)!="expert" or not has_permission("inspection_execution_review",self.current.role):raise ForbiddenError("需要独立领域专家复核")
        row=await self.get(run_id,lock=True)
        if row.created_by==self.current.user_id:raise ForbiddenError("不能复核本人创建的执行结果")
        raw=fingerprint({"run_id":run_id,"actor_id":self.current.user_id,"payload":payload})
        old=(await self.session.execute(select(InspectionExecutionAction).where(InspectionExecutionAction.org_id==self.org_id,
            InspectionExecutionAction.request_key==payload["request_key"]))).scalar_one_or_none()
        if old:
            if old.payload_hash!=raw:raise ConflictError("操作编号已用于不同决定")
            return await self.serialize(row)
        if row.row_version!=payload["expected_version"] or row.status!="draft":raise ConflictError("执行记录已经改变或复核完成")
        validation=await self.verification(row)
        if len(str(payload.get("reason") or "").strip())<4:raise ValidationError("复核须填写有效说明")
        evidence_refs=[str(v).strip() for v in payload.get("evidence_refs",[]) if str(v).strip()]
        if payload["decision"]=="accept":
            issues=[b["message"] for b in validation["blockers"]]
            if issues or row.evaluation["missing_inputs"] or row.evaluation["item_verdict"] not in {"pass","fail"}:
                raise ValidationError("依据、检测覆盖或条件不足，不能确认结论",detail={"issues":issues})
            if any(o["kind"]=="report_attachment" for o in row.snapshot["observations"]) and not payload["report_values_verified"]:
                raise ValidationError("报告转录值需逐项核对原PDF后再确认")
            report_ids={o["evidence_id"] for o in row.snapshot["observations"] if o["kind"]=="report_attachment"}
            if set(payload.get("verified_evidence_ids",[]))!=report_ids:raise ValidationError("请逐项记录已核对的报告引用，勾选总开关不能代替逐项复核")
            if not evidence_refs:raise ValidationError("专业复核须记录依据")
        validation["verified_evidence_ids"]=list(dict.fromkeys(payload.get("verified_evidence_ids",[])))
        validation["report_values_verified"]=bool(payload.get("report_values_verified"))
        if payload["decision"]=="accept":
            for source in validation["sources"]:
                if source["evidence_id"] in validation["verified_evidence_ids"]:source["transcription_verified"]=True
        row.status={"accept":"accepted","reject":"rejected","request_evidence":"awaiting_evidence"}[payload["decision"]]
        row.row_version+=1;row.reviewed_by=self.current.user_id;row.reviewed_at=utcnow()
        self.session.add(InspectionExecutionAction(org_id=self.org_id,run_id=row.id,actor_id=self.current.user_id,
            request_key=payload["request_key"],payload_hash=raw,action=payload["decision"],reason=payload["reason"],
            evidence_refs=evidence_refs,verification_snapshot=validation))
        await self.session.flush();return await self.serialize(row)
