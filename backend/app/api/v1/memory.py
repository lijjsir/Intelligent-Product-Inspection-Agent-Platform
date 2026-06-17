"""Memory governance API endpoints.

POST /api/v1/memory/candidates         - write candidate memory
POST /api/v1/memory/search             - controlled retrieval
POST /api/v1/memory/contamination/graph - propagation graph
POST /api/v1/memory/rollback           - execute rollback
POST /api/v1/memory/evaluation/replay  - recovery verification
PUT  /api/v1/memory/policies/{key}     - policy configuration
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import require_role
from app.schemas.common import ResponseEnvelope
from app.schemas.memory import (
    MemoryEvaluationRequest,
    MemoryEvaluationResponse,
    MemoryPolicyResponse,
    MemoryPolicyUpsert,
    MemoryPropagationRequest,
    MemoryPropagationResponse,
    MemoryRollbackRequest,
    MemoryRollbackResponse,
    MemorySearchRequest,
    MemorySearchResponse,
    MemoryWriteRequest,
    MemoryWriteResponse,
    RetrievalGatewayRequest,
    RetrievalGatewayResponse,
    Workspace,
)
from app.schemas.user import CurrentUser
from app.services.retrieval_gateway_service import RetrievalGatewayService
from app.services.memory_service import MemoryService
from app.services.memory_vector_service import MemoryVectorService
from app.services.memory_governance_service import (
    MemoryPropagationService,
    MemoryRollbackService,
    MemoryEvaluationService,
)

router = APIRouter()


def _get_memory_service(db, org_id: str, vector_svc: MemoryVectorService | None = None) -> MemoryService:
    return MemoryService(db, org_id, vector_service=vector_svc)


# ---------------------------------------------------------------
# Write candidate memory
# ---------------------------------------------------------------

@router.post("/candidates", response_model=ResponseEnvelope[MemoryWriteResponse])
async def write_candidate(
    body: MemoryWriteRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """Submit a candidate memory through the write gate."""
    require_role("memory_governance", current.role)
    org_id = body.org_id or current.org_id
    if not org_id:
        raise HTTPException(status_code=400, detail="missing org_id")

    vector_svc = MemoryVectorService()
    service = _get_memory_service(db, org_id, vector_svc)
    resp = await service.write_candidate(body)
    return ResponseEnvelope(data=resp)


# ---------------------------------------------------------------
# Search / retrieval
# ---------------------------------------------------------------

@router.post("/search", response_model=ResponseEnvelope[MemorySearchResponse])
async def search_memory(
    body: MemorySearchRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """Controlled retrieval with MySQL permission filter -> Qdrant semantic recall -> verify -> rerank."""
    require_role("memory_governance", current.role)
    org_id = body.org_id or current.org_id
    if not org_id:
        raise HTTPException(status_code=400, detail="missing org_id")

    vector_svc = MemoryVectorService()
    service = _get_memory_service(db, org_id, vector_svc)
    resp = await service.search(body)
    return ResponseEnvelope(data=resp)


@router.post("/retrieval", response_model=ResponseEnvelope[RetrievalGatewayResponse])
async def retrieval_gateway(
    body: RetrievalGatewayRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """Unified retrieval gateway: document RAG and memory RAG stay separate, but return together."""
    require_role("memory_governance", current.role)
    org_id = body.org_id or current.org_id
    if not org_id:
        raise HTTPException(status_code=400, detail="missing org_id")

    request = body.model_copy(update={
        "org_id": org_id,
        "user_id": body.user_id or current.user_id,
    })
    service = RetrievalGatewayService(db, org_id=org_id, user_id=current.user_id)
    resp = await service.search(request)
    return ResponseEnvelope(data=resp)


@router.get("/export")
async def export_memory_training_data(
    status: str | None = Query(default="active"),
    workspace: str | None = Query(default=None),
    memory_type: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """Export governed memory rows from MySQL for offline agent evaluation/training datasets."""
    require_role("memory_governance", current.role)
    from app.repositories.memory_repo import MemoryItemRepository

    repo = MemoryItemRepository(db, current.org_id)
    rows = await repo.list_by_org(
        status=status,
        workspace=workspace,
        memory_type=memory_type,
        limit=limit,
        offset=offset,
    )
    return ResponseEnvelope(data={
        "source": "memory_items",
        "org_id": current.org_id,
        "count": len(rows),
        "items": [
            {
                "memory_id": row.memory_id,
                "workspace": row.workspace,
                "memory_type": row.memory_type,
                "status": row.status,
                "scope": row.scope_json or {},
                "summary": row.content_summary or "",
                "content": row.content_json or {},
                "evidence_pointers": row.evidence_pointers or {},
                "source_event_ids": row.source_event_ids or [],
                "trust_score": float(row.trust_score) if row.trust_score is not None else None,
                "confidence": float(row.confidence) if row.confidence is not None else None,
                "usage_policy": row.usage_policy,
                "ttl_policy": row.ttl_policy,
                "privacy_level": row.privacy_level,
                "trace_id": row.trace_id,
                "created_by_type": row.created_by_type,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            }
            for row in rows
        ],
    })


# ---------------------------------------------------------------
# Events
# ---------------------------------------------------------------

@router.get("/events")
async def list_events(
    memory_id: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    trace_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """List memory events for the current org."""
    require_role("memory_governance", current.role)
    service = _get_memory_service(db, current.org_id)
    events = await service.get_events(
        memory_id=memory_id,
        event_type=event_type,
        trace_id=trace_id,
        limit=limit,
    )
    return ResponseEnvelope(data=[
        {
            "event_id": e.event_id,
            "event_type": e.event_type,
            "memory_id": e.memory_id,
            "trace_id": e.trace_id,
            "source_kind": e.source_kind,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in events
    ])


# ---------------------------------------------------------------
# Contamination propagation graph
# ---------------------------------------------------------------

@router.post("/contamination/graph", response_model=ResponseEnvelope[MemoryPropagationResponse])
async def build_propagation_graph(
    body: MemoryPropagationRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """Build contamination propagation subgraph from dependency edges."""
    require_role("memory_governance", current.role)
    org_id = body.org_id or current.org_id
    if not org_id:
        raise HTTPException(status_code=400, detail="missing org_id")
    if body.workspace != "governance":
        raise HTTPException(status_code=403, detail="requires governance workspace")

    svc = MemoryPropagationService(db, org_id)
    resp = await svc.build_propagation_graph(
        root_memory_id=body.root_memory_id,
        max_depth=body.max_depth,
        include_edge_types=body.include_edge_types,
    )
    return ResponseEnvelope(data=resp)


# ---------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------

@router.post("/rollback", response_model=ResponseEnvelope[MemoryRollbackResponse])
async def execute_rollback(
    body: MemoryRollbackRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """Execute a rollback action on contaminated memories."""
    require_role("memory_governance", current.role)
    org_id = body.org_id or current.org_id
    if not org_id:
        raise HTTPException(status_code=400, detail="missing org_id")
    if body.workspace not in (Workspace.OPS, Workspace.GOVERNANCE):
        raise HTTPException(status_code=403, detail="requires ops or governance workspace")

    vector_svc = MemoryVectorService()
    svc = MemoryRollbackService(db, org_id, vector_svc)
    resp = await svc.execute_rollback(
        root_memory_id=body.root_memory_id,
        operator_id=body.operator_id,
        operator_role=current.role,
        workspace=body.workspace.value,
        trace_id=body.trace_id,
        action=body.rollback_action,
        target_memory_ids=body.target_memory_ids,
        reason=body.reason,
        require_human_review=body.require_human_review,
        propagation_graph=body.propagation_graph,
    )
    return ResponseEnvelope(data=resp)


# ---------------------------------------------------------------
# Recovery evaluation
# ---------------------------------------------------------------

@router.post("/evaluation/replay", response_model=ResponseEnvelope[MemoryEvaluationResponse])
async def replay_evaluation(
    body: MemoryEvaluationRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """Run recovery verification after a rollback."""
    require_role("memory_governance", current.role)
    org_id = body.org_id or current.org_id
    if not org_id:
        raise HTTPException(status_code=400, detail="missing org_id")

    svc = MemoryEvaluationService(db, org_id)
    resp = await svc.evaluate_recovery(
        rollback_id=body.rollback_id,
        task_id=body.task_id,
        trace_id=body.trace_id,
        scenario=body.scenario,
    )
    return ResponseEnvelope(data=resp)


# ---------------------------------------------------------------
# Policy configuration
# ---------------------------------------------------------------

@router.put("/policies/{policy_key}", response_model=ResponseEnvelope[MemoryPolicyResponse])
async def upsert_policy(
    policy_key: str,
    body: MemoryPolicyUpsert,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """Upsert a memory governance policy."""
    require_role("memory_policy", current.role)
    from app.repositories.memory_repo import MemoryPolicyRepository
    from app.core.ids import uuid7
    from app.models.memory import MemoryPolicy

    repo = MemoryPolicyRepository(db, current.org_id)
    existing = await repo.get_active(policy_key, body.policy_type.value)
    if existing:
        new_version = existing.version + 1
        policy = MemoryPolicy(
            id=str(uuid7()),
            org_id=current.org_id,
            workspace=body.workspace.value,
            policy_key=policy_key,
            policy_type=body.policy_type.value,
            config_json=body.config,
            status=body.status,
            version=new_version,
            updated_by=current.user_id,
        )
    else:
        policy = MemoryPolicy(
            id=str(uuid7()),
            org_id=current.org_id,
            workspace=body.workspace.value,
            policy_key=policy_key,
            policy_type=body.policy_type.value,
            config_json=body.config,
            status=body.status,
            version=1,
            updated_by=current.user_id,
        )
    await repo.create(policy)
    return ResponseEnvelope(data=MemoryPolicyResponse(
        policy_key=policy_key,
        policy_type=body.policy_type,
        workspace=body.workspace,
        config=body.config,
        status=body.status,
        version=policy.version,
        updated_at=policy.created_at,
    ))


@router.get("/policies")
async def list_policies(
    workspace: str | None = Query(default=None),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """List memory policies for the current org."""
    require_role("memory_governance", current.role)
    from app.repositories.memory_repo import MemoryPolicyRepository

    repo = MemoryPolicyRepository(db, current.org_id)
    policies = await repo.list_by_workspace(workspace or "ops")
    return ResponseEnvelope(data=[
        {
            "policy_key": p.policy_key,
            "policy_type": p.policy_type,
            "workspace": p.workspace,
            "status": p.status,
            "version": p.version,
        }
        for p in policies
    ])
