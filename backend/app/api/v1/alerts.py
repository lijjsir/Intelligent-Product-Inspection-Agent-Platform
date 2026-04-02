from fastapi import APIRouter, Depends

from app.api.v1.deps import get_db, get_current_user
from app.core.permissions import require_role
from app.schemas.alert import AlertResponse, AlertListQuery, AlertHandleRequest
from app.schemas.common import ResponseEnvelope, PagedResponse
from app.schemas.user import CurrentUser
from app.services.alert_service import AlertService


router = APIRouter()


@router.get("", response_model=ResponseEnvelope[PagedResponse[AlertResponse]])
async def list_alerts(
    query: AlertListQuery = Depends(),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("alert", current.role)
    service = AlertService(db, current.org_id)
    skip = (query.page - 1) * query.size
    total, items = await service.list_alerts(skip, query.size, query.status, query.severity)

    return ResponseEnvelope(
        data=PagedResponse(
            items=[AlertResponse.model_validate(item) for item in items],
            total=total,
            page=query.page,
            size=query.size,
        )
    )

@router.get("/{alert_id}", response_model=ResponseEnvelope[AlertResponse])
async def get_alert(
    alert_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("alert", current.role)
    service = AlertService(db, current.org_id)
    alert = await service.get(alert_id)
    if not alert:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("Alert not found")

    return ResponseEnvelope(data=AlertResponse.model_validate(alert))


@router.patch("/{alert_id}", response_model=ResponseEnvelope[AlertResponse])
async def handle_alert(
    alert_id: str,
    body: AlertHandleRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("alert", current.role)
    service = AlertService(db, current.org_id)
    alert = await service.handle_alert(
        alert_id, body.action, current.user_id, body.action_note
    )
    return ResponseEnvelope(data=AlertResponse.model_validate(alert))


@router.put("/{alert_id}/resolve", response_model=ResponseEnvelope[bool])
async def resolve_alert(
    alert_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """兼容旧接口，内部转调 handle_alert"""
    require_role("alert", current.role)
    service = AlertService(db, current.org_id)
    await service.resolve_alert(alert_id, current.user_id)
    return ResponseEnvelope(data=True)
