from fastapi import APIRouter, Depends

from app.api.v1.deps import get_db, get_current_user
from app.core.permissions import require_role
from app.schemas.common import ResponseEnvelope
from app.schemas.stability import StabilityResponse
from app.schemas.user import CurrentUser
from app.services.stability_service import StabilityService


router = APIRouter()


@router.get("/by-task/{task_id}", response_model=ResponseEnvelope[StabilityResponse])
async def get_by_task(
    task_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("stability", current.role)
    service = StabilityService(db, current.org_id)
    report = await service.get_by_task(task_id)
    if not report:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("Stability report not found for task")

    from app.schemas.stability import StabilityResponse
    if report.created_at:
        report.created_at = report.created_at.isoformat()
    if report.handled_at:
        report.handled_at = report.handled_at.isoformat()
    return ResponseEnvelope(data=StabilityResponse.model_validate(report))
