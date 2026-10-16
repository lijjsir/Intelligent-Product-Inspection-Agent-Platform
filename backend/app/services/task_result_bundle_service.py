"""One task-scoped, versioned read model for results, risk, reports and knowledge."""
import copy,json
from sqlalchemy import select,func
from app.core.datetime import utcnow
from app.core.exceptions import ForbiddenError,NotFoundError,ConflictError,ValidationError
from app.core.permissions import has_permission
from app.models.inspection_execution import InspectionExecutionRun
from app.models.task import InspectionTask
from app.models.result import InspectionResult
from app.models.quality_risk import QualityRiskAssessment,QualityRiskCase
from app.repositories.task_repo import TaskRepository
from app.repositories.result_repo import ResultRepository
from app.services.inspection_execution_service import InspectionExecutionService
from app.services.knowledge_source_service import fingerprint
from app.services.result_service import result_effective_verdict,result_score_status
from app.services.result_trace_utils import extract_citation_items

BUNDLE_VERSION='task-result-v1'
BOUNDARY='本记录仅覆盖列出的样品、项目和证据；试验条件及图片辅助结果不能代替产品性能，产品整体未评定。'
VERDICTS={'pass':'选定项目符合要求','fail':'存在不符合项目','incomplete':'检测或依据尚不完整',
    'uncertain':'结果不确定','manual_required':'需人工核对','missing':'缺少观测'}


def execution_digest(run, review_history=None):
    source={k:getattr(run,k) for k in ['snapshot','evaluation','row_version','status','reviewed_by','reviewed_at']}
    if review_history is not None:
        source['review_history']=review_history
    return fingerprint(source)


def legacy_digest(result):
    return fingerprint({k:getattr(result,k,None) for k in ['id','verdict','overall_score','defects','citations','reasoning_chain',
        'reviewed_by','reviewed_at','review_note','signed_by','signed_at','prompt_version','llm_model']})


def json_value(value):
    return json.loads(json.dumps(value,ensure_ascii=False,default=str))


class TaskResultBundleService:
    def __init__(self,session,current,storage=None):
        self.session,self.current,self.storage=session,current,storage;self.org_id=current.org_id

    async def task(self,task_id):
        if not has_permission('task',self.current.role) or not has_permission('result',self.current.role):raise ForbiddenError('没有任务结果读取权限')
        from app.services.inspection_execution_context_service import valid_uuid
        if not valid_uuid(task_id):raise NotFoundError('任务编号无效')
        task=await TaskRepository(self.session).get_for_user(self.org_id,task_id,
            owner_user_id=self.current.user_id if str(self.current.role)=='user' else None)
        if not task:raise NotFoundError('任务不存在或不在当前授权范围')
        await self.session.refresh(task)
        return task

    async def summary(self,task_id,*,execution_run_id=None,legacy_only=False):
        task=await self.task(task_id)
        execution_allowed=str(self.current.role) in {'user','expert'} and has_permission('inspection_execution',self.current.role)
        if execution_run_id and not execution_allowed:raise ForbiddenError('没有标准执行结果读取权限')
        run_ids=(await self.session.scalars(select(InspectionExecutionRun.id).where(InspectionExecutionRun.org_id==self.org_id,
            InspectionExecutionRun.task_id==task.id).order_by(InspectionExecutionRun.created_at.desc(),InspectionExecutionRun.id.desc())
            )).all() if execution_allowed else []
        runs_by_id={r.id:r for r in (await self.session.scalars(select(InspectionExecutionRun).where(
            InspectionExecutionRun.org_id==self.org_id,InspectionExecutionRun.task_id==task.id,InspectionExecutionRun.id.in_(run_ids))
            .execution_options(populate_existing=True))).all()} if run_ids else {}
        runs=[runs_by_id[run_id] for run_id in run_ids if run_id in runs_by_id]
        chosen=None if legacy_only else next((r for r in runs if r.id==execution_run_id),None) if execution_run_id else runs[0] if runs else None
        if execution_run_id and not chosen:raise NotFoundError('执行版本不属于本任务')
        legacy=await self.session.scalar(select(InspectionResult).where(InspectionResult.org_id==self.org_id,
            InspectionResult.task_id==task.id,InspectionResult.deleted_at.is_(None)).execution_options(populate_existing=True))
        refs=[];execution=None;auxiliary=None;risks=[]
        if chosen:
            service=InspectionExecutionService(self.session,self.current,self.storage)
            execution=await service.serialize(chosen)
            refs.append({'kind':'inspection_execution','id':chosen.id,'version':chosen.row_version,
                'source_hash':execution_digest(chosen,execution['review_history'])})
        if legacy:
            reason=legacy.reasoning_chain or {};signed=bool(reason.get('supervision_signed'))
            auxiliary={'id':legacy.id,'task_id':legacy.task_id,'kind':'legacy_signed_items' if signed else 'visual_auxiliary',
                'scope':reason.get('assessment_scope') or 'legacy_auxiliary_record','verdict':result_effective_verdict(legacy),
                'stored_verdict':legacy.verdict,'score_status':result_score_status(legacy),'defects':legacy.defects or [],
                'citations':extract_citation_items(legacy.citations),'summary':reason.get('summary') or (reason.get('standard_evaluation') or {}).get('summary') or '',
                'reviewed_by':legacy.reviewed_by,'reviewed_at':str(legacy.reviewed_at) if legacy.reviewed_at else None,'review_note':legacy.review_note,
                'llm_model':legacy.llm_model,'product_verdict':'not_assessed',
                'notice':'按原记录范围保留；旧签发或图片复核不会自动成为本次产品整体判定。'}
            refs.append({'kind':'task_result','id':legacy.id,'source_hash':legacy_digest(legacy)})
        if chosen and has_permission('quality',self.current.role):
            q=select(QualityRiskAssessment.id,QualityRiskCase.id).join(QualityRiskCase,QualityRiskCase.id==QualityRiskAssessment.risk_case_id).where(
                QualityRiskAssessment.org_id==self.org_id,QualityRiskCase.org_id==self.org_id,QualityRiskAssessment.deleted_at.is_(None),QualityRiskCase.deleted_at.is_(None))
            if str(self.current.role)=='user':q=q.where((QualityRiskCase.created_by==self.current.user_id)|(QualityRiskCase.assigned_to==self.current.user_id))
            pairs=(await self.session.execute(q.order_by(QualityRiskAssessment.created_at.desc(),QualityRiskAssessment.version.desc()).limit(200))).all()
            assessment_ids=[assessment_id for assessment_id,_ in pairs]
            case_ids=[case_id for _,case_id in pairs]
            assessments={r.id:r for r in (await self.session.scalars(select(QualityRiskAssessment).where(
                QualityRiskAssessment.org_id==self.org_id,QualityRiskAssessment.id.in_(assessment_ids),QualityRiskAssessment.deleted_at.is_(None))
                .execution_options(populate_existing=True))).all()} if pairs else {}
            cases={r.id:r for r in (await self.session.scalars(select(QualityRiskCase).where(
                QualityRiskCase.org_id==self.org_id,QualityRiskCase.id.in_(case_ids),QualityRiskCase.deleted_at.is_(None))
                .execution_options(populate_existing=True))).all()} if pairs else {}
            rows=[(assessments[assessment_id],cases[case_id]) for assessment_id,case_id in pairs
                if assessment_id in assessments and case_id in cases]
            seen=set()
            for assessment,case in rows:
                if case.id in seen:continue
                seen.add(case.id)
                if not any(m.get('kind')=='inspection_execution' and m.get('run_id')==chosen.id for m in assessment.standard_matches or []):continue
                from app.services.risk_evidence_validation_service import validate_risk
                validation=await validate_risk(self.session,self.current,case,assessment,self.storage)
                risks.append({'id':assessment.id,'case_id':case.id,'version':assessment.version,'risk_level':assessment.risk_level,
                    'status':assessment.status,'effective_status':'needs_reassessment' if validation['blockers'] else assessment.status,
                    'risk_type':assessment.risk_type,'possible_causes':assessment.possible_causes,'recommendations':assessment.recommendations,
                    'probability':assessment.probability,'scope':assessment.scope,'reviewed_by':assessment.reviewed_by,'reviewed_at':str(assessment.reviewed_at) if assessment.reviewed_at else None,
                    'source_validation':validation,'policy_version':assessment.policy_version})
                refs.append({'kind':'risk_assessment','id':assessment.id,'version':assessment.version,
                    'source_hash':fingerprint({k:getattr(assessment,k) for k in ['scope','evidence_ids','standard_matches','model_versions','risk_level','risk_type','possible_causes','recommendations','probability','policy_version','status','reviewed_by','reviewed_at','review_comment']})})
        if execution:
            evaluation=execution['evaluation'];conditions=bool(evaluation['checks']) and all(c.get('candidate_type')=='method_condition' for c in evaluation['checks'])
            valid=not execution['current_source_issues']
            stage='reviewed_selected_items' if execution['status']=='accepted' and valid else 'needs_reassessment' if not valid else 'execution_draft'
            label=VERDICTS.get(evaluation['item_verdict'],'需人工核对')
            if conditions and evaluation['item_verdict'] in {'pass','fail'}:label='试验条件符合要求' if evaluation['item_verdict']=='pass' else '试验条件不符合要求'
            if not valid:label='当前依据需重新核验（历史项目判定保留）'
        else:
            stage='auxiliary_record' if auxiliary else 'no_result';label='历史选定项目记录' if auxiliary and auxiliary['kind']=='legacy_signed_items' else '图片 / 旧记录辅助分析' if auxiliary else '尚无结果'
        task_info={'id':task.id,'product_id':task.product_id,'spec_code':task.spec_code,'product_name':(task.meta_data or {}).get('quality_product_name') or
            (task.meta_data or {}).get('product_sku_name') or task.product_id}
        gate={'execution_issues':execution['current_source_issues'] if execution else [],
            'risks':[(r['id'],r['effective_status'],sorted({b['code'] for b in r['source_validation']['blockers']})) for r in risks]}
        result_token=fingerprint({'refs':refs,'gate':gate,'stage':stage,'task':task_info,'legacy_only':legacy_only})
        return json_value({'bundle_version':BUNDLE_VERSION,'task':task_info,'selection':{'execution_run_id':chosen.id if chosen else None,'legacy_only':legacy_only},
            'execution_versions':[{'id':r.id,'row_version':r.row_version,'status':r.status,'created_at':r.created_at,'item_verdict':r.evaluation.get('item_verdict')} for r in runs],
            'execution':execution,'auxiliary':auxiliary,'risks':risks,'scope':{'stage':stage,'label':label,'product_verdict':'not_assessed','boundary':BOUNDARY},
            'source_refs':refs,'result_token':result_token,'can_export':bool(execution or auxiliary)})

    async def report_tasks(self,limit=100):
        legacy=select(InspectionResult.id).where(InspectionResult.task_id==InspectionTask.id,InspectionResult.org_id==self.org_id,
            InspectionResult.deleted_at.is_(None)).exists()
        executions=select(InspectionExecutionRun.id).where(InspectionExecutionRun.task_id==InspectionTask.id,InspectionExecutionRun.org_id==self.org_id).exists()
        allowed=str(self.current.role) in {'user','expert'} and has_permission('inspection_execution',self.current.role)
        # MySQL filesort must not carry large image/metadata JSON documents.
        q=select(InspectionTask.id,legacy.label('legacy_exists'),executions.label('execution_exists')).where(InspectionTask.org_id==self.org_id,
            InspectionTask.deleted_at.is_(None),legacy|executions if allowed else legacy)
        if str(self.current.role)=='user':q=q.where(InspectionTask.created_by==self.current.user_id)
        rows=(await self.session.execute(q.order_by(InspectionTask.created_at.desc()).limit(limit))).all()
        ids=[task_id for task_id,_,_ in rows]
        tasks={t.id:t for t in (await self.session.scalars(select(InspectionTask).where(
            InspectionTask.org_id==self.org_id,InspectionTask.id.in_(ids),InspectionTask.deleted_at.is_(None)))).all()} if ids else {}
        return [{'id':t.id,'org_id':t.org_id,'created_by':t.created_by,'status':t.status,'priority':t.priority,'product_id':t.product_id,
            'product_name':(t.meta_data or {}).get('quality_product_name') or (t.meta_data or {}).get('product_sku_name') or t.product_id,
            'spec_code':t.spec_code,'has_result':bool(old),'has_execution_result':bool(new and allowed)}
            for task_id,old,new in rows if (t:=tasks.get(task_id)) is not None]

    async def list_results(self,page=1,size=20,product_id=None,task_id=None,verdict=None,model_key=None):
        old=select(InspectionResult.id).where(InspectionResult.org_id==self.org_id,InspectionResult.task_id==InspectionTask.id,InspectionResult.deleted_at.is_(None)).exists()
        new=select(InspectionExecutionRun.id).where(InspectionExecutionRun.org_id==self.org_id,InspectionExecutionRun.task_id==InspectionTask.id).exists()
        allowed=str(self.current.role) in {'user','expert'} and has_permission('inspection_execution',self.current.role)
        q=select(InspectionTask.id).where(InspectionTask.org_id==self.org_id,InspectionTask.deleted_at.is_(None),old|new if allowed else old)
        if str(self.current.role)=='user':q=q.where(InspectionTask.created_by==self.current.user_id)
        if product_id:q=q.where(InspectionTask.product_id.contains(product_id,autoescape=True))
        if task_id:
            from app.services.inspection_execution_context_service import valid_uuid
            if not valid_uuid(task_id):raise ValidationError('任务筛选需提供完整有效的编号')
            q=q.where(InspectionTask.id==task_id)
        if model_key:q=q.where(select(InspectionResult.id).where(InspectionResult.task_id==InspectionTask.id,InspectionResult.org_id==self.org_id,
            InspectionResult.llm_model.contains(model_key,autoescape=True)).exists())
        if verdict:
            # Filters refer to the latest selected execution, not any older pass.
            latest=select(InspectionExecutionRun.evaluation['item_verdict'].as_string()).where(InspectionExecutionRun.org_id==self.org_id,
                InspectionExecutionRun.task_id==InspectionTask.id).order_by(InspectionExecutionRun.created_at.desc(),InspectionExecutionRun.id.desc()).limit(1).scalar_subquery()
            legacy_verdict=select(InspectionResult.verdict).where(InspectionResult.org_id==self.org_id,InspectionResult.task_id==InspectionTask.id,
                InspectionResult.deleted_at.is_(None)).limit(1).scalar_subquery()
            q=q.where(func.coalesce(latest,legacy_verdict)==verdict if allowed else legacy_verdict==verdict)
        total=await self.session.scalar(select(func.count()).select_from(q.subquery()))
        ids=(await self.session.scalars(q.order_by(InspectionTask.created_at.desc()).offset((page-1)*size).limit(size))).all()
        tasks_by_id={t.id:t for t in (await self.session.scalars(select(InspectionTask).where(
            InspectionTask.org_id==self.org_id,InspectionTask.id.in_(ids),InspectionTask.deleted_at.is_(None)))).all()} if ids else {}
        tasks=[tasks_by_id[task_id] for task_id in ids if task_id in tasks_by_id]
        items=[]
        for task in tasks:
            bundle=await self.summary(task.id);execution=bundle['execution']
            items.append({'task_id':task.id,'product_id':task.product_id,'product_name':bundle['task']['product_name'],'scope':bundle['scope'],
                'execution_run_id':execution['id'] if execution else None,'legacy_result_id':bundle['auxiliary']['id'] if bundle['auxiliary'] else None,
                'created_at':str(task.created_at),'verdict':execution['evaluation']['item_verdict'] if execution else bundle['auxiliary']['verdict']})
        return {'items':items,'total':int(total or 0),'page':page,'size':size}

    async def freeze(self,task_id,*,execution_run_id=None,legacy_only=False,expected_result_token=None):
        bundle=await self.summary(task_id,execution_run_id=execution_run_id,legacy_only=legacy_only)
        if not bundle['can_export']:raise ValidationError('任务尚无可导出的执行或辅助记录')
        if expected_result_token and bundle['result_token']!=expected_result_token:raise ConflictError('结果版本或来源状态已变化，请刷新后生成报告')
        bundle['frozen_at_utc']=utcnow().isoformat()+'Z'
        return bundle

    async def recheck(self,bundle):
        selection=bundle['selection']
        current=await self.summary(bundle['task']['id'],execution_run_id=selection.get('execution_run_id'),legacy_only=selection.get('legacy_only',False))
        if current['result_token']!=bundle['result_token']:raise ConflictError('报告依据版本、权限或有效性已经变化，请重新生成报告')
        return current
