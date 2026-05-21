from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import require_role
from app.schemas.common import ResponseEnvelope
from app.schemas.meeting import (
    MeetingMessageCreateRequest,
    MeetingMessageResponse,
    MeetingRoomCreateRequest,
    MeetingRoomJoinRequest,
    MeetingRoomResponse,
)
from app.schemas.user import CurrentUser
from app.services.meeting_service import MeetingService


router = APIRouter(prefix="/meetings", tags=["meetings"])


def _build_service(db, current: CurrentUser) -> MeetingService:
    require_role("meeting", current.role)
    return MeetingService(db, current.org_id, current.user_id)


@router.get("/rooms", response_model=ResponseEnvelope[list[MeetingRoomResponse]])
async def list_rooms(
    limit: int = Query(default=100, ge=1, le=200),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.list_rooms(limit=limit))


@router.post("/rooms", response_model=ResponseEnvelope[MeetingRoomResponse])
async def create_room(
    body: MeetingRoomCreateRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.create_room(body.title, body.password))


@router.post("/rooms/join", response_model=ResponseEnvelope[MeetingRoomResponse])
async def join_room(
    body: MeetingRoomJoinRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.join_room(body.access_code, body.password))


@router.get("/rooms/{room_id}/messages", response_model=ResponseEnvelope[list[MeetingMessageResponse]])
async def list_messages(
    room_id: str,
    after_seq: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.list_messages(room_id, after_seq=after_seq, limit=limit))


@router.post("/rooms/{room_id}/messages", response_model=ResponseEnvelope[MeetingMessageResponse])
async def send_message(
    room_id: str,
    body: MeetingMessageCreateRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.send_message(room_id, body.content))
