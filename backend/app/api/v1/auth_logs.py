from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import require_role
from app.schemas.auth_log import AuthLogResponse
from app.schemas.common import PagedResponse, ResponseEnvelope
from app.schemas.user import CurrentUser
from app.services.auth_log_service import AuthLogService

router = APIRouter()


def _to_response(log) -> AuthLogResponse:
    return AuthLogResponse(
        id=log.id,
        org_id=log.org_id,
        user_id=log.user_id,
        username=log.username,
        event_type=log.event_type,
        ip_address=log.ip_address,
        user_agent=log.user_agent,
        success=log.success,
        detail=log.detail,
        occurred_at=log.occurred_at,
    )


@router.get("", response_model=ResponseEnvelope[PagedResponse[AuthLogResponse]])
async def list_auth_logs(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    user_id: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    ip_address: str | None = Query(default=None),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("auth_log", current.role)
    service = AuthLogService(db)
    items, total = await service.list_logs(
        org_id=current.org_id,
        page=page,
        size=size,
        user_id=user_id,
        event_type=event_type,
        ip_address=ip_address,
        start_date=start_date,
        end_date=end_date,
    )
    return ResponseEnvelope(
        data=PagedResponse(
            items=[_to_response(item) for item in items],
            total=total,
            page=page,
            size=size,
        )
    )
