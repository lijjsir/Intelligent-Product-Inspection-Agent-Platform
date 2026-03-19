from fastapi import APIRouter, Depends

from app.api.v1.deps import get_db, get_current_user
from app.core.permissions import require_role
from app.schemas.alert import AlertResponse, AlertListQuery
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
    
    # Format datetimes
    formatted_items = []
    for item in items:
        if item.created_at: item.created_at = item.created_at.isoformat()
        if item.dispatched_at: item.dispatched_at = item.dispatched_at.isoformat()
        if item.ack_at: item.ack_at = item.ack_at.isoformat()
        if item.resolved_at: item.resolved_at = item.resolved_at.isoformat()
        formatted_items.append(AlertResponse.model_validate(item))
        
    return ResponseEnvelope(
        data=PagedResponse(
            items=formatted_items,
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
        
    if alert.created_at: alert.created_at = alert.created_at.isoformat()
    if alert.dispatched_at: alert.dispatched_at = alert.dispatched_at.isoformat()
    if alert.ack_at: alert.ack_at = alert.ack_at.isoformat()
    if alert.resolved_at: alert.resolved_at = alert.resolved_at.isoformat()

    return ResponseEnvelope(data=AlertResponse.model_validate(alert))

@router.put("/{alert_id}/resolve", response_model=ResponseEnvelope[bool])
async def resolve_alert(
    alert_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("alert", current.role)
    service = AlertService(db, current.org_id)
    success = await service.resolve_alert(alert_id, current.id)
    if not success:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("Alert not found")
    return ResponseEnvelope(data=True)
