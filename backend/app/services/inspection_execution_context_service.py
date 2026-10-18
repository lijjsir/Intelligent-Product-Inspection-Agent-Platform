"""Resolve task objects without conflating product similarity with evidence access."""
import copy
from uuid import UUID
from sqlalchemy import select
from app.core.datetime import utcnow
from app.core.exceptions import ConflictError,NotFoundError,ValidationError
from app.core.permissions import has_permission
from app.models.task import InspectionTask
from app.models.product import ProductSku,ProductBatch
from app.models.quality_risk import ProductCategory,QualityProduct,QualityProductionBatch,PhysicalSample,QualityAttachment,QualitySourceRecord
from app.models.supervision import SupervisionRecord,MeasurementRecord
from app.models.inspection_execution import InspectionPolicyPublication
from app.services.execution_evidence_service import ExecutionEvidenceService,parsed_time
from app.services.knowledge_source_service import fingerprint


def valid_uuid(value):
    try:return str(UUID(str(value)))
    except (ValueError,TypeError):return None


def task_image_inputs(task):
    images={}
    for index,item in enumerate(task.image_items or []):
        if item.get("hash") and item.get("url"):
            images.setdefault(item["hash"],{"image_hash":item["hash"],"index":index,"view":item.get("view") or ""})
    return list(images.values())


class InspectionExecutionContextService:
    def __init__(self,session,current,storage=None):
        self.session,self.current,self.storage=session,current,storage;self.org_id=current.org_id

    async def entity(self,model,entity_id):
        entity_id=valid_uuid(entity_id)
        if not entity_id:return None
        return await self.session.scalar(select(model).where(model.id==entity_id,model.org_id==self.org_id,
            model.deleted_at.is_(None)).execution_options(populate_existing=True))

    async def scope(self,task):
        meta=task.meta_data or {};issues=[]
        product=await self.entity(QualityProduct,task.quality_product_id) if task.quality_product_id else None
        category_id=task.product_category_id or (product.category_id if product else None)
        category=await self.entity(ProductCategory,category_id) if category_id else None
        batch_id=meta.get("quality_batch_id")
        batch=await self.entity(QualityProductionBatch,batch_id) if batch_id else None
        if task.quality_product_id and (not product or not product.is_active):issues.append("任务产品档案不存在或已停用")
        if category_id and (not category or not category.is_active):issues.append("任务类别不存在或已停用")
        if product and category and product.category_id!=category.id:issues.append("任务产品与类别关联不一致")
        if batch_id and (not batch or not product or batch.product_id!=product.id):issues.append("任务批次不属于当前产品或已撤回")
        sku=await self.entity(ProductSku,task.product_sku_id) if task.product_sku_id else None
        native_batch=await self.entity(ProductBatch,task.batch_id) if task.batch_id else None
        if task.product_sku_id and (not sku or not sku.is_active):issues.append("任务型号档案不存在或已停用")
        if task.batch_id and (not native_batch or not native_batch.is_active or not sku or native_batch.product_sku_id!=sku.id):issues.append("任务型号与批次不一致或批次已停用")
        date=(batch.production_date.isoformat() if batch and batch.production_date else
            native_batch.production_date.isoformat() if native_batch and native_batch.production_date else meta.get("production_date"))
        return {"task_id":task.id,"product_id":task.quality_product_id or task.product_id,
            "quality_product_id":task.quality_product_id,"product_sku_id":task.product_sku_id,
            "product_name":product.name if product else sku.name if sku else meta.get("quality_product_name") or meta.get("product_sku_name") or task.product_id,
            "category_id":category_id,"product_category":category.name if category else meta.get("product_category_name") or meta.get("product_family") or "",
            "quality_batch_id":batch_id,"batch_id":task.batch_id,"production_date":date,
            "production_batch_ref":batch.original_batch_no if batch else native_batch.batch_no if native_batch else meta.get("production_batch_ref") or meta.get("batch_no"),
            "unit_serial_ref":meta.get("unit_serial_ref"),"input_mode":meta.get("input_mode") or "image",
            "spec_code":task.spec_code,"issues":issues}

    def policy_issues(self,policy,scope):
        snap=policy.snapshot;issues=[];bound=snap.get("scope") or {}
        if snap.get("spec_code")!=scope["spec_code"]:issues.append("策略检测场景与任务不一致")
        if scope["input_mode"] not in snap.get("input_modes",["image","measurement","mixed","report"]):issues.append("策略不适用于本任务输入类型")
        if bound.get("quality_product_id") and bound["quality_product_id"]!=scope["quality_product_id"]:issues.append("策略具体产品不匹配")
        if bound.get("product_id") and bound["product_id"] not in {scope["product_id"],scope.get("product_sku_code")}:
            issues.append("策略产品对象与任务不匹配")
        if bound.get("applicable_skus") and scope["product_sku_id"] not in bound["applicable_skus"]:issues.append("策略型号范围不匹配")
        if bound.get("product_family") and bound["product_family"]!=scope["product_category"]:issues.append("策略产品类别不匹配")
        start=parsed_time(snap.get("effective_from"));end=parsed_time(snap.get("effective_to"));now=utcnow()
        if (start and now<start) or (end and now>end):issues.append("策略当前尚未生效或已超出执行有效期")
        return issues

    async def policies(self,scope,selected_id=None):
        rows=(await self.session.scalars(select(InspectionPolicyPublication).where(InspectionPolicyPublication.org_id==self.org_id,
            InspectionPolicyPublication.status=="published").order_by(InspectionPolicyPublication.created_at.desc(),InspectionPolicyPublication.id.desc()).limit(200))).all()
        if selected_id and not any(p.id==selected_id for p in rows):
            selected=await self.session.scalar(select(InspectionPolicyPublication).where(InspectionPolicyPublication.org_id==self.org_id,InspectionPolicyPublication.id==selected_id,InspectionPolicyPublication.status=='published'))
            if selected:rows=[*rows,selected]
        return [{"id":p.id,"snapshot":p.snapshot,"published_at":p.created_at.isoformat(),"definition_hash":fingerprint(p.snapshot),"issues":self.policy_issues(p,scope)} for p in rows]

    def source_permitted(self,record,task,*,submitted=False):
        validator=ExecutionEvidenceService(self.session,self.current,self.storage)
        return validator.record_authorized(record) or (submitted and record.created_by==task.created_by
            and str(self.current.role)=="expert" and has_permission("inspection_execution_review",self.current.role))

    def record_scope_issues(self,record,scope):
        ref=record.product_ref or {};issues=[]
        for key,target in [("product_id",scope["quality_product_id"]),("category_id",scope["category_id"]),
            ("production_batch_ref",scope["production_batch_ref"]),("unit_serial_ref",scope["unit_serial_ref"])]:
            if target and ref.get(key) and str(ref[key])!=str(target):issues.append("报告登记的产品、类别、批次或单件与任务不一致")
        return list(dict.fromkeys(issues))

    async def source_report(self,task,link,scope,*,submitted=True):
        record=await self.entity(QualitySourceRecord,link["source_record_id"])
        if not record or not self.source_permitted(record,task,submitted=submitted):raise NotFoundError("报告来源不在当前授权范围")
        if record.record_type!="inspection_report" or record.data_nature!="observed":raise ValidationError("请选择真实检测报告来源，标准正文和推断资料不能作为检测报告")
        if record.authorization_scope=="private" and record.created_by!=task.created_by:
            raise ValidationError("私有报告需由资料所属任务使用，或先明确授权到组织业务范围")
        issues=self.record_scope_issues(record,scope)
        if issues:raise ValidationError(issues[0])
        attachment=await self.entity(QualityAttachment,link["attachment_id"])
        if not attachment or attachment.id not in (record.attachment_ids or []) or attachment.mime_type!="application/pdf":
            raise ValidationError("报告附件不在来源记录中，或不是 PDF")
        if link.get("file_hash") and link["file_hash"]!=attachment.sha256:raise ValidationError("任务关联的报告版本已变化，请重新核对关联")
        if link.get("source_hash") and link["source_hash"]!=self.record_hash(record):raise ValidationError("报告来源资料在关联后已变化")
        return record,attachment

    @staticmethod
    def record_hash(record):
        return fingerprint({key:getattr(record,key) for key in ["content","content_hash","attachment_ids","data_nature","product_ref"]})

    async def context(self,task,*,session_id=None,sample_ids=(),policy_id=None):
        scope=await self.scope(task)
        sessions=(await self.session.scalars(select(SupervisionRecord).where(SupervisionRecord.org_id==self.org_id,
            SupervisionRecord.kind=="inspection-sessions",SupervisionRecord.data["task_id"].as_string()==task.id)
            .order_by(SupervisionRecord.created_at.desc(),SupervisionRecord.id.desc()).limit(200))).all()
        if session_id and not any(s.id==session_id for s in sessions):
            extra=await self.session.scalar(select(SupervisionRecord).where(SupervisionRecord.org_id==self.org_id,SupervisionRecord.kind=='inspection-sessions',
                SupervisionRecord.id==session_id,SupervisionRecord.data['task_id'].as_string()==task.id))
            if extra:sessions=[*sessions,extra]
        native_samples=(await self.session.scalars(select(SupervisionRecord).where(SupervisionRecord.org_id==self.org_id,
            SupervisionRecord.kind=="samples",SupervisionRecord.data["task_id"].as_string()==task.id).order_by(SupervisionRecord.created_at.desc(),SupervisionRecord.id.desc()).limit(500))).all()
        missing={valid_uuid(value) for value in sample_ids if valid_uuid(value)}-{s.id for s in native_samples}
        if missing:
            extra=(await self.session.scalars(select(SupervisionRecord).where(SupervisionRecord.org_id==self.org_id,SupervisionRecord.kind=='samples',SupervisionRecord.id.in_(missing),
                SupervisionRecord.data['task_id'].as_string()==task.id).order_by(SupervisionRecord.created_at.desc(),SupervisionRecord.id.desc()))).all()
            native_samples=[*native_samples,*extra]
        samples=[]
        for s in native_samples:
            sample_issues=[] if s.data.get("sampled_at") else ["尚未记录采样时间"]
            if task.product_sku_id and s.data.get("product_sku_id")!=task.product_sku_id:sample_issues.append("样品型号与任务型号不一致")
            if task.batch_id and s.data.get("batch_id")!=task.batch_id:sample_issues.append("样品批次与任务批次不一致")
            if scope['quality_product_id'] and s.data.get('quality_product_id') and s.data['quality_product_id']!=scope['quality_product_id']:sample_issues.append("样品产品与任务产品不一致")
            samples.append({"id":s.id,"label":s.name,"code":s.code,"kind":"platform_sample","sampled_at":s.data.get("sampled_at"),"issues":sample_issues})
        physical_ids=[valid_uuid(i) for i in (task.meta_data or {}).get("physical_sample_ids",[]) if valid_uuid(i)]
        physical=(await self.session.scalars(select(PhysicalSample).where(PhysicalSample.org_id==self.org_id,
            PhysicalSample.id.in_(physical_ids),PhysicalSample.deleted_at.is_(None)))).all() if physical_ids else []
        for s in physical:
            sample_issues=[] if s.sampled_at else ["样品尚未完成采样登记"]
            if scope['quality_product_id'] and s.product_id!=scope['quality_product_id']:sample_issues.append("实物样品产品与任务产品不一致")
            if scope['production_batch_ref'] and s.production_batch_ref!=scope['production_batch_ref']:sample_issues.append("实物样品批次与任务批次不一致")
            samples.append({"id":s.id,"label":s.external_sample_code or s.unit_serial_ref or "抽查实物样品", "code":s.external_sample_code,
                "kind":"physical_sample","sampled_at":str(s.sampled_at) if s.sampled_at else None,"issues":sample_issues})
        ids=[s.id for s in sessions if not session_id or s.id==session_id]
        measurements=(await self.session.scalars(select(MeasurementRecord).where(MeasurementRecord.org_id==self.org_id,
            MeasurementRecord.session_id.in_(ids)).order_by(MeasurementRecord.created_at.desc()).limit(5000))).all() if ids else []
        reports=[]
        for link in ((task.meta_data or {}).get("execution_inputs") or {}).get("report_links",[]):
            try:
                record,attachment=await self.source_report(task,link,scope)
                reports.append({**link,"file_name":attachment.file_name,"record_label":record.external_record_id or "检测报告",
                    "issues":[],"page_count":link.get("page_count")})
                samples.extend({"id":s["id"],"label":s["label"],"kind":"report_sample","report_attachment_id":attachment.id,"issues":[]} for s in link.get("samples",[]))
            except (NotFoundError,ValidationError) as exc:
                reports.append({"attachment_id":link["attachment_id"],"source_record_id":link["source_record_id"],"issues":[exc.message],"samples":[]})
        policies=await self.policies(scope,policy_id)
        token=fingerprint({"task":{k:getattr(task,k) for k in ["id","product_id","product_sku_id","batch_id","quality_product_id","product_category_id","meta_data","image_items","image_urls"]},
            "scope":scope,"sessions":[(s.id,s.version,s.data) for s in sessions],"samples":[(s.id,s.version,s.data) for s in native_samples],
            "physical":[(s.id,s.updated_at) for s in physical],"measurements":[(m.id,m.content_hash,m.validation_status) for m in measurements],
            "policies":[(p["id"],p["definition_hash"]) for p in policies]})
        return {"task_scope":scope,"context_hash":token,"images":task_image_inputs(task),"samples":samples,"reports":reports,"policies":policies,
            "case_preparation":(task.meta_data or {}).get('case_preparation'),
            "sessions":[{"id":s.id,"label":s.name,"code":s.code,"version":s.version,"status":s.status,"sample_ids":s.data.get("sample_ids",[]),
                "product_category":s.data.get("product_category"),"production_date":s.data.get("production_date")} for s in sessions],
            "measurements":[{"id":m.id,"session_id":m.session_id,"sample_id":m.sample_id,"device_id":m.device_id,"event_id":m.event_id,
                "validation_status":m.validation_status,"source_hash":m.content_hash,"data":m.data} for m in measurements],
            "truncated":{"sessions":len(sessions)>=200,"samples":len(native_samples)>=500,"measurements":len(measurements)>=5000}}

    async def report_candidates(self,task,keyword=""):
        scope=await self.scope(task)
        q=select(QualitySourceRecord).where(QualitySourceRecord.org_id==self.org_id,QualitySourceRecord.deleted_at.is_(None),
            QualitySourceRecord.record_type=="inspection_report",QualitySourceRecord.data_nature=="observed")
        if not has_permission("quality_material_read_business",self.current.role):q=q.where(QualitySourceRecord.created_by==self.current.user_id)
        rows=(await self.session.scalars(q.order_by(QualitySourceRecord.created_at.desc()).limit(200))).all();result=[]
        for r in rows:
            if not self.source_permitted(r,task):continue
            for aid in r.attachment_ids or []:
                a=await self.entity(QualityAttachment,aid)
                if not a or a.mime_type!="application/pdf":continue
                label=f"{r.external_record_id or '检测报告'} · {a.file_name}"
                if keyword and keyword.casefold() not in label.casefold():continue
                issues=self.record_scope_issues(r,scope)
                if r.authorization_scope=="private" and r.created_by!=task.created_by:issues.append("私有报告尚未授权给该任务发起者")
                result.append({"source_record_id":r.id,"attachment_id":a.id,"label":label,"file_hash":a.sha256,
                    "issues":issues,"product_ref":r.product_ref})
        return result

    async def link_report(self,task,payload):
        meta=copy.deepcopy(task.meta_data or {});inputs=meta.get("execution_inputs") or {"schema_version":1,"report_links":[],"events":[]}
        raw=fingerprint(payload)
        old=next((e for e in inputs.get("events",[]) if e["request_key"]==payload["request_key"]),None)
        if old:
            if old["payload_hash"]!=raw:raise ConflictError("相同操作编号不能关联不同报告")
            return await self.context(task)
        context=await self.context(task)
        if context["context_hash"]!=payload["expected_context_hash"]:raise ConflictError("任务关联资料已变化，请刷新后重新选择")
        if task.status in {"signed","archived"}:raise ConflictError("已归档任务不能改变资料关联")
        record,a=await self.source_report(task,payload,context["task_scope"],submitted=False)
        validator=ExecutionEvidenceService(self.session,self.current,self.storage)
        _,_,file_context=await validator.file(a.id,pdf=True)
        codes=list(dict.fromkeys(str(code).strip() for code in payload["sample_codes"] if str(code).strip()))
        if not codes or len(str(payload.get("reason") or "").strip())<4:raise ValidationError("请记录报告原样品编号及对象对应的核对说明")
        link={"source_record_id":record.id,"attachment_id":a.id,"source_hash":self.record_hash(record),"file_hash":a.sha256,
            "page_count":file_context["page_count"],"samples":[{"id":"report-sample:"+fingerprint({"attachment":a.id,"code":c})[:32],"label":c} for c in codes],
            "linked_by":self.current.user_id,"linked_at":utcnow().isoformat(),"reason":payload["reason"].strip(),"object_scope":context["task_scope"]}
        inputs["report_links"]=[l for l in inputs.get("report_links",[]) if l["attachment_id"]!=a.id]+[link]
        inputs["events"]=[*inputs.get("events",[]),{"request_key":payload["request_key"],"payload_hash":raw,"actor_id":self.current.user_id,
            "at":utcnow().isoformat(),"action":"link_report","link":link}]
        task.meta_data={**meta,"execution_inputs":inputs};await self.session.flush()
        return await self.context(task)

    async def validate_selection(self,task,payload,context):
        issues=list(context["task_scope"]["issues"]);scope=context["task_scope"]
        if payload.get("context_hash") and payload["context_hash"]!=context["context_hash"]:raise ConflictError("任务资料、样品或策略已变化，请刷新后再执行")
        if scope["product_category"] and scope["product_category"]!=payload["product_category"]:issues.append("执行类别与任务产品类别不一致")
        if scope["production_date"] and scope["production_date"]!=payload["production_date"]:issues.append("执行生产日期与已登记批次日期不一致")
        samples={s["id"]:s for s in context["samples"]}
        if not set(payload["sample_ids"])<=set(samples):raise ValidationError("请选择本任务已关联的平台样品或报告原样品")
        issues.extend(m for sample_id in payload["sample_ids"] for m in samples[sample_id]["issues"])
        for obs in payload["observations"]:
            if obs["kind"]=="report_attachment":
                report=next((r for r in context["reports"] if r["attachment_id"]==obs["id"] and not r["issues"]),None)
                if not report or obs["sample_id"] not in {s["id"] for s in report["samples"]}:raise ValidationError("报告或原样品未关联到本次任务")
            elif not payload.get("session_id"):raise ValidationError("实测记录必须选择所属检测会话")
        session=next((s for s in context["sessions"] if s["id"]==payload.get("session_id")),None)
        if payload.get("session_id") and not session:raise ValidationError("检测会话不属于当前任务")
        if session:
            if session.get("product_category") and session["product_category"]!=payload["product_category"]:issues.append("会话登记的产品类别不一致")
            if session.get("production_date") and session["production_date"]!=payload["production_date"]:issues.append("会话登记的生产日期不一致")
        return issues
