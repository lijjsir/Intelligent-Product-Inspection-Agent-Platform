from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.v1.deps import get_current_user
from app.schemas.common import ResponseEnvelope
from app.schemas.stream import StreamSessionCreateRequest, StreamSessionResponse
from app.schemas.user import CurrentUser
from app.services.chat_service import ChatService


router = APIRouter(prefix="/streams", tags=["streams"])


@router.post("/session", response_model=ResponseEnvelope[StreamSessionResponse])
async def create_stream_session(
    body: StreamSessionCreateRequest,
    current: CurrentUser = Depends(get_current_user),
):
    service = ChatService(org_id=current.org_id, user_id=current.user_id, current=current)
    return ResponseEnvelope(data=await service.create_stream_session(resource=body.resource, resource_id=body.resource_id))
