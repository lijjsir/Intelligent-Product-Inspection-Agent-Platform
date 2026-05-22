from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import require_role
from app.schemas.common import ResponseEnvelope
from app.schemas.gpu_infra import (
    GpuComputeNodeCreateRequest,
    GpuComputeNodeResponse,
    GpuComputeNodeUpdateRequest,
    GpuNodeConnectionTestResponse,
    GpuNodeHeartbeatRequest,
    GpuNodeMetricRefreshResponse,
)
from app.schemas.user import CurrentUser
from app.services.gpu_infra_service import GpuNodeService


router = APIRouter(prefix="/gpu-nodes", tags=["gpu-nodes"])


def _svc(current: CurrentUser, db):
    require_role("gpu_infra", current.role)
    return GpuNodeService(db, current.org_id, current.user_id)


@router.get("", response_model=ResponseEnvelope[list[GpuComputeNodeResponse]])
async def list_gpu_nodes(current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).list_nodes())


@router.get("/{node_id}", response_model=ResponseEnvelope[GpuComputeNodeResponse])
async def get_gpu_node(node_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).get_node(node_id))


@router.post("", response_model=ResponseEnvelope[GpuComputeNodeResponse], status_code=status.HTTP_201_CREATED)
async def create_gpu_node(
    payload: GpuComputeNodeCreateRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    return ResponseEnvelope(data=await _svc(current, db).create_node(payload))


@router.patch("/{node_id}", response_model=ResponseEnvelope[GpuComputeNodeResponse])
async def update_gpu_node(
    node_id: str,
    payload: GpuComputeNodeUpdateRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    return ResponseEnvelope(data=await _svc(current, db).update_node(node_id, payload))


@router.delete("/{node_id}", response_model=ResponseEnvelope[dict[str, bool]])
async def delete_gpu_node(node_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    await _svc(current, db).delete_node(node_id)
    return ResponseEnvelope(data={"deleted": True})


@router.post("/{node_id}/test-connection", response_model=ResponseEnvelope[GpuNodeConnectionTestResponse])
async def test_gpu_node_connection(node_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    success, message = await _svc(current, db).test_connection(node_id)
    return ResponseEnvelope(data=GpuNodeConnectionTestResponse(success=success, message=message))


@router.post("/{node_id}/heartbeat", response_model=ResponseEnvelope[GpuComputeNodeResponse])
async def heartbeat_gpu_node(
    node_id: str,
    payload: GpuNodeHeartbeatRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    return ResponseEnvelope(data=await _svc(current, db).heartbeat(node_id, payload))


@router.post("/{node_id}/refresh-metrics", response_model=ResponseEnvelope[GpuNodeMetricRefreshResponse])
async def refresh_gpu_node_metrics(node_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    node, metrics = await _svc(current, db).refresh_metrics(node_id)
    return ResponseEnvelope(data=GpuNodeMetricRefreshResponse(node=node, metrics=metrics))


@router.post("/{node_id}/enable", response_model=ResponseEnvelope[GpuComputeNodeResponse])
async def enable_gpu_node(node_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).set_node_enabled(node_id, enabled=True))


@router.post("/{node_id}/disable", response_model=ResponseEnvelope[GpuComputeNodeResponse])
async def disable_gpu_node(node_id: str, current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    return ResponseEnvelope(data=await _svc(current, db).set_node_enabled(node_id, enabled=False))
