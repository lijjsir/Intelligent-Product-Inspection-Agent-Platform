from fastapi import APIRouter, Depends

from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import require_role
from app.schemas.common import ResponseEnvelope
from app.schemas.governance import ModelConfigCreate, ModelConfigResponse, ModelConfigUpdate
from app.schemas.user import CurrentUser
from app.services.model_config_service import ModelConfigService


router = APIRouter()


def _to_response(model) -> ModelConfigResponse:
    return ModelConfigResponse(
        id=model.id,
        org_id=model.org_id,
        provider=model.provider,
        model_key=model.model_key,
        display_name=model.display_name,
        endpoint=model.endpoint,
        model_type=model.model_type,
        priority=model.priority,
        rpm_limit=model.rpm_limit,
        input_price_per_million=float(model.input_price_per_million) if model.input_price_per_million is not None else None,
        output_price_per_million=float(model.output_price_per_million) if model.output_price_per_million is not None else None,
        is_active=model.is_active,
        health_status=model.health_status,
        health_message=model.health_message,
        has_api_key=bool(model.api_key_enc),
    )


@router.get("", response_model=ResponseEnvelope[list[ModelConfigResponse]])
async def list_model_configs(
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("model_config", current.role)
    service = ModelConfigService(db, current.org_id)
    items = await service.list_configs()
    return ResponseEnvelope(data=[_to_response(item) for item in items])


@router.post("", response_model=ResponseEnvelope[ModelConfigResponse])
async def create_model_config(
    payload: ModelConfigCreate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("model_config", current.role)
    service = ModelConfigService(db, current.org_id)
    item = await service.create_config(payload.model_dump())
    return ResponseEnvelope(data=_to_response(item))


@router.patch("/{config_id}", response_model=ResponseEnvelope[ModelConfigResponse])
async def update_model_config(
    config_id: str,
    payload: ModelConfigUpdate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("model_config", current.role)
    service = ModelConfigService(db, current.org_id)
    item = await service.update_config(config_id, payload.model_dump(exclude_unset=True))
    return ResponseEnvelope(data=_to_response(item))


@router.delete("/{config_id}", response_model=ResponseEnvelope[bool])
async def delete_model_config(
    config_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("model_config", current.role)
    service = ModelConfigService(db, current.org_id)
    await service.delete_config(config_id)
    return ResponseEnvelope(data=True)
