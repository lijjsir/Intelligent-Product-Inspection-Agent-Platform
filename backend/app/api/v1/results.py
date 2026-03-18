from fastapi import APIRouter, Depends

from app.api.v1.deps import get_db, get_current_user
from app.core.permissions import require_role
from app.schemas.common import ResponseEnvelope
from app.schemas.result import ResultResponse
from app.schemas.user import CurrentUser
from app.services.result_service import ResultService


router = APIRouter()


@router.get("/by-task/{task_id}", response_model=ResponseEnvelope[ResultResponse])
async def get_by_task(
    task_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("result", current.role)
    service = ResultService(db, current.org_id)
    result = await service.get_by_task(task_id)

    return ResponseEnvelope(
        data=ResultResponse(
            id=result.id,
            task_id=result.task_id,
            org_id=result.org_id,
            verdict=result.verdict,
            overall_score=float(result.overall_score),
        )
    )
