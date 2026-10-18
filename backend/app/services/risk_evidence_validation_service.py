"""Recheck the frozen evidence of a risk draft before professional acceptance."""
from sqlalchemy import select
from app.core.datetime import utcnow
from app.core.exceptions import NotFoundError,ForbiddenError,ValidationError,ConflictError
from app.core.permissions import has_permission
from app.models.quality_risk import QualityEvidenceItem,QualitySourceRecord,RiskPolicy
from app.models.standard_admission import StandardDocumentRevision
from app.models.inspection_standard_library import StandardDocument,InspectionStandardLibrary
from app.services.execution_evidence_service import ExecutionEvidenceService,blocker,VALIDATOR_VERSION
from app.services.knowledge_source_service import fingerprint


def record_definition(row):
    return fingerprint({key:getattr(row,key) for key in ["id","content_hash","content","data_nature","attachment_ids",
        "product_ref","enterprise_ref","provenance","occurred_at"]})


def evidence_definition(row):
    return fingerprint({key:getattr(row,key) for key in ["id","content_hash","source_record_id","attachment_id",
        "nature","text","structured_data","locator"]})


async def validate_risk(session,current,case,assessment,storage=None,*,freeze_sources=False,lock_returns=False):
    blockers=[];sources=[]
    basis=(assessment.model_versions or {}).get("evidence_basis") or {}
    if not basis:blockers.append(blocker("risk_evidence_provenance","历史草稿未冻结来源版本，请重新生成草稿后复核"))
    if fingerprint(case.scope)!=fingerprint(assessment.scope):blockers.append(blocker("risk_scope_changed","本案对象范围与研判快照不一致，请重新生成草稿"))
    if basis and (
        set(case.evidence_ids or []) != set(basis.get("evidence_ids", assessment.evidence_ids or []))
        or set(case.source_record_ids or []) != set(basis.get("records", {}))
    ):
        blockers.append(blocker("risk_evidence_set_changed", "本案关联证据已更新，请生成新版草稿后重新复核"))
    ids=basis.get("evidence_ids",assessment.evidence_ids or [])
    evidence=(await session.scalars(select(QualityEvidenceItem).where(QualityEvidenceItem.org_id==current.org_id,
        QualityEvidenceItem.id.in_(ids),QualityEvidenceItem.deleted_at.is_(None)).execution_options(populate_existing=True))).all()
    records=(await session.scalars(select(QualitySourceRecord).where(QualitySourceRecord.org_id==current.org_id,
        QualitySourceRecord.id.in_({e.source_record_id for e in evidence}),QualitySourceRecord.deleted_at.is_(None))
        .execution_options(populate_existing=True))).all()
    by_id={r.id:r for r in records};observed_sources=set()
    validator=ExecutionEvidenceService(session,current,storage)
    for missing in set(ids)-{e.id for e in evidence}:blockers.append(blocker("risk_evidence_missing","引用证据已撤回、丢失或不在组织范围",{"evidence_id":missing}))
    for e in evidence:
        record=by_id.get(e.source_record_id)
        if not record:
            blockers.append(blocker("risk_source_missing","证据缺少现存真实来源",{"evidence_id":e.id}));continue
        # Submitting one's own source to a case permits review of that source
        # within this case, without changing its private/global knowledge scope.
        case_submission=(record.id in (case.source_record_ids or []) and record.created_by==case.created_by
            and str(current.role)=="expert" and has_permission("quality_material_read_business",current.role))
        if not validator.record_authorized(record) and not case_submission:
            blockers.append(blocker("risk_source_authorization","来源没有授权给本案复核范围",{"evidence_id":e.id}));continue
        if basis.get("records",{}).get(record.id)!=record_definition(record) or basis.get("evidence",{}).get(e.id)!=evidence_definition(e):
            blockers.append(blocker("risk_source_changed","风险草稿生成后来源或证据发生变化，请重新生成草稿",{"evidence_id":e.id}));continue
        if e.nature=="observed" and record.data_nature=="observed" and (e.text or e.structured_data or e.attachment_id):
            observed_sources.add(record.id)
        if e.attachment_id:
            if e.attachment_id not in (record.attachment_ids or []):
                blockers.append(blocker("risk_attachment_binding","附件不在证据原始来源中",{"evidence_id":e.id}));continue
            try:
                scoped=ExecutionEvidenceService(session,current,storage,review_owner=record.created_by if case_submission else None,
                    review_attachment_ids=[e.attachment_id] if case_submission else [],review_permission="quality_material_read_business")
                _,_,file_context=await scoped.file(e.attachment_id)
                expected=basis.get("attachment_hashes",{}).get(e.attachment_id)
                if not freeze_sources and expected!=file_context["sha256"]:
                    blockers.append(blocker("risk_attachment_changed","报告或附件原件版本与风险草稿不一致，请重新生成草稿",{"evidence_id":e.id}))
                sources.append({"evidence_id":e.id,**file_context})
            except (NotFoundError,ValidationError) as exc:
                blockers.append(blocker("risk_attachment_missing",exc.message,{"evidence_id":e.id}))
        sources.append({"evidence_id":e.id,"source_record_id":record.id,"record_version":record_definition(record),"nature":e.nature})
    if not observed_sources:blockers.append(blocker("risk_observed_missing","缺少真实来源证据，推断资料或专家填级不能替代原始证据"))
    policy_basis=(assessment.model_versions or {}).get("risk_policy_basis")
    if assessment.policy_version:
        if not policy_basis:
            blockers.append(blocker("risk_policy_provenance","历史研判未记录政策对象和内容版本，请重新生成草稿"))
        else:
            policy=await session.scalar(select(RiskPolicy).where(RiskPolicy.id==policy_basis["id"],RiskPolicy.org_id==current.org_id,
                RiskPolicy.deleted_at.is_(None)).execution_options(populate_existing=True))
            if not policy or policy.status!="published" or fingerprint(policy.rules)!=policy_basis["rules_hash"]:
                blockers.append(blocker("risk_policy_changed","引用风险政策已撤回、被替代或修改"))
            else:
                minimum=float((policy.rules.get("evidence_sufficiency") or {}).get("minimum") or 0)
                total_sources={e.source_record_id for e in evidence}
                if len(observed_sources)/max(len(total_sources),1)<minimum:
                    blockers.append(blocker("risk_policy_sufficiency","独立真实来源证据充分度未达到已发布政策要求"))
    for match in assessment.standard_matches or []:
        if match.get("kind")=="inspection_execution":
            try:
                from app.services.inspection_execution_service import InspectionExecutionService
                service=InspectionExecutionService(session,current,storage)
                run=await service.get(match["run_id"])
                validation=await service.verification(run)
                blockers.extend(validation["blockers"])
                if run.status!="accepted" or run.row_version!=match.get("row_version"):
                    blockers.append(blocker("risk_execution_review","引用执行结果尚未独立确认或版本已变化"))
                execution_scope=(run.snapshot.get("task_context") or {}).get("scope") or {}
                if case.scope_type=="category":
                    category=case.scope.get("product_category") or case.scope.get("category_name") or case.scope.get("name")
                    mismatch=(case.scope.get("category_id")!=execution_scope.get("category_id")) if case.scope.get("category_id") else category and category!=run.snapshot.get("product_category")
                    if mismatch:
                        blockers.append(blocker("risk_execution_scope","引用执行的产品类别与本案研判对象不一致"))
                elif case.scope_type in {"product","production_batch","individual_unit"}:
                    task=await service.task(run.task_id)
                    target=case.scope.get("product_id")
                    if not target or str(execution_scope.get("quality_product_id") or task.quality_product_id or task.product_id)!=str(target):
                        blockers.append(blocker("risk_execution_scope","无法证明引用执行与本案属于同一产品对象"))
                    for key in ["production_batch_ref","unit_serial_ref"]:
                        if case.scope.get(key) and execution_scope.get(key,(task.meta_data or {}).get(key))!=case.scope[key]:
                            blockers.append(blocker("risk_execution_scope","引用执行缺少与本案一致的批次或单件关联"))
            except (NotFoundError,ForbiddenError,ValidationError) as exc:
                blockers.append(blocker("risk_execution_unavailable",exc.message))
        elif match.get("revision_id"):
            row=(await session.execute(select(StandardDocumentRevision).join(StandardDocument,StandardDocument.published_revision_id==StandardDocumentRevision.id)
                .join(InspectionStandardLibrary,InspectionStandardLibrary.id==StandardDocument.library_id).where(
                    StandardDocumentRevision.id==match["revision_id"],StandardDocumentRevision.org_id==current.org_id,
                    StandardDocument.org_id==current.org_id,InspectionStandardLibrary.org_id==current.org_id,
                    StandardDocument.deleted_at.is_(None),InspectionStandardLibrary.deleted_at.is_(None),InspectionStandardLibrary.is_active.is_(True)))).scalar_one_or_none()
            if not row or row.review_status!="approved" or row.publication_status!="published" or row.file_hash!=match.get("file_hash"):
                blockers.append(blocker("risk_standard_changed","引用标准已撤回、停用或版本不一致"))
    from app.services.risk_execution_evidence_service import execution_returns, RiskExecutionEvidenceService
    entries = await execution_returns(session, current.org_id, case.id, lock=freeze_sources or lock_returns)
    refs = [{'return_id':entry['id'], **entry['ref']} for entry in entries]
    frozen_refs = (assessment.model_versions or {}).get('returned_execution_refs', [])
    if fingerprint(refs) != fingerprint(frozen_refs):
        blockers.append(blocker('risk_execution_returns_changed', '检测结果回流或撤回后须生成新版研判并独立复核'))
    service = RiskExecutionEvidenceService(session, current, storage)
    matches = {m.get('run_id'):m for m in assessment.standard_matches or [] if m.get('kind') == 'inspection_execution'}
    for entry in entries:
        try:
            await service.resolve(case, entry['ref'])
            if matches.get(entry['ref']['run_id'], {}).get('row_version') != entry['ref']['row_version']:
                blockers.append(blocker('risk_execution_return_missing', '本版未完整引用原事项回流的检测结果'))
        except (NotFoundError, ForbiddenError, ValidationError, ConflictError) as exc:
            blockers.append(blocker('risk_execution_return_invalid', exc.message))
    uncertainties=list(dict.fromkeys(m for m in (assessment.missing_inputs or []) if m!="真实来源证据" and m!="经规则或专家确认的风险等级"))
    if assessment.probability is None:uncertainties.append("发生概率尚未校准，当前确认只适用于本案风险信号及建议")
    return {"validator_version":VALIDATOR_VERSION,"checked_at":utcnow().isoformat(),"blockers":blockers,
        "uncertainties":uncertainties,"sources":sources,"independent_observed_sources":len(observed_sources),
        "boundary":"风险确认不等于产品整体合格或不合格，未知概率和待补实验须继续保留。"}
