from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import require_role
from app.schemas.approval import ApprovalCreate, ApprovalResponse, ApprovalReviewRequest
from app.schemas.common import PagedResponse, ResponseEnvelope
from app.schemas.user import CurrentUser
from app.services.approval_service import ApprovalService

router = APIRouter()


def _service(db, current: CurrentUser) -> ApprovalService:
    return ApprovalService(db, current.org_id)


@router.get("", response_model=ResponseEnvelope[PagedResponse[ApprovalResponse]])
async def list_approvals(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    status: str | None = Query(default=None),
    source_module: str | None = Query(default=None),
    risk_level: str | None = Query(default=None),
    requester_id: str | None = Query(default=None),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("approval_read", current.role)
    service = _service(db, current)
    items, total = await service.list_approvals(
        page=page,
        size=size,
        status=status,
        source_module=source_module,
        risk_level=risk_level,
        requester_id=requester_id,
        current_role=current.role,
        current_user_id=current.user_id,
    )
    return ResponseEnvelope(data=PagedResponse(items=[ApprovalResponse.model_validate(item) for item in items], total=total, page=page, size=size))


@router.get("/{approval_id}", response_model=ResponseEnvelope[ApprovalResponse])
async def get_approval(
    approval_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("approval_read", current.role)
    service = _service(db, current)
    return ResponseEnvelope(data=ApprovalResponse.model_validate(await service.get_approval(approval_id, current.role, current.user_id)))


@router.post("", response_model=ResponseEnvelope[ApprovalResponse])
async def create_approval(
    payload: ApprovalCreate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("approval_create", current.role)
    service = _service(db, current)
    approval = await service.create_approval(current.user_id, current.role, payload)
    return ResponseEnvelope(data=ApprovalResponse.model_validate(approval))


@router.post("/{approval_id}/approve", response_model=ResponseEnvelope[ApprovalResponse])
async def approve_approval(
    approval_id: str,
    payload: ApprovalReviewRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("approval", current.role)
    service = _service(db, current)
    approval = await service.approve(approval_id, current.user_id, payload.comment)
    return ResponseEnvelope(data=ApprovalResponse.model_validate(approval))


@router.post("/{approval_id}/reject", response_model=ResponseEnvelope[ApprovalResponse])
async def reject_approval(
    approval_id: str,
    payload: ApprovalReviewRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("approval", current.role)
    service = _service(db, current)
    approval = await service.reject(approval_id, current.user_id, payload.comment)
    return ResponseEnvelope(data=ApprovalResponse.model_validate(approval))


@router.post("/{approval_id}/cancel", response_model=ResponseEnvelope[ApprovalResponse])
async def cancel_approval(
    approval_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("approval_create", current.role)
    service = _service(db, current)
    approval = await service.cancel(approval_id, current.user_id)
    return ResponseEnvelope(data=ApprovalResponse.model_validate(approval))
