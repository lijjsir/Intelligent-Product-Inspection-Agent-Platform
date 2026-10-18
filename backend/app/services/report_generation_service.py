"""Render a server-frozen result bundle, never the latest result row."""
import json
from datetime import timedelta
from infra.database.session import get_session
from app.core.config import settings
from app.core.datetime import utcnow
from app.core.exceptions import NotFoundError,ConflictError
from app.core.permissions import PermissionRole,require_role
from app.schemas.user import CurrentUser
from app.services.permission_service import PermissionService
from app.repositories.export_job_repo import ExportJobRepository
from app.services.task_result_bundle_service import TaskResultBundleService
from app.services.object_storage.factory import build_object_storage
from app.services.report_renderers import build_renderer


async def report_actor(session,job):
    identity=await PermissionService(session,job.org_id).identity(job.actor_id)
    role=PermissionRole(identity['role'],identity['effective'])
    for permission in ['report_generate','task','result']:require_role(permission,role)
    current=CurrentUser(user_id=job.actor_id,org_id=job.org_id,role=identity['role']);current.role=role
    return current


async def prepare_report(session,job):
    current=await report_actor(session,job)
    config=_parse_config(job.config_json)
    if job.report_type == 'risk_assessment':
        from app.services.risk_report_service import RiskReportService
        report=await RiskReportService(session,current).get(config.get('risk_report_id'))
        if report['snapshot_hash'] != config.get('snapshot_hash'):
            raise ConflictError('研判导出与固定报告摘要不一致')
        return {'risk_report':report}
    service=TaskResultBundleService(session,current)
    bundle=config.get('report_snapshot')
    if not bundle:
        # Old queued requests explicitly retain the legacy source they selected.
        bundle=await service.freeze(config.get('task_id'),legacy_only=True)
        job.config_json=json.dumps({**config,'report_snapshot':bundle},ensure_ascii=False)
        await session.commit()
    if bundle['task']['id']!=config.get('task_id'):raise ConflictError('导出任务与冻结结果范围不一致')
    await service.recheck(bundle)
    return bundle


async def generate_report(*,job_id:str,org_id:str):
    async with get_session() as session:
        repo=ExportJobRepository(session);job=await repo.get_by_id(job_id)
        if not job or job.org_id!=org_id:raise NotFoundError('导出任务不在当前组织')
        if job.status=='success':return
        await repo.update_status(job_id,'running');await session.commit()
        try:
            bundle=await prepare_report(session,job)
            format=job.format;report_name=job.report_name;report_type=job.report_type
            if format not in {'pdf','docx'}:raise ValueError('任务报告只支持 PDF 或 DOCX')
            content=build_renderer(format).render({'report_name':report_name,'report_type_label':_type_label(report_type),
                **bundle} if report_type=='risk_assessment' else {'report_name':report_name,'report_type_label':_type_label(report_type),'bundle':bundle})
            # Re-open the read snapshot, so withdrawal during rendering is visible.
            await session.commit();session.expire_all()
            fresh=await repo.get_by_id(job_id)
            if not fresh or fresh.org_id!=org_id:raise NotFoundError('导出任务已撤回')
            current=await report_actor(session,fresh)
            if report_type=='risk_assessment':
                fresh_bundle=await prepare_report(session,fresh)
                if fresh_bundle['risk_report']['snapshot_hash'] != bundle['risk_report']['snapshot_hash']:
                    raise ConflictError('研判报告快照已变化')
            else:
                await TaskResultBundleService(session,current).recheck(bundle)
            storage=build_object_storage();bucket=settings.report_export_bucket
            object_key=f'{org_id}/{job_id}/report.{format}'
            storage.ensure_bucket(bucket)
            storage.put_bytes(bucket=bucket,object_key=object_key,data=content,content_type=_content_type(format))
            await repo.update_status(job_id,'success',file_url=f'/api/v1/files/{bucket}/{object_key}',file_size=len(content),expires_at=utcnow()+timedelta(days=7))
            await session.commit()
        except Exception as exc:
            await session.rollback()
            await repo.update_status(job_id,'failed',error_message=str(exc));await session.commit()
            raise


def _parse_config(value):
    try:return json.loads(value or '{}')
    except (ValueError,TypeError):return {}


def _type_label(value):
    if value=='risk_assessment':return '独立演示研判报告'
    return {'single_task':'单任务检测记录','batch_summary':'检测汇总（本次单任务范围）','quality_analysis':'质量分析（本次单任务范围）',
        'feedback_report':'异常反馈（本次单任务范围）','evidence_trace':'证据溯源（本次单任务范围）'}.get(value,'单任务检测记录')


def _content_type(value):
    return {'pdf':'application/pdf','docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}[value]
