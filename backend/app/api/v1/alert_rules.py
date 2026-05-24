from fastapi import APIRouter, Depends

from app.api.v1.deps import get_db, get_current_user
from app.core.permissions import require_role
from app.schemas.alert_rule import AlertRuleCreate, AlertRuleUpdate, AlertRuleListQuery, AlertRuleResponse
from app.schemas.common import ResponseEnvelope, PagedResponse
from app.schemas.user import CurrentUser
from app.services.alert_rule_service import AlertRuleService
from app.core.exceptions import NotFoundError


router = APIRouter()


def _scope_org_id(current: CurrentUser) -> str | None:
    return current.org_id


@router.get("/rules", response_model=ResponseEnvelope[PagedResponse[AlertRuleResponse]])
async def list_alert_rules(
    query: AlertRuleListQuery = Depends(),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("alert_rule_read", current.role)
    service = AlertRuleService(db, _scope_org_id(current))
    skip = (query.page - 1) * query.size
    total, items = await service.list_rules(skip, query.size, query.severity, query.enabled)
    return ResponseEnvelope(
        data=PagedResponse(
            items=[AlertRuleResponse.model_validate(item) for item in items],
            total=total,
            page=query.page,
            size=query.size,
        )
    )


@router.post("/rules", response_model=ResponseEnvelope[AlertRuleResponse])
async def create_alert_rule(
    body: AlertRuleCreate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("alert_rule", current.role)
    service = AlertRuleService(db, _scope_org_id(current))
    payload = body.model_dump()
    payload["org_id"] = _scope_org_id(current)
    rule = await service.create_rule(payload)
    return ResponseEnvelope(data=AlertRuleResponse.model_validate(rule))


@router.get("/rules/{rule_id}", response_model=ResponseEnvelope[AlertRuleResponse])
async def get_alert_rule(
    rule_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("alert_rule_read", current.role)
    service = AlertRuleService(db, _scope_org_id(current))
    rule = await service.get(rule_id)
    if not rule:
        raise NotFoundError("Alert rule not found")
    return ResponseEnvelope(data=AlertRuleResponse.model_validate(rule))


@router.put("/rules/{rule_id}", response_model=ResponseEnvelope[AlertRuleResponse])
async def update_alert_rule(
    rule_id: str,
    body: AlertRuleUpdate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("alert_rule", current.role)
    service = AlertRuleService(db, _scope_org_id(current))
    rule = await service.update_rule(rule_id, body.model_dump(exclude_unset=True))
    return ResponseEnvelope(data=AlertRuleResponse.model_validate(rule))


@router.delete("/rules/{rule_id}", response_model=ResponseEnvelope[bool])
async def delete_alert_rule(
    rule_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("alert_rule", current.role)
    service = AlertRuleService(db, _scope_org_id(current))
    await service.delete_rule(rule_id)
    return ResponseEnvelope(data=True)
