from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import require_role
from app.schemas.agent_ops import (
    AgentDefinitionCreate,
    AgentDefinitionResponse,
    AgentDefinitionUpdate,
    AgentDefinitionListQuery,
    IntentRouteCreate,
    IntentRouteResponse,
    IntentRouteUpdate,
    IntentRouteListQuery,
    PromptVersionCreate,
    PromptVersionResponse,
    PromptVersionUpdate,
    PromptVersionListQuery,
    RagAnalysisResponse,
)
from app.schemas.agent_management import (
    BatchUpdateStatusRequest,
    BatchDeleteRequest,
    BatchOperationResponse,
    AgentMetricsResponse,
    AgentConfigVersionResponse,
    CreateConfigVersionRequest,
    RollbackConfigRequest,
)
from app.schemas.common import PagedResponse, ResponseEnvelope
from app.schemas.user import CurrentUser
from app.services.agent_ops_service import AgentOpsService

router = APIRouter(prefix="/agent-ops", tags=["Agent Operations"])


def _build_service(current: CurrentUser, db) -> AgentOpsService:
    require_role("agent_ops", current.role)
    return AgentOpsService(db, current.org_id, current.user_id)


@router.get("/agents", response_model=ResponseEnvelope[PagedResponse[AgentDefinitionResponse]])
async def list_agents(
    query: AgentDefinitionListQuery = Depends(),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    items, total = await svc.list_agents(query)
    return ResponseEnvelope(
        data=PagedResponse(items=items, total=total, page=query.page, size=query.size)
    )


@router.post("/agents", response_model=ResponseEnvelope[AgentDefinitionResponse], status_code=201)
async def create_agent(
    body: AgentDefinitionCreate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    try:
        data = await svc.create_agent(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ResponseEnvelope(data=data)


@router.get("/agents/{id}", response_model=ResponseEnvelope[AgentDefinitionResponse])
async def get_agent(
    id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    return ResponseEnvelope(data=await svc.get_agent(id))


@router.put("/agents/{id}", response_model=ResponseEnvelope[AgentDefinitionResponse])
async def update_agent(
    id: str,
    body: AgentDefinitionUpdate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    try:
        data = await svc.update_agent(id, body)
    except ValueError as exc:
        raise HTTPException(
            status_code=404 if "not found" in str(exc).lower() else 400, detail=str(exc)
        ) from exc
    return ResponseEnvelope(data=data)


@router.delete("/agents/{id}", response_model=ResponseEnvelope[dict])
async def delete_agent(
    id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    try:
        await svc.delete_agent(id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ResponseEnvelope(data={"deleted": True})


@router.get("/prompts", response_model=ResponseEnvelope[PagedResponse[PromptVersionResponse]])
async def list_prompts(
    query: PromptVersionListQuery = Depends(),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    items, total = await svc.list_prompts(query)
    return ResponseEnvelope(
        data=PagedResponse(items=items, total=total, page=query.page, size=query.size)
    )


@router.post("/prompts", response_model=ResponseEnvelope[PromptVersionResponse], status_code=201)
async def create_prompt(
    body: PromptVersionCreate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    data = await svc.create_prompt(body)
    return ResponseEnvelope(data=data)


@router.get("/prompts/{id}", response_model=ResponseEnvelope[PromptVersionResponse])
async def get_prompt(
    id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    return ResponseEnvelope(data=await svc.get_prompt(id))


@router.put("/prompts/{id}", response_model=ResponseEnvelope[PromptVersionResponse])
async def update_prompt(
    id: str,
    body: PromptVersionUpdate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    try:
        data = await svc.update_prompt(id, body)
    except ValueError as exc:
        raise HTTPException(
            status_code=404 if "not found" in str(exc).lower() else 400, detail=str(exc)
        ) from exc
    return ResponseEnvelope(data=data)


@router.delete("/prompts/{id}", response_model=ResponseEnvelope[dict])
async def delete_prompt(
    id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    try:
        await svc.delete_prompt(id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ResponseEnvelope(data={"deleted": True})


@router.get("/routes", response_model=ResponseEnvelope[PagedResponse[IntentRouteResponse]])
async def list_routes(
    query: IntentRouteListQuery = Depends(),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    items, total = await svc.list_routes(query)
    return ResponseEnvelope(
        data=PagedResponse(items=items, total=total, page=query.page, size=query.size)
    )


@router.post("/routes", response_model=ResponseEnvelope[IntentRouteResponse], status_code=201)
async def create_route(
    body: IntentRouteCreate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    try:
        data = await svc.create_route(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ResponseEnvelope(data=data)


@router.get("/routes/{id}", response_model=ResponseEnvelope[IntentRouteResponse])
async def get_route(
    id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    return ResponseEnvelope(data=await svc.get_route(id))


@router.put("/routes/{id}", response_model=ResponseEnvelope[IntentRouteResponse])
async def update_route(
    id: str,
    body: IntentRouteUpdate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    try:
        data = await svc.update_route(id, body)
    except ValueError as exc:
        raise HTTPException(
            status_code=404 if "not found" in str(exc).lower() else 400, detail=str(exc)
        ) from exc
    return ResponseEnvelope(data=data)


@router.delete("/routes/{id}", response_model=ResponseEnvelope[dict])
async def delete_route(
    id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    try:
        await svc.delete_route(id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ResponseEnvelope(data={"deleted": True})


@router.get("/rag-analysis", response_model=ResponseEnvelope[RagAnalysisResponse])
async def get_rag_analysis(
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    return ResponseEnvelope(data=await svc.get_rag_analysis())


@router.post("/agents/batch/status", response_model=ResponseEnvelope[BatchOperationResponse])
async def batch_update_status(
    body: BatchUpdateStatusRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    try:
        result = await svc.batch_update_status(body.agent_ids, body.is_active)
        return ResponseEnvelope(data=BatchOperationResponse(**result))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/agents/batch/delete", response_model=ResponseEnvelope[BatchOperationResponse])
async def batch_delete(
    body: BatchDeleteRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    try:
        result = await svc.batch_delete(body.agent_ids)
        return ResponseEnvelope(data=BatchOperationResponse(**result))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/agents/{id}/metrics", response_model=ResponseEnvelope[AgentMetricsResponse])
async def get_agent_metrics(
    id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    try:
        metrics = await svc.get_agent_metrics(id)
        return ResponseEnvelope(data=AgentMetricsResponse(**metrics))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/agents/{id}/config-versions", response_model=ResponseEnvelope[dict], status_code=201)
async def create_config_version(
    id: str,
    body: CreateConfigVersionRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    try:
        config = body.model_dump(exclude_none=True)
        result = await svc.create_config_version(id, config)
        return ResponseEnvelope(data=result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/agents/{id}/config-versions", response_model=ResponseEnvelope[list[AgentConfigVersionResponse]])
async def list_config_versions(
    id: str,
    limit: int = Query(10, ge=1, le=100),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    try:
        versions = await svc.list_config_versions(id, limit)
        return ResponseEnvelope(data=versions)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/agents/{id}/config-versions/rollback", response_model=ResponseEnvelope[dict])
async def rollback_config(
    id: str,
    body: RollbackConfigRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    try:
        result = await svc.rollback_config(id, body.version)
        return ResponseEnvelope(data=result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
