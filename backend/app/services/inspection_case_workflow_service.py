"""Read a case's actual progress; preparation flags never grant authority."""
import json
from sqlalchemy import select
from app.core.permissions import has_permission
from app.core.exceptions import NotFoundError, ForbiddenError, ValidationError
from app.models.inspection_standard_library import StandardDocument
from app.models.standard_admission import StandardDocumentRevision
from app.models.knowledge_admission import KnowledgeAdmission
from app.services.inspection_execution_service import InspectionExecutionService
from app.services.inspection_execution_context_service import InspectionExecutionContextService
from app.services.task_result_bundle_service import TaskResultBundleService
from app.services.export_job_service import ExportJobService
from app.services.knowledge_admission_service import KnowledgeAdmissionService


class InspectionCaseWorkflowService:
    def __init__(self, session, current, storage=None):
        self.session, self.current, self.storage = session, current, storage

    async def read(self, task_id):
        execution_service=InspectionExecutionService(self.session,self.current,self.storage)
        task=await execution_service.task(task_id)
        plan=(task.meta_data or {}).get('case_preparation')
        if not plan:return None
        from app.services.inspection_execution_context_service import valid_uuid
        if not isinstance(plan,dict) or not all(key in plan for key in ['case_id','title','standard_document_id',
            'standard_revision_id','standard_refs','initial_execution_keys','report_attachment_id','planned_items','limitations']):
            raise ValidationError('案例准备资料不完整，请重新核对资料包')
        if any(not valid_uuid(plan[key]) for key in ['standard_document_id','standard_revision_id','report_attachment_id']):
            raise ValidationError('案例对象引用格式无效')
        if any(not isinstance(plan[key],list) for key in ['standard_refs','initial_execution_keys','planned_items','limitations']):
            raise ValidationError('案例项目和来源须按列表登记')
        if any(not isinstance(r,dict) or not valid_uuid(r.get('revision_id')) or not valid_uuid(r.get('candidate_id'))
            or not r.get('measurement_key') for r in plan['standard_refs']):
            raise ValidationError('案例检测要求引用不完整')
        context=await InspectionExecutionContextService(self.session,self.current,self.storage).context(task)
        bundle=await TaskResultBundleService(self.session,self.current,self.storage).summary(task_id)
        document=await self.session.scalar(select(StandardDocument).where(StandardDocument.org_id==self.current.org_id,
            StandardDocument.id==plan['standard_document_id'],StandardDocument.library_id==task.inspection_standard_id,
            StandardDocument.deleted_at.is_(None)))
        revision=await self.session.scalar(select(StandardDocumentRevision).where(StandardDocumentRevision.org_id==self.current.org_id,
            StandardDocumentRevision.id==plan['standard_revision_id'],StandardDocumentRevision.document_id==document.id)) if document else None
        standard_ready=bool(revision and document.published_revision_id==revision.id and
            revision.review_status=='approved' and revision.publication_status=='published')
        initial_refs=[r for r in plan['standard_refs'] if r['measurement_key'] in plan['initial_execution_keys']]
        requirement_issues=['案例引用的标准修订不存在或不在本任务范围']
        if revision and initial_refs and context['task_scope']['production_date'] and all(
            r['revision_id']==revision.id for r in initial_refs) and {r['measurement_key'] for r in initial_refs}==set(plan['initial_execution_keys']):
            _,_,requirement_issues=await execution_service.bindings(initial_refs,context['task_scope']['product_category'],
                context['task_scope']['production_date'])
        report=next((r for r in context['reports'] if r['attachment_id']==plan['report_attachment_id']),None)
        report_ready=bool(report and not report['issues'])
        run=bundle['execution'];reviewed=bool(run and run['effective_status']=='accepted')
        reports=[]
        current_execution_hash=next((r['source_hash'] for r in bundle['source_refs'] if r['kind']=='inspection_execution'),None)
        if has_permission('report_read',self.current.role):
            _,jobs=await ExportJobService(self.session,self.current.org_id,actor_user_id=self.current.user_id,
                actor_role=self.current.role).list_jobs(1,50,task_id=task_id)
            for job in jobs:
                saved=json.loads(job.config_json or '{}').get('report_snapshot') or {}
                matching=any(r['kind']=='inspection_execution' and r['id']==run['id'] and r['source_hash']==current_execution_hash
                    for r in saved.get('source_refs',[])) if run else False
                if matching and job.status=='success' and job.file_url:
                    reports.append(job.id)
        knowledge=[]
        if run:
            # Use existing candidate visibility rules, including private/consent restrictions.
            service=KnowledgeAdmissionService(self.session,self.current)
            ids=(await self.session.scalars(select(KnowledgeAdmission.id).where(KnowledgeAdmission.org_id==self.current.org_id))).all()
            for admission_id in ids:
                try:item=await service.get(admission_id)
                except (NotFoundError,ForbiddenError):continue
                if not any(r['kind']=='inspection_execution' and r['id']==run['id'] for r in item.source_refs):continue
                valid=not await service.source_issues(item)
                knowledge.append({'id':item.id,'status':item.publication_status,'current_sources_valid':valid})
        published=any(k['status']=='published' and k['current_sources_valid'] for k in knowledge)
        def step(key,label,ready,detail):
            return {'key':key,'label':label,'status':'complete' if ready else 'pending','detail':detail}
        first_items='、'.join(p.get('indicator') or p['measurement_key'] for p in plan['planned_items']
            if isinstance(p,dict) and p.get('measurement_key') in plan['initial_execution_keys']) or '已登记的首轮项目'
        stages=[
            step('report','报告与样品关联',report_ready,'原件、哈希、PDF页码和原报告样品已关联。' if report_ready else '需核对报告原件、授权及任务对象。'),
            step('standard','标准原文专业核验',standard_ready,'本案所选修订已专业核验并发布。' if standard_ready else '原件已接收；适用日期、范围和正文仍待专家核验及发布。'),
            step('requirements','首轮检测要求确认',not requirement_issues,
                '首轮要求已确认，仍按本案来源范围执行。' if not requirement_issues else '；'.join(requirement_issues)),
            step('execution','创建选定项目执行',bool(run),'已有执行记录，产品整体仍未评定。' if run else
                f'首轮核对{first_items}；其他列项按证据覆盖情况补充观测。'),
            step('review','独立复核',reviewed,'来源与逐项复核凭据当前有效。' if reviewed else '由另一位专家逐项打开原报告、核对转录值并记录复核引用。'),
            step('risk','限定范围风险研判',any(r['effective_status']=='accepted' for r in bundle['risks']),
                '由授权专家处理；历史线索不代替当前产品检测，未知发生概率保持未校准。'),
            step('export','同版本报告',bool(reports),'报告引用所选执行版本；生成时快照与当前有效性分开。'),
            step('candidate','知识候选',bool(knowledge),'从已复核执行提出有适用条件和限制的候选，不自动进入公共RAG。'),
            step('knowledge','知识审核与准入',published,'需专业审核、范围授权及来源复核；发布后再验证检索与任务复用。')]
        return {'case_id':plan['case_id'],'title':plan['title'],'steps':stages,'limitations':plan['limitations'],
            'planned_items':plan['planned_items'],'initial_execution_keys':plan['initial_execution_keys'],
            'standard_document_id':document.id if document else None,'standard_revision_id':revision.id if revision else None,
            'standard_no':revision.snapshot.get('standard_no') if revision else None,
            'can_prepare_execution':bool(standard_ready and not requirement_issues and report_ready),
            'execution_run_id':run['id'] if run else None,'product_verdict':'not_assessed',
            'professional_work_complete':all(s['status']=='complete' for s in stages),
            'retrieval_reuse_verified':False}
