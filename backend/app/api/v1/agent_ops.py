from fastapi import APIRouter, Depends, HTTPException, Query

from agent.topology_catalog import get_dspy_optimization_target, get_topology
from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import ROLE_ADMIN, normalize_role, require_role
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


def _use_global_scope(current: CurrentUser) -> bool:
    return normalize_role(current.role) == ROLE_ADMIN


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


@router.get("/agents/topology", response_model=ResponseEnvelope[dict])
async def get_agents_topology(
    subgraph_key: str = Query("all"),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    _build_service(current, db)
    return ResponseEnvelope(data=get_topology(subgraph_key, include_root=True))


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


@router.get("/runtime-agents", response_model=ResponseEnvelope[list[dict]])
async def get_runtime_agents(
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    data = await svc.get_runtime_agents()
    return ResponseEnvelope(data=data)


@router.post("/agents/import-runtime", response_model=ResponseEnvelope[AgentDefinitionResponse], status_code=201)
async def import_runtime_agent(
    body: dict,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    try:
        name = body.get("name")
        if not name:
            raise HTTPException(status_code=400, detail="name is required")
        data = await svc.import_runtime_agent(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ResponseEnvelope(data=data)


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


@router.get("/routing/strategy", response_model=ResponseEnvelope[dict])
async def get_routing_strategy(
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    return ResponseEnvelope(data=await svc.get_routing_strategy())


@router.get("/prompt-optimization/targets/{target_key}/runs", response_model=ResponseEnvelope[list[dict]])
async def list_prompt_optimization_runs(
    target_key: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    runs = await svc._optimization_run_repo.list_for_target(target_key)
    return ResponseEnvelope(data=[getattr(run, "__dict__", {}) for run in runs])


@router.put("/prompt-optimization/targets/{target_key}/config", response_model=ResponseEnvelope[dict])
async def update_prompt_optimization_config(
    target_key: str,
    body: dict,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    item = await svc._optimization_repo.update_config(target_key, body)
    if not item:
        raise HTTPException(status_code=404, detail="optimization target not found")
    return ResponseEnvelope(data=getattr(item, "__dict__", {}))


@router.post("/prompt-optimization/targets/{target_key}/compile", response_model=ResponseEnvelope[dict])
async def compile_prompt_optimization_target(
    target_key: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    run = await svc.compile_prompt_optimization_target(target_key)
    return ResponseEnvelope(data=getattr(run, "__dict__", {}))


@router.post("/prompt-optimization/targets/{target_key}/rollback", response_model=ResponseEnvelope[dict])
async def rollback_prompt_optimization_target(
    target_key: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    latest = await svc._optimization_run_repo.get_latest_completed(target_key)
    return ResponseEnvelope(data=getattr(latest, "__dict__", {}) if latest else {})


@router.get("/prompt-optimization/targets/{target_key}", response_model=ResponseEnvelope[dict])
async def get_prompt_optimization_target(
    target_key: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    target = await svc._optimization_repo.get_by_target_key(target_key)
    return ResponseEnvelope(data=getattr(target, "__dict__", {}) if target else (get_dspy_optimization_target(target_key) or {}))


@router.get("/rag-analysis", response_model=ResponseEnvelope[RagAnalysisResponse])
async def get_rag_analysis(
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    return ResponseEnvelope(data=await svc.get_rag_analysis(global_scope=_use_global_scope(current)))


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
