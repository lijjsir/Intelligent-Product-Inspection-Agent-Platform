"""Durable, organization-scoped analysis with frozen inputs and explicit retries."""
from sqlalchemy import select
from app.core.config import settings
from app.core.datetime import utcnow
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.permissions import require_role, has_permission
from app.models.risk_analysis_job import RiskAnalysisJob
from app.models.quality_risk import QualityRiskAssessment, QualitySourceRecord, QualityEvidenceItem, RiskPolicy
from app.models.inspection_execution import InspectionExecutionRun
from app.models.supervision import SupervisionRecord
from app.services.knowledge_source_service import fingerprint
from app.services.risk_evidence_validation_service import record_definition, evidence_definition

ACTIVE = {'queued','running'}
MAX_ANALYSIS_SECONDS = 900


def model_error_code(exc):
    import httpx
    if isinstance(exc,httpx.HTTPStatusError):
        return 'provider_rate_limited' if exc.response.status_code==429 else 'provider_unavailable'
    if isinstance(exc,(TimeoutError,httpx.TimeoutException)):return 'model_timeout'
    return 'model_response_invalid'


async def analysis_basis(db, case, payload, *, lock=False):
    """Detect changed evidence, authorization, references and concurrent reviews."""
    def current(stmt):return (stmt.with_for_update() if lock else stmt).execution_options(populate_existing=True)
    records=list(await db.scalars(current(select(QualitySourceRecord).where(QualitySourceRecord.org_id==case.org_id,
        QualitySourceRecord.id.in_(case.source_record_ids or []),QualitySourceRecord.deleted_at.is_(None)))))
    evidence=list(await db.scalars(current(select(QualityEvidenceItem).where(QualityEvidenceItem.org_id==case.org_id,
        QualityEvidenceItem.id.in_(case.evidence_ids or []),QualityEvidenceItem.deleted_at.is_(None)))))
    latest=await db.scalar(current(select(QualityRiskAssessment).where(QualityRiskAssessment.org_id==case.org_id,
        QualityRiskAssessment.risk_case_id==case.id,QualityRiskAssessment.deleted_at.is_(None))
        .order_by(QualityRiskAssessment.version.desc()).limit(1)))
    policy=await db.scalar(current(select(RiskPolicy).where(RiskPolicy.org_id==case.org_id,RiskPolicy.id==payload.policy_id,
        RiskPolicy.deleted_at.is_(None)))) if payload.policy_id else None
    run=await db.scalar(current(select(InspectionExecutionRun).where(InspectionExecutionRun.org_id==case.org_id,
        InspectionExecutionRun.id==payload.inspection_execution_run_id))) if payload.inspection_execution_run_id else None
    links=list(await db.scalars(current(select(SupervisionRecord).where(SupervisionRecord.org_id==case.org_id,
        SupervisionRecord.kind=='risk-lab-verifications',SupervisionRecord.data['case_id'].as_string()==case.id)
        )))
    return fingerprint({'case':{'scope':case.scope,'status':case.status,'records':case.source_record_ids,'evidence':case.evidence_ids},
        'records':{r.id:[record_definition(r),r.authorization_scope] for r in records},
        'evidence':{e.id:evidence_definition(e) for e in evidence},
        'latest':[latest.id,latest.status,latest.reviewed_at,latest.review_comment] if latest else None,
        'policy':[policy.id,policy.status,policy.version,policy.rules] if policy else None,
        'execution':[run.id,run.row_version,run.status,run.snapshot,run.evaluation] if run else None,
        'lab':{r.id:[r.version,r.status,r.data] for r in links},
        'options':payload.model_dump(mode='json')})


class RiskAnalysisJobService:
    def __init__(self,db,current):
        from app.services.quality_risk_service import QualityRiskService
        self.db,self.current,self.risk=db,current,QualityRiskService(db,current)

    async def case(self,case_id,lock=False):
        require_role('quality',self.current.role)
        return await self.risk.risk_case(case_id,lock=lock)

    @staticmethod
    def response(job):
        return {key:getattr(job,key) for key in ('id','case_id','created_by','status','assessment_id','error_code','message','created_at','started_at','finished_at')}

    async def latest(self,case_id):
        await self.case(case_id)
        job=await self.db.scalar(select(RiskAnalysisJob).where(RiskAnalysisJob.org_id==self.current.org_id,
            RiskAnalysisJob.case_id==case_id).order_by(RiskAnalysisJob.created_at.desc(),RiskAnalysisJob.id.desc()).limit(1).execution_options(populate_existing=True))
        return self.response(job) if job else None

    async def get(self,case_id,job_id):
        await self.case(case_id)
        job=await self.db.scalar(select(RiskAnalysisJob).where(RiskAnalysisJob.id==job_id,
            RiskAnalysisJob.case_id==case_id,RiskAnalysisJob.org_id==self.current.org_id).execution_options(populate_existing=True))
        if not job:raise NotFoundError('研判任务不存在或不在当前事项范围')
        return self.response(job)

    async def cancel(self,case_id,job_id):
        await self.case(case_id)
        job=await self.db.scalar(select(RiskAnalysisJob).where(RiskAnalysisJob.id==job_id,
            RiskAnalysisJob.case_id==case_id,RiskAnalysisJob.org_id==self.current.org_id).with_for_update().execution_options(populate_existing=True))
        if not job:raise NotFoundError('研判任务不存在')
        if job.created_by!=self.current.user_id:raise ForbiddenError('只有请求提交人可以取消排队')
        if job.status=='cancelled':return self.response(job)
        if job.status!='queued':raise ConflictError('任务已开始或已结束，请核对当前结果，不能按排队请求取消')
        job.status='cancelled';job.finished_at=utcnow();job.message='已取消排队，原有资料和研判版本保留'
        await self.db.flush()
        return self.response(job)

    async def authorize_sources(self,case):
        from app.services.execution_evidence_service import ExecutionEvidenceService
        authorization=ExecutionEvidenceService(self.db,self.current,self.risk.storage)
        for rid in case.source_record_ids or []:
            record=await self.db.scalar(select(QualitySourceRecord).where(QualitySourceRecord.org_id==self.current.org_id,
                QualitySourceRecord.id==rid,QualitySourceRecord.deleted_at.is_(None)).execution_options(populate_existing=True))
            submitted=(record and record.created_by==case.created_by and str(self.current.role)=='expert' and
                has_permission('quality_material_read_business',self.current.role))
            if not record or (not authorization.record_authorized(record) and not submitted):
                raise ForbiddenError('部分来源尚未授权给本次研判')

    async def queue(self,case_id,payload):
        self.risk.require_role({'user','expert'})
        require_role('quality',self.current.role)
        if settings.quality_demo_enabled:raise ValidationError('演示环境请使用演示草稿')
        body=payload.model_dump(mode='json',exclude={'request_key'})
        same=await self.db.scalar(select(RiskAnalysisJob).where(RiskAnalysisJob.org_id==self.current.org_id,
            RiskAnalysisJob.request_key==str(payload.request_key)))
        if same:
            if same.case_id!=case_id or same.payload!=body or same.created_by!=self.current.user_id:
                raise ConflictError('相同请求编号不能用于其他事项、操作者或分析条件')
            await self.case(case_id)
            return self.response(same)
        # An existing running job is returned without waiting on its case lock.
        active_query=select(RiskAnalysisJob).where(RiskAnalysisJob.org_id==self.current.org_id,
            RiskAnalysisJob.case_id==case_id,RiskAnalysisJob.status.in_(ACTIVE))
        active=await self.db.scalar(active_query)
        if active:
            await self.case(case_id)
            if active.payload!=body:raise ConflictError('本事项正在分析，请等待后再修改分析条件')
            return self.response(active)
        case=await self.case(case_id,lock=True)
        if case.scope.get('execution_mode')=='demo':raise ValidationError('演示事项不能进入真实模型分析')
        active=await self.db.scalar(active_query.with_for_update().execution_options(populate_existing=True))
        if active:
            if active.payload!=body:raise ConflictError('本事项已有其他分析请求')
            return self.response(active)
        latest=await self.db.scalar(select(QualityRiskAssessment.id).where(QualityRiskAssessment.org_id==self.current.org_id,
            QualityRiskAssessment.risk_case_id==case.id,QualityRiskAssessment.deleted_at.is_(None))
            .order_by(QualityRiskAssessment.version.desc()).limit(1).with_for_update())
        if latest!=(str(payload.base_assessment_id) if payload.base_assessment_id else None):
            raise ConflictError('研判版本已更新，请刷新查看，避免重复生成')
        await self.authorize_sources(case)
        from app.schemas.quality_risk import RiskAnalyzeRequest
        options=RiskAnalyzeRequest(policy_id=payload.policy_id,inspection_execution_run_id=payload.inspection_execution_run_id)
        job=RiskAnalysisJob(org_id=self.current.org_id,case_id=case_id,created_by=self.current.user_id,
            request_key=str(payload.request_key),payload=body,basis_hash=await analysis_basis(self.db,case,options))
        from sqlalchemy.exc import IntegrityError
        try:
            async with self.db.begin_nested():
                self.db.add(job);await self.db.flush()
        except IntegrityError:
            same=await self.db.scalar(select(RiskAnalysisJob).where(RiskAnalysisJob.org_id==self.current.org_id,
                RiskAnalysisJob.request_key==str(payload.request_key)).with_for_update())
            if same and same.case_id==case_id and same.payload==body and same.created_by==self.current.user_id:
                return self.response(same)
            raise ConflictError('请求编号已用于其他操作，请刷新后重试') from None
        return self.response(job)
