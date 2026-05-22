from fastapi import APIRouter, Depends

from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import require_role
from app.schemas.common import PagedResponse, ResponseEnvelope
from app.schemas.governance import FeedbackQuery, FeedbackResponse, FeedbackSubmit, MessageFeedbackQuery, MessageFeedbackResponse
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


@router.post("/messages/{target_type}/{target_id}", response_model=ResponseEnvelope[MessageFeedbackResponse])
async def submit_message_feedback(
    target_type: str,
    target_id: str,
    payload: FeedbackSubmit,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = FeedbackService(db, current.org_id)
    item = await service.submit_message_feedback(target_type, target_id, current.user_id, payload.model_dump())
    return ResponseEnvelope(data=MessageFeedbackResponse.model_validate(item))


@router.get("/messages", response_model=ResponseEnvelope[list[MessageFeedbackResponse]])
async def list_message_feedbacks(
    query: MessageFeedbackQuery = Depends(),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("feedback", current.role)
    target_ids = [item.strip() for item in (query.target_ids or "").split(",") if item.strip()]
    service = FeedbackService(db, current.org_id)
    items = await service.list_message_feedbacks(
        target_type=query.target_type,
        actor_id=current.user_id,
        target_ids=target_ids or None,
    )
    return ResponseEnvelope(data=[MessageFeedbackResponse.model_validate(item) for item in items])
