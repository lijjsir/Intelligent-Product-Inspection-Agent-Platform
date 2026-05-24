from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.v1.deps import get_current_user, get_db
from app.core.exceptions import NotFoundError
from app.core.permissions import require_role, ROLE_ADMIN
from app.schemas.agent_ops import (
    AgentDefinitionCreate,
    AgentDefinitionResponse,
    AgentDefinitionUpdate,
    AgentDefinitionListQuery,
    AgentDetailResponse,
    AgentRuntimeEventResponse,
    IntentRouteCreate,
    IntentRouteResponse,
    IntentRouteUpdate,
    IntentRouteListQuery,
    PauseRouteRequest,
    PromptVersionCreate,
    PromptVersionResponse,
    PromptVersionUpdate,
    PromptVersionListQuery,
    RagAnalysisResponse,
    RagTraceDetailResponse,
    AgentRuntimeOverviewResponse,
    AgentRuntimeInstanceResponse,
    AgentTopologyResponse,
    RoutingStrategyOverviewResponse,
    RoutingCurrentResponse,
    RouteSimulateRequest,
    RouteSimulateResponse,
    RouteEventItem,
    RoutingMetricsResponse,
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


def _build_service(current: CurrentUser, db, permission: str = "agent_ops_read") -> AgentOpsService:
    require_role(permission, current.role)
    return AgentOpsService(db, current.org_id, current.user_id)


def _use_global_scope(current: CurrentUser) -> bool:
    return ROLE_ADMIN in current.roles


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
    svc = _build_service(current, db, "agent_ops")
    try:
        data = await svc.create_agent(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ResponseEnvelope(data=data)


@router.get("/agents/topology", response_model=ResponseEnvelope[AgentTopologyResponse])
async def get_agents_topology(
    subgraph_key: str = Query(default="all"),
    mode: str = Query(default="design", description="design / runtime"),
    include_planned: bool = Query(default=True, description="whether planned subgraphs should be included"),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    topology = await svc.get_agents_topology(
        subgraph_key=subgraph_key,
        mode=mode,
        include_planned=include_planned,
    )
    return ResponseEnvelope(data=topology)


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
    svc = _build_service(current, db, "agent_ops")
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
    svc = _build_service(current, db, "agent_ops")
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
    svc = _build_service(current, db, "agent_ops")
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
    svc = _build_service(current, db, "agent_ops")
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
    svc = _build_service(current, db, "agent_ops")
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
    svc = _build_service(current, db, "agent_ops")
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


@router.get("/routing/strategy", response_model=ResponseEnvelope[RoutingStrategyOverviewResponse])
async def get_routing_strategy(
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    return ResponseEnvelope(data=await svc.get_routing_strategy())


@router.get("/routing/current", response_model=ResponseEnvelope[RoutingCurrentResponse])
async def get_routing_current(
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """获取当前系统真实路由策略视图（非配置版，展示真实路由结构）"""
    svc = _build_service(current, db)
    return ResponseEnvelope(data=await svc.get_routing_current())


@router.post("/routing/simulate", response_model=ResponseEnvelope[RouteSimulateResponse])
async def simulate_route(
    body: RouteSimulateRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """模拟路由 — 调用真实路由决策逻辑，展示路由结果，不执行Agent"""
    svc = _build_service(current, db)
    return ResponseEnvelope(data=await svc.simulate_route(body))


@router.get("/routing/events", response_model=ResponseEnvelope[list[RouteEventItem]])
async def get_routing_events(
    limit: int = Query(default=20, ge=1, le=100),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """获取最近路由事件"""
    svc = _build_service(current, db)
    return ResponseEnvelope(data=await svc.get_routing_events(limit=limit))


@router.get("/routing/metrics", response_model=ResponseEnvelope[RoutingMetricsResponse])
async def get_routing_metrics(
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """获取路由统计指标（最近24h）"""
    svc = _build_service(current, db)
    return ResponseEnvelope(data=await svc.get_routing_metrics())


@router.post("/routes", response_model=ResponseEnvelope[IntentRouteResponse], status_code=201)
async def create_route(
    body: IntentRouteCreate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db, "agent_ops")
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
    svc = _build_service(current, db, "agent_ops")
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
    svc = _build_service(current, db, "agent_ops")
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
    return ResponseEnvelope(data=await svc.get_rag_analysis(global_scope=_use_global_scope(current)))


@router.get("/rag-analysis/traces/{trace_id}", response_model=ResponseEnvelope[RagTraceDetailResponse])
async def get_rag_trace_detail(
    trace_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    try:
        data = await svc.get_rag_trace_detail(trace_id, global_scope=_use_global_scope(current))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ResponseEnvelope(data=data)


@router.get("/runtime/overview", response_model=ResponseEnvelope[AgentRuntimeOverviewResponse])
async def get_runtime_overview(
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    return ResponseEnvelope(data=await svc.get_runtime_overview())


@router.get("/runtime/agents", response_model=ResponseEnvelope[list[AgentRuntimeInstanceResponse]])
async def list_runtime_agents(
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    return ResponseEnvelope(data=await svc.list_runtime_agents())


@router.post("/runtime/agents/{runtime_key}/start", response_model=ResponseEnvelope[AgentRuntimeInstanceResponse])
async def start_runtime_agent(
    runtime_key: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db, "agent_ops")
    try:
        return ResponseEnvelope(data=await svc.set_runtime_status(runtime_key, status="running"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/runtime/agents/{runtime_key}/stop", response_model=ResponseEnvelope[AgentRuntimeInstanceResponse])
async def stop_runtime_agent(
    runtime_key: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db, "agent_ops")
    try:
        return ResponseEnvelope(data=await svc.set_runtime_status(runtime_key, status="stopped"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/routes/{id}/graph", response_model=ResponseEnvelope[AgentTopologyResponse])
async def get_route_graph(
    id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db)
    return ResponseEnvelope(data=await svc.get_route_graph(id))


@router.post("/runtime/agents/{runtime_key}/pause-route", response_model=ResponseEnvelope[AgentRuntimeInstanceResponse])
async def pause_agent_route(
    runtime_key: str,
    body: PauseRouteRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """暂停 Agent 路由 — 该 Agent 不再接收新请求"""
    svc = _build_service(current, db, "agent_ops")
    return ResponseEnvelope(data=await svc.pause_route(runtime_key, body.reason))


@router.post("/runtime/agents/{runtime_key}/resume-route", response_model=ResponseEnvelope[AgentRuntimeInstanceResponse])
async def resume_agent_route(
    runtime_key: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """恢复 Agent 路由 — 该 Agent 重新接收请求"""
    svc = _build_service(current, db, "agent_ops")
    return ResponseEnvelope(data=await svc.resume_route(runtime_key))


@router.get("/agents/{agent_id}/detail", response_model=ResponseEnvelope[AgentDetailResponse])
async def get_agent_detail(
    agent_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """获取 Agent 完整详情（含绑定资源、操作记录）"""
    svc = _build_service(current, db)
    return ResponseEnvelope(data=await svc.get_agent_detail(agent_id))


@router.get("/runtime/events", response_model=ResponseEnvelope[list[AgentRuntimeEventResponse]])
async def list_runtime_events(
    agent_id: str = Query(..., description="Agent ID"),
    limit: int = Query(default=20, ge=1, le=100),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """查询 Agent 运行态操作事件日志"""
    svc = _build_service(current, db)
    return ResponseEnvelope(data=await svc.list_runtime_events(agent_id, limit=limit))


@router.post("/agents/batch/status", response_model=ResponseEnvelope[BatchOperationResponse])
async def batch_update_status(
    body: BatchUpdateStatusRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _build_service(current, db, "agent_ops")
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
    svc = _build_service(current, db, "agent_ops")
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
    svc = _build_service(current, db, "agent_ops")
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
    svc = _build_service(current, db, "agent_ops")
    try:
        result = await svc.rollback_config(id, body.version)
        return ResponseEnvelope(data=result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
