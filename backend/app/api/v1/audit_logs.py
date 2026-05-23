from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import require_role
from app.repositories.audit_repo import AuditRepository
from app.schemas.audit_log import AuditLogResponse
from app.schemas.common import PagedResponse, ResponseEnvelope
from app.schemas.user import CurrentUser

router = APIRouter()


def _to_response(log) -> AuditLogResponse:
    return AuditLogResponse(
        id=log.id,
        org_id=log.org_id,
        actor_id=log.actor_id,
        actor_role=log.actor_role,
        resource_type=log.resource_type,
        resource_id=log.resource_id,
        action=log.action,
        payload_hash=log.payload_hash,
        request_id=log.request_id,
        ip_address=log.ip_address,
        user_agent=log.user_agent,
        result_code=log.result_code,
        occurred_at=log.occurred_at,
    )


@router.get("", response_model=ResponseEnvelope[PagedResponse[AuditLogResponse]])
async def list_audit_logs(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    actor_id: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    action: str | None = Query(default=None),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("audit_log", current.role)
    repo = AuditRepository(db)
    items, total = await repo.list_logs(
        org_id=current.org_id,
        page=page,
        size=size,
        actor_id=actor_id,
        resource_type=resource_type,
        action=action,
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
