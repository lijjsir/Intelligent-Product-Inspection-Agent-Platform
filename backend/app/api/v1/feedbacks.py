from fastapi import APIRouter, Depends

from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import require_role
from app.schemas.common import PagedResponse, ResponseEnvelope
from app.schemas.governance import FeedbackQuery, FeedbackResponse, FeedbackSubmit
from app.schemas.user import CurrentUser
from app.services.feedback_service import FeedbackService


router = APIRouter()


@router.post("/results/{result_id}", response_model=ResponseEnvelope[FeedbackResponse])
async def submit_feedback(
    result_id: str,
    payload: FeedbackSubmit,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("feedback", current.role)
    service = FeedbackService(db, current.org_id)
    item = await service.submit(result_id, current.user_id, payload.model_dump())
    return ResponseEnvelope(data=FeedbackResponse.model_validate(item))


@router.get("", response_model=ResponseEnvelope[PagedResponse[FeedbackResponse]])
async def list_feedbacks(
    query: FeedbackQuery = Depends(),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("feedback", current.role)
    service = FeedbackService(db, current.org_id)
    total, items = await service.list_feedbacks(query.page, query.size, query.result_id, query.feedback_type)
    return ResponseEnvelope(
        data=PagedResponse(
            items=[FeedbackResponse.model_validate(item) for item in items],
            total=total,
            page=query.page,
            size=query.size,
        )
    )

