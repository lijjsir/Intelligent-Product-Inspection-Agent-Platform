from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.api.v1.deps import get_current_user, get_db
from app.core.exceptions import ForbiddenError, ValidationError
from app.core.permissions import require_role
from app.core.security import safe_decode_token
from app.schemas.collab import (
    CollabAttachmentUploadResponse,
    CollabActionRequestCreateRequest,
    CollabMessageActionRequest,
    CollabMessageCreateRequest,
    CollabMessageReceiptResponse,
    CollabMessageResponse,
    CollabTargetResponse,
    CollabThreadCreateRequest,
    CollabThreadResponse,
    CollabWorkItemResponse,
    CollabWorkItemSummaryResponse,
)
from app.schemas.common import ResponseEnvelope
from app.schemas.user import CurrentUser
from app.services.collab_service import CollabService
from app.services.stream_service import collab_stream_broker


router = APIRouter(prefix="/collab", tags=["collab"])


def _build_service(db, current: CurrentUser) -> CollabService:
    require_role("collab", current.role)
    return CollabService(db, current.org_id, current.user_id, role=current.role)


def _get_user_for_stream(token: str = Query(default="")) -> CurrentUser:
    if not token:
        raise ForbiddenError("missing stream token")
    payload = safe_decode_token(token)
    if payload.get("typ") != "stream":
        raise ForbiddenError("invalid stream token type")
    current = CurrentUser(
        user_id=str(payload.get("user_id") or payload.get("sub") or ""),
        org_id=str(payload.get("org_id") or ""),
        role=str(payload.get("role") or ""),
        roles=[str(item) for item in (payload.get("roles") or [])],
        plan_tier=str(payload.get("plan_tier") or "basic"),
        capabilities=[str(item) for item in (payload.get("capabilities") or [])],
        workspaces=[str(item) for item in (payload.get("workspaces") or [])],
        default_workspace=str(payload.get("default_workspace") or "app"),
        stream_resource=payload.get("resource"),
        stream_resource_id=payload.get("resource_id"),
    )
    require_role("collab", current.role)
    if current.stream_resource and current.stream_resource != "collab":
        raise ForbiddenError("invalid stream token")
    if current.stream_resource_id and current.stream_resource_id != current.user_id:
        raise ForbiddenError("invalid stream token")
    return current


@router.get("/threads", response_model=ResponseEnvelope[list[CollabThreadResponse]])
async def list_threads(
    limit: int = Query(default=100, ge=1, le=200),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.list_threads(limit=limit))


@router.get("/targets", response_model=ResponseEnvelope[list[CollabTargetResponse]])
async def list_targets(
    limit: int = Query(default=100, ge=1, le=200),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.list_targets(limit=limit))


@router.post("/threads", response_model=ResponseEnvelope[CollabThreadResponse])
async def create_thread(
    body: CollabThreadCreateRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    _build_service(db, current)
    raise ValidationError("collaboration center only creates structured action requests")


@router.get("/work-items", response_model=ResponseEnvelope[list[CollabWorkItemResponse]])
async def list_work_items(
    view: str = Query(default="pending", pattern="^(pending|initiated|processed)$"),
    item_type: str | None = Query(default=None, pattern="^(memory_share|action_request)$"),
    scope_type: str | None = Query(default=None),
    room_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(
        data=await service.list_work_items(
            view=view,
            item_type=item_type,
            scope_type=scope_type,
            room_id=room_id,
            limit=limit,
        )
    )


@router.get("/summary", response_model=ResponseEnvelope[CollabWorkItemSummaryResponse])
async def get_work_item_summary(
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.get_work_item_summary())


@router.post("/action-requests", response_model=ResponseEnvelope[CollabWorkItemResponse])
async def create_action_request(
    body: CollabActionRequestCreateRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.create_action_request(body))


@router.get("/threads/{thread_id}/messages", response_model=ResponseEnvelope[list[CollabMessageResponse]])
async def list_messages(
    thread_id: str,
    limit: int = Query(default=200, ge=1, le=500),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.list_messages(thread_id, limit=limit))


@router.post("/threads/{thread_id}/messages", response_model=ResponseEnvelope[CollabMessageResponse])
async def send_message(
    thread_id: str,
    body: CollabMessageCreateRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.send_work_item_comment(thread_id, body))


@router.post("/messages/{message_id}/read", response_model=ResponseEnvelope[CollabMessageReceiptResponse])
async def mark_message_read(
    message_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.mark_read(message_id))


@router.post("/messages/{message_id}/action", response_model=ResponseEnvelope[CollabMessageReceiptResponse])
async def update_message_action(
    message_id: str,
    body: CollabMessageActionRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.update_action(message_id, body))


@router.post("/threads/{thread_id}/archive", response_model=ResponseEnvelope[CollabThreadResponse])
async def archive_thread(
    thread_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.archive_thread(thread_id))


@router.delete("/threads/{thread_id}", response_model=ResponseEnvelope[dict])
async def delete_thread(
    thread_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    _build_service(db, current)
    raise ValidationError("collaboration history is read-only and cannot be deleted")


@router.delete("/messages/{message_id}", response_model=ResponseEnvelope[dict])
async def delete_message(
    message_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    _build_service(db, current)
    raise ValidationError("collaboration history is read-only and cannot be deleted")


@router.get("/stream")
async def stream_collab_events(token: str = Query(default="")):
    current = _get_user_for_stream(token)

    async def event_generator():
        async for event in collab_stream_broker.subscribe(current.user_id):
            yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/uploads", response_model=ResponseEnvelope[CollabAttachmentUploadResponse])
async def upload_collab_attachments(
    files: list[UploadFile] = File(...),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    items = await service.upload_attachments(files)
    return ResponseEnvelope(data=CollabAttachmentUploadResponse(items=items))
