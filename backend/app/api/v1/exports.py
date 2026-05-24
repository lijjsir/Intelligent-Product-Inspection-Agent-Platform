from fastapi import APIRouter, Depends

from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import require_role
from app.schemas.common import PagedResponse, ResponseEnvelope
from app.schemas.governance import ExportJobCreate, ExportJobQuery, ExportJobResponse
from app.schemas.user import CurrentUser
from app.services.export_job_service import ExportJobService


router = APIRouter()


@router.post("", response_model=ResponseEnvelope[ExportJobResponse])
async def create_export_job(
    payload: ExportJobCreate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("feedback", current.role)
    service = ExportJobService(db, current.org_id)
    item = await service.create_job(current.user_id, payload.model_dump())
    return ResponseEnvelope(data=ExportJobResponse.model_validate(item))


@router.get("", response_model=ResponseEnvelope[PagedResponse[ExportJobResponse]])
async def list_export_jobs(
    query: ExportJobQuery = Depends(),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("feedback", current.role)
    service = ExportJobService(db, current.org_id)
    total, items = await service.list_jobs(query.page, query.size, query.status, query.report_type)
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
    require_role("feedback", current.role)
    service = ExportJobService(db, current.org_id)
    item = await service.get_detail(job_id)
    return ResponseEnvelope(data=ExportJobResponse.model_validate(item))


@router.delete("/{job_id}", response_model=ResponseEnvelope[None])
async def delete_export_job(
    job_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("feedback", current.role)
    service = ExportJobService(db, current.org_id)
    await service.delete_job(job_id)
    return ResponseEnvelope()
