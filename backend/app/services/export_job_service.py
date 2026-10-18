from __future__ import annotations

import json

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError,ConflictError
from app.core.permissions import ROLE_USER, require_role
from app.core.ids import uuid7
from app.repositories.export_job_repo import ExportJobRepository
from app.services.base import TenantAwareService


class ExportJobService(TenantAwareService):
    def __init__(self, session, org_id: str, *, actor_user_id: str | None = None, actor_role: str | None = None):
        super().__init__(session, org_id)
        self._repo = ExportJobRepository(session)
        self._actor_user_id = actor_user_id
        self._actor_role = actor_role

    def _require_business_access(self, permission: str = "report_read") -> None:
        if self._actor_role is not None:
            require_role(permission, self._actor_role)
            require_role("task", self._actor_role)
            require_role("result", self._actor_role)

    @property
    def _owner_user_id(self) -> str | None:
        if self._actor_role == ROLE_USER and not self._actor_user_id:
            raise ForbiddenError("缺少当前用户身份")
        return self._actor_user_id if self._actor_role == ROLE_USER else None

    async def create_job(self, actor_id: str, payload: dict):
        self._require_business_access("report_generate")
        if payload.get('report_type') == 'risk_assessment':
            return await self.create_risk_report_job(actor_id, payload)
        if self._actor_user_id is not None and actor_id!=self._actor_user_id:raise ForbiddenError('导出创建者必须是当前业务身份')
        if self._actor_role == ROLE_USER:
            if not self._owner_user_id or actor_id != self._owner_user_id:
                raise ForbiddenError("只能创建本人的报告导出记录")
            if payload.get("report_type") != "single_task":
                raise ForbiddenError("普通用户只能导出本人任务的检测报告")
            if payload.get("format", "pdf") not in {"pdf", "docx"}:
                raise ValidationError("检测报告支持 PDF 或 DOCX 格式")
            from app.repositories.task_repo import TaskRepository

            config = dict(payload.get("config_json") or {})
            task_id = str(config.get("task_id") or "").strip()
            if not task_id:
                raise ValidationError("请选择需要导出报告的检测任务")
            task = await TaskRepository(self._session).get_for_user(
                self._org_id, task_id, owner_user_id=self._owner_user_id,
            )
            if not task:
                raise NotFoundError("检测任务不存在或无权访问")
            payload = {**payload, "template": "standard", "config_json": {
                "task_id": task_id,
                "execution_run_id":config.get('execution_run_id'),"legacy_only":bool(config.get('legacy_only',False)),
                "expected_result_token":config.get('expected_result_token'),
                "include_defects": True,
                "include_citations": True,
                "include_reasoning": False,
            }}
        config=dict(payload.get('config_json') or {})
        task_id=str(config.get('task_id') or '').strip()
        if not task_id:raise ValidationError('请选择报告对应的具体任务')
        if payload.get('format','pdf') not in {'pdf','docx'}:raise ValidationError('任务报告支持 PDF 或 Word 格式')
        from app.schemas.user import CurrentUser
        from app.services.task_result_bundle_service import TaskResultBundleService
        if not self._actor_role or not self._actor_user_id:raise ForbiddenError('报告生成需有明确业务身份')
        current=CurrentUser(user_id=self._actor_user_id,org_id=self._org_id,role=str(self._actor_role));current.role=self._actor_role
        bundle=await TaskResultBundleService(self._session,current).freeze(task_id,execution_run_id=config.get('execution_run_id'),
            legacy_only=bool(config.get('legacy_only',False)),expected_result_token=config.get('expected_result_token'))
        # Source data is always resolved by the server, never accepted from config_json.
        payload={**payload,'config_json':{'task_id':task_id,'execution_run_id':bundle['selection']['execution_run_id'],
            'legacy_only':bundle['selection']['legacy_only'],'include_defects':True,'include_citations':True,'include_reasoning':False,
            'report_snapshot':bundle}}
        from app.core.datetime import utcnow
        now = utcnow()
        config_json = payload.get("config_json")
        if isinstance(config_json, dict):
            config_json = json.dumps(config_json, ensure_ascii=False)
        job = await self._repo.create({
            "id": str(uuid7()),
            "org_id": self._org_id,
            "actor_id": actor_id,
            "report_name": payload["report_name"],
            "report_type": payload["report_type"],
            "format": payload.get("format", "pdf"),
            "template": payload.get("template", "standard"),
            "config_json": config_json,
            "status": "pending",
            "created_at": now,
            "updated_at": now,
        })
        # The report worker opens its own session and must see a committed job.
        await self._session.commit()

        import asyncio
        from worker.tasks.report_generate_task import generate_report_task

        task_payload = {"job_id": job.id, "org_id": self._org_id}
        try:
            generate_report_task.delay(task_payload)
        except Exception:
            from worker.tasks.report_generate_task import _run
            asyncio.create_task(_run(task_payload))

        return job

    async def create_risk_report_job(self, actor_id, payload):
        from app.schemas.user import CurrentUser
        from app.services.risk_report_service import RiskReportService
        from app.services.report_generation_service import generate_report
        from app.models.export_job import ExportJob
        from app.core.datetime import utcnow
        from sqlalchemy import select
        if not self._actor_user_id or actor_id != self._actor_user_id or str(self._actor_role) != 'expert':
            raise ForbiddenError('研判报告导出需要明确的专家身份')
        current = CurrentUser(user_id=actor_id, org_id=self._org_id, role=str(self._actor_role)); current.role = self._actor_role
        service = RiskReportService(self._session, current)
        await service.guard(write=True)
        config = payload.get('config_json') or {}
        if set(config) != {'risk_report_id'} or payload.get('format', 'pdf') not in {'pdf', 'docx'}:
            raise ValidationError('研判报告仅接受原报告编号与 PDF/Word 格式，不接受任务或客户端快照')
        from uuid import UUID
        try: report_id = str(UUID(str(config['risk_report_id'])))
        except (TypeError, ValueError): raise ValidationError('研判报告编号无效') from None
        report = await service.get(report_id)
        format = payload.get('format', 'pdf')
        renderer_version = 'risk-report-v1' if report['snapshot']['execution_mode'] == 'demo' else 'risk-report-v2'
        # Serialize retries in the demo organization, then reuse an unexpired
        # export of this same immutable report and format by the same reader.
        jobs = list(await self._session.scalars(select(ExportJob).where(ExportJob.org_id == self._org_id,
            ExportJob.actor_id == actor_id, ExportJob.report_type == 'risk_assessment', ExportJob.format == format,
            ExportJob.deleted_at.is_(None)).with_for_update().execution_options(populate_existing=True)))
        inflight = None
        from datetime import timedelta
        for job in jobs:
            job_config = json.loads(job.config_json or '{}')
            if job_config.get('risk_report_id') == report['id'] and job_config.get('renderer_version') == renderer_version and job.status == 'success' and job.expires_at and job.expires_at > utcnow():
                return job
            if job_config.get('risk_report_id') == report['id'] and job_config.get('renderer_version') == renderer_version and job.status in {'pending', 'running'} and job.created_at >= utcnow() - timedelta(minutes=5):
                if inflight is None or job.created_at > inflight.created_at:
                    inflight = job
        if inflight is not None:
            return inflight
        job = await self._repo.create({'id': str(uuid7()), 'org_id': self._org_id, 'actor_id': actor_id,
            'report_name': report['title'], 'report_type': 'risk_assessment', 'format': format, 'template': 'risk_assessment',
            'config_json': json.dumps({'risk_report_id': report['id'], 'snapshot_hash': report['snapshot_hash'], 'renderer_version':renderer_version}, ensure_ascii=False),
            'status': 'pending', 'created_at': utcnow(), 'updated_at': utcnow()})
        await self._session.commit()
        # The isolated compose intentionally has no model/Celery workers. Use
        # the same renderer/storage generation service directly for this type.
        job_id = job.id
        await generate_report(job_id=job_id, org_id=self._org_id)
        self._session.expire_all()
        return await self.get_detail(job_id)

    async def get_detail(self, job_id: str):
        self._require_business_access()
        job = await self._repo.get_by_id(job_id)
        if not job or job.org_id != self._org_id or (
            self._actor_role == ROLE_USER and job.actor_id != self._owner_user_id
        ):
            raise NotFoundError("export job not found")
        try:config=json.loads(getattr(job,'config_json',None) or '{}')
        except (ValueError,TypeError):config={}
        if job.report_type == 'risk_assessment':
            if job.actor_id != self._actor_user_id:
                raise ForbiddenError('只能读取本人生成的研判导出记录')
            from app.schemas.user import CurrentUser
            from app.services.risk_report_service import RiskReportService
            current=CurrentUser(user_id=self._actor_user_id,org_id=self._org_id,role=str(self._actor_role));current.role=self._actor_role
            report=await RiskReportService(self._session,current).get(config.get('risk_report_id'))
            if report['snapshot_hash'] != config.get('snapshot_hash'):
                raise ConflictError('导出与原报告快照不一致')
            job.source_issues=report['source_issues']; job.source_version=report['snapshot_hash']
            job.result_scope={'label':'演示研判报告' if report['snapshot']['execution_mode'] == 'demo' else '风险研判报告','assessment_version':report['snapshot']['assessment_version']}
            job.effective_status=report['effective_status']
            return job
        snapshot=config.get('report_snapshot') or {}
        if snapshot.get('risks'):
            from app.core.permissions import has_permission
            if not has_permission('quality',self._actor_role):raise ForbiddenError('没有此风险研判报告的读取权限')
        if snapshot.get('execution'):
            from app.core.permissions import has_permission
            if str(self._actor_role) not in {'user','expert'} or not has_permission('inspection_execution',self._actor_role):
                raise ForbiddenError('没有此标准执行报告的读取权限')
        if snapshot and self._actor_role:
            from app.schemas.user import CurrentUser
            from app.services.task_result_bundle_service import TaskResultBundleService
            current=CurrentUser(user_id=self._actor_user_id,org_id=self._org_id,role=str(self._actor_role));current.role=self._actor_role
            await TaskResultBundleService(self._session,current).task(snapshot['task']['id'])
            try:
                fresh=await TaskResultBundleService(self._session,current).recheck(snapshot)
                job.source_issues=[]
            except (ConflictError,NotFoundError,ValidationError) as exc:
                job.source_issues=[exc.message]
            job.result_scope=snapshot.get('scope',{});job.source_version=snapshot.get('result_token')
            job.effective_status='historical_snapshot' if job.source_issues else job.status
        return job

    async def list_jobs(self, page: int, size: int, status: str | None = None, report_type: str | None = None, *, task_id: str | None = None):
        self._require_business_access()
        filters = {"task_id": task_id} if task_id else {}
        if str(self._actor_role) == 'expert':
            filters['risk_actor_id'] = self._actor_user_id
        return await self._repo.list_jobs(
            self._org_id, page, size, status, report_type, actor_id=self._owner_user_id, **filters,
        )

    async def delete_job(self, job_id: str):
        self._require_business_access("report_generate")
        await self.get_detail(job_id)
        deleted = await self._repo.soft_delete(job_id)
        if not deleted:
            raise NotFoundError("export job not found")
