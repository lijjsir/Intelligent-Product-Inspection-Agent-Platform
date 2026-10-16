from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import require_role
from app.schemas.common import PagedResponse, ResponseEnvelope
from app.schemas.governance import ExportJobCreate, ExportJobQuery, ExportJobResponse
from app.schemas.user import CurrentUser
from app.services.export_job_service import ExportJobService
from app.services.object_storage.factory import build_object_storage


router = APIRouter()


@router.post("", response_model=ResponseEnvelope[ExportJobResponse])
async def create_export_job(
    payload: ExportJobCreate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("report_generate", current.role)
    service = ExportJobService(db, current.org_id, actor_user_id=current.user_id, actor_role=current.role)
    item = await service.create_job(current.user_id, payload.model_dump(mode="json"))
    return ResponseEnvelope(data=ExportJobResponse.model_validate(item))


@router.get("", response_model=ResponseEnvelope[PagedResponse[ExportJobResponse]])
async def list_export_jobs(
    query: ExportJobQuery = Depends(),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("report_read", current.role)
    service = ExportJobService(db, current.org_id, actor_user_id=current.user_id, actor_role=current.role)
    total, items = await service.list_jobs(query.page, query.size, query.status, query.report_type, task_id=query.task_id)
    return ResponseEnvelope(
        data=PagedResponse(
            items=[ExportJobResponse.model_validate(item) for item in items],
            total=total,
            page=query.page,
            size=query.size,
        )
    )


@router.get("/{job_id}", response_model=ResponseEnvelope[ExportJobResponse])
async def get_export_job(
    job_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("report_read", current.role)
    service = ExportJobService(db, current.org_id, actor_user_id=current.user_id, actor_role=current.role)
    item = await service.get_detail(job_id)
    return ResponseEnvelope(data=ExportJobResponse.model_validate(item))


@router.get("/{job_id}/download")
async def download_export_job(
    job_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("report_read", current.role)
    service = ExportJobService(db, current.org_id, actor_user_id=current.user_id, actor_role=current.role)
    job = await service.get_detail(job_id)
    from app.core.datetime import utcnow
    if not job.file_url or job.status!='success' or (job.expires_at and job.expires_at<utcnow()):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="report file not available")
    storage = build_object_storage()
    # Parse bucket/object_key from file_url
    # file_url format: /api/v1/files/{bucket}/{object_key}
    url = job.file_url
    if url.startswith("/api/v1/files/"):
        parts = url[len("/api/v1/files/"):].split("/", 1)
        if len(parts) == 2:
            bucket, object_key = parts[0], parts[1]
            result = storage.get_bytes(bucket=bucket, object_key=object_key)
            if result:
                content, content_type = result
                filename = f"{job.report_name or 'report'}.{job.format or 'pdf'}"
                encoded = quote(filename)
                return Response(
                    content=content,
                    media_type=content_type or "application/octet-stream",
                    headers={
                        "Content-Disposition": (
                            f'attachment; filename="{encoded}";'
                            f" filename*=UTF-8''{encoded}"
                        ),
                    },
                )
    from app.core.exceptions import NotFoundError
    raise NotFoundError('报告原件不存在或定位信息无效，请重新生成')


@router.delete("/{job_id}", response_model=ResponseEnvelope[None])
async def delete_export_job(
    job_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("report_generate", current.role)
    service = ExportJobService(db, current.org_id, actor_user_id=current.user_id, actor_role=current.role)
    await service.delete_job(job_id)
    return ResponseEnvelope()
