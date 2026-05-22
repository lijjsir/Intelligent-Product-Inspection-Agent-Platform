from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import require_role
from app.schemas.common import ResponseEnvelope
from app.schemas.meeting import AdminMeetingRoomQuery, AdminMeetingRoomResponse, MeetingRoomDetailResponse
from app.schemas.user import CurrentUser
from app.services.meeting_admin_service import MeetingAdminService


router = APIRouter(prefix="/admin/meetings", tags=["admin-meetings"])


def _build_admin_service(db, current: CurrentUser) -> MeetingAdminService:
    require_role("meeting_admin", current.role)
    return MeetingAdminService(db, current.org_id)


@router.get("/", response_model=ResponseEnvelope[dict])
async def list_all_rooms(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
    keyword: str | None = Query(default=None),
    status: str | None = Query(default=None),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_admin_service(db, current)
    results, total = await service.list_all_rooms(page=page, size=size, keyword=keyword, status=status)
    return ResponseEnvelope(data={
        "items": [item.model_dump() for item in results],
        "total": total,
        "page": page,
        "size": size,
    })


@router.get("/{room_id}", response_model=ResponseEnvelope[MeetingRoomDetailResponse])
async def get_room(
    room_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_admin_service(db, current)
    return ResponseEnvelope(data=await service.get_room_detail(room_id))


@router.delete("/{room_id}", response_model=ResponseEnvelope[dict])
async def archive_room(
    room_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_admin_service(db, current)
    await service.archive_room(room_id)
    return ResponseEnvelope(data={"ok": True})


@router.delete("/{room_id}/members/{user_id}", response_model=ResponseEnvelope[dict])
async def remove_member(
    room_id: str,
    user_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_admin_service(db, current)
    await service.remove_member(room_id, user_id)
    return ResponseEnvelope(data={"ok": True})
