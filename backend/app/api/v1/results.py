from fastapi import APIRouter, Depends

from app.api.v1.deps import get_db, get_current_user
from app.core.exceptions import NotFoundError
from app.core.permissions import require_role
from app.schemas.common import PagedResponse, ResponseEnvelope
from app.schemas.result import ResultListItemResponse, ResultListQuery, ResultResponse, ReviewSubmit
from app.schemas.user import CurrentUser
from app.services.result_service import ResultService


router = APIRouter()


@router.get("", response_model=ResponseEnvelope[PagedResponse[ResultListItemResponse]])
async def list_results(
    query: ResultListQuery = Depends(),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("result", current.role)
    service = ResultService(db, current.org_id)
    rows, total = await service.list_results(query)
    items = [
        ResultListItemResponse(
            id=result.id,
            task_id=result.task_id,
            org_id=result.org_id,
            product_id=product_id,
            verdict=result.verdict,
            overall_score=float(result.overall_score or 0.0),
            llm_model=result.llm_model,
            prompt_version=result.prompt_version,
            created_at=result.created_at,
        )
        for result, product_id in rows
    ]
    return ResponseEnvelope(data=PagedResponse(items=items, total=total, page=query.page, size=query.size))


@router.get("/by-task/{task_id}", response_model=ResponseEnvelope[ResultResponse])
async def get_by_task(
    task_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("result", current.role)
    service = ResultService(db, current.org_id)
    result = await service.get_by_task(task_id)
    if not result:
        raise NotFoundError("Result not found for task")

    return ResponseEnvelope(data=ResultResponse.model_validate(result))


@router.patch("/{result_id}/review", response_model=ResponseEnvelope[dict])
async def review_result(
    result_id: str,
    payload: ReviewSubmit,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("result", current.role)
    service = ResultService(db, current.org_id)
    reviewed = await service.review(result_id, current.user_id, current.role, payload.model_dump())
    return ResponseEnvelope(data=reviewed)
