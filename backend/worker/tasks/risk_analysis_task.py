"""DB-backed dispatch and one-shot leases; retries never silently spend model calls."""
import asyncio
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select
from app.core.datetime import utcnow
from app.core.exceptions import ConflictError, ForbiddenError, ValidationError
from app.core.permissions import PermissionRole, require_role
from app.models.risk_analysis_job import RiskAnalysisJob
from app.schemas.user import CurrentUser
from app.schemas.quality_risk import RiskAnalyzeRequest
from app.services.permission_service import PermissionService
from app.services.quality_risk_service import QualityRiskService
from app.services.risk_analysis_job_service import MAX_ANALYSIS_SECONDS
from infra.database.session import get_session
from worker.asyncio_runner import run_celery_async
from worker.celery_app import celery_app


async def resolve_actor(db,job,*,fresh=False):
    if fresh:
        from app.models.organization import Organization
        from app.models.user import User
        from app.models.permission import RolePermission,UserPermission
        def locked(stmt):return stmt.with_for_update().execution_options(populate_existing=True)
        await db.scalar(locked(select(Organization).where(Organization.id==job.org_id)))
        user=await db.scalar(locked(select(User).where(User.id==job.created_by,User.org_id==job.org_id)))
        if not user:raise ForbiddenError('提交人已不属于当前组织')
        await db.scalar(locked(select(RolePermission).where(RolePermission.org_id==job.org_id,RolePermission.role==user.role)))
        await db.scalar(locked(select(UserPermission).where(UserPermission.org_id==job.org_id,UserPermission.user_id==job.created_by)))
    identity=await PermissionService(db,job.org_id).identity(job.created_by)
    role=PermissionRole(identity['role'],identity['effective'])
    require_role('quality',role)
    if str(role) not in {'user','expert'}:raise ForbiddenError('提交人的业务角色已改变')
    current=CurrentUser(user_id=job.created_by,org_id=job.org_id,role=identity['role'])
    current.role=role
    current.effective_permissions=identity['effective']
    return current


@celery_app.task(name='worker.tasks.risk_analysis_task.dispatch_risk_analysis')
def dispatch_risk_analysis():return run_celery_async(_dispatch())


@celery_app.task(name='worker.tasks.risk_analysis_task.process_risk_analysis',acks_late=True,
    time_limit=MAX_ANALYSIS_SECONDS+90,soft_time_limit=MAX_ANALYSIS_SECONDS+30)
def process_risk_analysis(job_id):return run_celery_async(_process(job_id))


async def _dispatch():
    async with get_session() as db:
        expired=list(await db.scalars(select(RiskAnalysisJob).where(RiskAnalysisJob.status=='running',
            RiskAnalysisJob.lease_until<utcnow()).with_for_update(skip_locked=True)))
        for job in expired:
            job.status='failed';job.error_code='worker_interrupted';job.finished_at=utcnow()
            job.message='后台任务中断，未自动重新调用模型；请刷新核对现有草稿后重新发起'
        ids=list(await db.scalars(select(RiskAnalysisJob.id).where(RiskAnalysisJob.status=='queued')
            .order_by(RiskAnalysisJob.created_at).limit(10)))
        await db.commit()
    for job_id in ids:process_risk_analysis.delay(job_id)
    return {'queued':len(ids),'interrupted':len(expired)}


async def _process(job_id):
    token=str(uuid4())
    async with get_session() as db:
        job=await db.scalar(select(RiskAnalysisJob).where(RiskAnalysisJob.id==job_id).with_for_update(skip_locked=True))
        if not job or job.status!='queued':return {'skipped':True}
        job.status='running';job.claim_token=token;job.started_at=utcnow()
        job.lease_until=utcnow()+timedelta(seconds=MAX_ANALYSIS_SECONDS+60)
        job.message='正在分析原始证据，完成后保存待独立复核草稿；可离开页面'
        await db.commit()
    try:
        async with asyncio.timeout(MAX_ANALYSIS_SECONDS):
            async with get_session() as db:
                job=await db.get(RiskAnalysisJob,job_id)
                actor=await resolve_actor(db,job)
                payload=RiskAnalyzeRequest.model_validate({key:job.payload.get(key) for key in ('policy_id','inspection_execution_run_id')})
                row=await QualityRiskService(db,actor).analyze_risk(job.case_id,payload,background_basis=job.basis_hash)
                refreshed=await resolve_actor(db,job,fresh=True)
                from app.services.risk_analysis_job_service import RiskAnalysisJobService
                access=RiskAnalysisJobService(db,refreshed)
                await access.authorize_sources(await access.case(job.case_id))
                job=await db.scalar(select(RiskAnalysisJob).where(RiskAnalysisJob.id==job_id)
                    .with_for_update().execution_options(populate_existing=True))
                if job.status!='running' or job.claim_token!=token:raise ConflictError('任务执行凭据已失效')
                models=row.get('model_versions') or {}
                blockers=(row.get('source_validation') or {}).get('blockers') or []
                incomplete=not models.get('model_success') or models.get('inference_status')=='manual_review_required'
                warnings=incomplete or bool(blockers) or row['status']=='awaiting_evidence'
                job.status='completed_with_warnings' if warnings else 'succeeded'
                job.assessment_id=row['id'];job.finished_at=utcnow()
                job.error_code=models.get('inference_error') if warnings else None
                job.message='草稿已保存；模型分析或语义核对未完成，需人工核对原始证据' if warnings else '研判草稿已保存，仍须独立专业复核'
                if job.error_code=='provider_rate_limited':job.message='模型服务限流；已保存待人工核对的草稿，可稍后重新分析'
                elif job.error_code=='model_timeout':job.message='模型响应超时；已保存待人工核对的草稿，请核对服务状态后重新分析'
                if blockers:
                    job.error_code='source_validation_failed';job.message='草稿已保存，但来源核验存在阻断项；请查看本版依据并补齐资料'
                elif row['status']=='awaiting_evidence' and not incomplete:
                    job.error_code='evidence_required';job.message='草稿已保存，证据仍有缺口；请查看本版要求并补充资料'
                await db.commit()
                return {'status':job.status,'assessment_id':job.assessment_id}
    except Exception as exc:
        code='analysis_timeout' if isinstance(exc,TimeoutError) else 'source_changed' if isinstance(exc,ConflictError) else 'permission_changed' if isinstance(exc,ForbiddenError) else 'invalid_input' if isinstance(exc,ValidationError) else 'analysis_failed'
        message={'analysis_timeout':'分析超过15分钟，已终止；请核对现有版本后重新发起',
            'source_changed':'证据、授权或研判版本已变化，本次分析未保存，请核对后重试',
            'permission_changed':'提交人的权限或来源授权已变化，分析未保存',
            'invalid_input':'分析条件或引用依据无效，请核对后重新发起',
            'analysis_failed':'分析未完成，原有研判保留；请检查服务状态后重新发起'}[code]
        async with get_session() as db:
            job=await db.scalar(select(RiskAnalysisJob).where(RiskAnalysisJob.id==job_id).with_for_update())
            if job.status=='running' and job.claim_token==token:
                job.status='stale' if code=='source_changed' else 'failed'
                job.error_code=code;job.message=message;job.finished_at=utcnow();await db.commit()
        return {'status':'failed','error_code':code}
