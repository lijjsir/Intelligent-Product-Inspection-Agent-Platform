from fastapi import APIRouter, Depends

from agent.llm.health_checker import ModelHealthChecker
from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import require_role
from app.repositories.model_config_repo import ModelConfigRepository
from app.schemas.common import ResponseEnvelope
from app.schemas.governance import HealthCheckAllResult, HealthCheckResult, ModelConfigCreate, ModelConfigResponse, ModelConfigUpdate
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
    await db.refresh(item)
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
    await db.refresh(item)
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


@router.post("/health-check-all", response_model=ResponseEnvelope[HealthCheckAllResult])
async def check_all_models_health(
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("model_config", current.role)
    repo = ModelConfigRepository(db)
    models = await repo.list_health_targets()
    runtimes = [ModelConfigService.to_runtime_payload(m) for m in models]
    checked = await ModelHealthChecker().check(runtimes)
    status_count = {"healthy": 0, "degraded": 0, "unhealthy": 0}
    index = {str(m.id): m for m in models}
    for item in checked:
        model = index.get(str(item.get("id") or ""))
        if not model:
            continue
        hs = str(item.get("health_status") or "unknown")
        hm = item.get("health_message")
        await repo.update_health(model, health_status=hs, health_message=str(hm) if hm else None)
        if hs in status_count:
            status_count[hs] += 1
    await db.commit()
    return ResponseEnvelope(data=HealthCheckAllResult(
        checked=len(checked),
        healthy=status_count["healthy"],
        degraded=status_count["degraded"],
        unhealthy=status_count["unhealthy"],
    ))


@router.post("/{config_id}/health-check", response_model=ResponseEnvelope[HealthCheckResult])
async def check_single_model_health(
    config_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("model_config", current.role)
    service = ModelConfigService(db, current.org_id)
    model = await service.get_config(config_id)
    runtime = ModelConfigService.to_runtime_payload(model)
    status, message = await ModelHealthChecker()._check_one(runtime)
    repo = ModelConfigRepository(db)
    await repo.update_health(model, health_status=status, health_message=message)
    await db.commit()
    return ResponseEnvelope(data=HealthCheckResult(health_status=status, health_message=message))
