from fastapi import APIRouter, Depends
import uuid

from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import require_role
from app.schemas.common import PagedResponse, ResponseEnvelope
from app.schemas.governance import (
    FeedbackQuery,
    FeedbackResponse,
    FeedbackStatusUpdate,
    FeedbackSubmit,
    FeedbackSummaryResponse,
    MessageFeedbackQuery,
    MessageFeedbackResponse,
)
from app.schemas.user import CurrentUser
from app.services.feedback_service import FeedbackService


def _parse_uuid_list(raw: str | None) -> list[str]:
    """从逗号分隔字符串中提取合法 UUID，静默丢弃非法值。"""
    if not raw:
        return []
    result: list[str] = []
    for item in raw.split(","):
        stripped = item.strip()
        if not stripped:
            continue
        try:
            uuid.UUID(stripped)
            result.append(stripped)
        except ValueError:
            continue
    return result


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


@router.get("/summary", response_model=ResponseEnvelope[FeedbackSummaryResponse])
async def feedback_summary(
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("feedback", current.role)
    service = FeedbackService(db, current.org_id)
    data = await service.summary()
    return ResponseEnvelope(data=FeedbackSummaryResponse(**data))


@router.get("", response_model=ResponseEnvelope[PagedResponse[FeedbackResponse]])
async def list_feedbacks(
    query: FeedbackQuery = Depends(),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("feedback", current.role)
    service = FeedbackService(db, current.org_id)
    total, items = await service.list_feedbacks(
        query.page, query.size, query.result_id, query.feedback_type,
        query.status, query.severity, query.source_type, query.category, query.assigned_to,
    )
    return ResponseEnvelope(
        data=PagedResponse(
            items=[FeedbackResponse.model_validate(item) for item in items],
            total=total,
            page=query.page,
            size=query.size,
        )
    )


@router.get("/messages", response_model=ResponseEnvelope[list[MessageFeedbackResponse]])
async def list_message_feedbacks(
    query: MessageFeedbackQuery = Depends(),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("feedback", current.role)
    target_ids = _parse_uuid_list(query.target_ids)
    service = FeedbackService(db, current.org_id)
    items = await service.list_message_feedbacks(
        target_type=query.target_type,
        actor_id=current.user_id,
        target_ids=target_ids or None,
    )
    return ResponseEnvelope(data=[MessageFeedbackResponse.model_validate(item) for item in items])


@router.get("/{feedback_id}", response_model=ResponseEnvelope[FeedbackResponse])
async def get_feedback_detail(
    feedback_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("feedback", current.role)
    service = FeedbackService(db, current.org_id)
    item = await service.get_detail(feedback_id)
    return ResponseEnvelope(data=FeedbackResponse.model_validate(item))


@router.patch("/{feedback_id}/status", response_model=ResponseEnvelope[FeedbackResponse])
async def update_feedback_status(
    feedback_id: str,
    payload: FeedbackStatusUpdate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("feedback", current.role)
    service = FeedbackService(db, current.org_id)
    item = await service.update_status(feedback_id, payload.status.value, payload.resolution)
    return ResponseEnvelope(data=FeedbackResponse.model_validate(item))


@router.delete("/{feedback_id}", response_model=ResponseEnvelope[dict])
async def delete_feedback(
    feedback_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("feedback", current.role)
    service = FeedbackService(db, current.org_id)
    await service.delete(feedback_id)
    return ResponseEnvelope(data={"deleted": True, "feedback_id": feedback_id})


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
