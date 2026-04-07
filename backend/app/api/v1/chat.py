from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.api.v1.deps import get_current_user, get_db
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.permissions import require_role
from app.schemas.chat import (
    ChatMessageResponse,
    ChatMessageSendRequest,
    ChatSendResponse,
    ChatSessionCreateRequest,
    ChatSessionResponse,
    ChatTaskSubmitRequest,
    ChatTaskResultAppendRequest,
)
from app.schemas.common import ResponseEnvelope
from app.schemas.rag_space import AttachmentUploadResponse
from app.schemas.user import CurrentUser
from app.services.chat_service import ChatService, get_current_user_for_stream
from app.services.rag_space_service import RagSpaceService


router = APIRouter(prefix="/chat", tags=["chat"])


def _build_service(current: CurrentUser) -> ChatService:
    require_role("chat", current.role)
    return ChatService(org_id=current.org_id, user_id=current.user_id, current=current)


@router.get("/sessions", response_model=ResponseEnvelope[list[ChatSessionResponse]])
async def list_sessions(
    limit: int = Query(default=100, ge=1, le=200),
    current: CurrentUser = Depends(get_current_user),
):
    service = _build_service(current)
    return ResponseEnvelope(data=await service.list_sessions(limit=limit))


@router.post("/sessions", response_model=ResponseEnvelope[ChatSessionResponse])
async def create_session(
    body: ChatSessionCreateRequest,
    current: CurrentUser = Depends(get_current_user),
):
    service = _build_service(current)
    return ResponseEnvelope(data=await service.create_session(title=body.title))


@router.get("/sessions/{session_id}/messages", response_model=ResponseEnvelope[list[ChatMessageResponse]])
async def list_messages(
    session_id: str,
    after_seq: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
    current: CurrentUser = Depends(get_current_user),
):
    service = _build_service(current)
    return ResponseEnvelope(data=await service.list_messages(session_id, after_seq=after_seq, limit=limit))


@router.post("/sessions/{session_id}/messages", response_model=ResponseEnvelope[ChatSendResponse])
async def send_message(
    session_id: str,
    body: ChatMessageSendRequest,
    current: CurrentUser = Depends(get_current_user),
):
    service = _build_service(current)
    return ResponseEnvelope(data=await service.send_message(session_id, body))


@router.post("/sessions/{session_id}/task-result", response_model=ResponseEnvelope[ChatMessageResponse])
async def append_task_result(
    session_id: str,
    body: ChatTaskResultAppendRequest,
    current: CurrentUser = Depends(get_current_user),
):
    service = _build_service(current)
    return ResponseEnvelope(data=await service.append_task_result(session_id=session_id, payload=body))


@router.post("/sessions/{session_id}/tasks/submit", response_model=ResponseEnvelope[ChatMessageResponse])
async def submit_task_from_chat(
    session_id: str,
    body: ChatTaskSubmitRequest,
    current: CurrentUser = Depends(get_current_user),
):
    service = _build_service(current)
    return ResponseEnvelope(data=await service.submit_task(session_id=session_id, payload=body))


@router.post("/uploads", response_model=ResponseEnvelope[AttachmentUploadResponse])
async def upload_chat_attachments(
    files: list[UploadFile] = File(...),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("chat", current.role)
    service = RagSpaceService(db, org_id=current.org_id, user_id=current.user_id)
    items = await service.upload_attachments(files=files)
    return ResponseEnvelope(data=AttachmentUploadResponse(items=items))


@router.delete("/sessions/{session_id}", response_model=ResponseEnvelope[dict])
async def delete_session(
    session_id: str,
    current: CurrentUser = Depends(get_current_user),
):
    service = _build_service(current)
    deleted = await service.delete_session(session_id)
    if not deleted:
        raise NotFoundError("chat session not found")
    return ResponseEnvelope(data={"deleted": True})


@router.get("/sessions/{session_id}/stream")
async def stream_session(
    session_id: str,
    current: CurrentUser = Depends(get_current_user_for_stream),
):
    if current.org_id == "":
        raise ForbiddenError("invalid stream token")
    if current.stream_resource != "chat" or current.stream_resource_id != session_id:
        raise ForbiddenError("invalid stream token")

    async def event_iter() -> AsyncIterator[str]:
        yield 'event: ready\ndata: {"message":"stream_connected"}\n\n'
        service = ChatService(org_id=current.org_id, user_id=current.user_id, current=current)
        stream = service.stream_events(session_id).__aiter__()
        while True:
            try:
                event = await asyncio.wait_for(stream.__anext__(), timeout=15.0)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            except StopAsyncIteration:
                break
            payload = json.dumps(event, ensure_ascii=False)
            yield f"event: message\ndata: {payload}\n\n"

    return StreamingResponse(event_iter(), media_type="text/event-stream")
