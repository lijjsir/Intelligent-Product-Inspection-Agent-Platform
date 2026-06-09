"""Memory governance API endpoints.

POST /api/v1/memory/candidates         - write candidate memory
POST /api/v1/memory/search             - controlled retrieval
POST /api/v1/memory/contamination/graph - propagation graph
POST /api/v1/memory/rollback           - execute rollback
POST /api/v1/memory/evaluation/replay  - recovery verification
PUT  /api/v1/memory/policies/{key}     - policy configuration
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import require_role
from app.schemas.common import ResponseEnvelope
from app.schemas.memory import (
    ConflictResolveRequest,
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
)
from app.schemas.user import CurrentUser
from app.services.memory_service import MemoryService
from app.services.memory_vector_service import MemoryVectorService, MemoryVectorServiceError
from app.services.memory_governance_service import (
    MemoryPropagationService,
    MemoryRollbackService,
    MemoryEvaluationService,
)

router = APIRouter()


def _get_memory_service(db, org_id: str, vector_svc: MemoryVectorService | None = None) -> MemoryService:
    return MemoryService(db, org_id, vector_service=vector_svc)


def _build_vector_service(
    org_id: str,
    user_id: str | None = None,
    trace_id: str | None = None,
) -> MemoryVectorService:
    """Build MemoryVectorService with a real Embedder factory."""
    from agent.rag.embedder import Embedder

    async def embedder_factory(text: str) -> list[float]:
        embedder = Embedder(
            org_id=org_id,
            user_id=user_id,
            trace_id=trace_id,
            allow_pseudo_fallback=False,
        )
        return await embedder.embed(text)

    return MemoryVectorService(
        embedder_factory=embedder_factory,
        org_id=org_id,
        user_id=user_id,
        trace_id=trace_id,
    )


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

    if body.org_id and body.org_id != current.org_id:
        raise HTTPException(status_code=403, detail={
            "error_code": "SHARED_MEMORY_SCOPE_FORBIDDEN",
            "message": "org_id in request does not match current user",
            "trace_id": body.trace_id,
        })

    org_id = current.org_id
    if not org_id:
        raise HTTPException(status_code=400, detail={
            "error_code": "SHARED_MEMORY_INVALID_REQUEST",
            "message": "missing org_id",
            "trace_id": body.trace_id,
        })

    try:
        vector_svc = _build_vector_service(org_id, current.user_id, body.trace_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail={
            "error_code": "SHARED_MEMORY_EMBEDDER_UNAVAILABLE",
            "message": f"Embedding service unavailable: {exc}",
            "trace_id": body.trace_id,
        })

    service = _get_memory_service(db, org_id, vector_svc)
    try:
        resp = await service.write_candidate(body)
    except Exception as exc:
        raise HTTPException(status_code=500, detail={
            "error_code": "SHARED_MEMORY_WRITE_FAILED",
            "message": f"Memory write failed: {exc}",
            "trace_id": body.trace_id,
        })

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

    if body.org_id and body.org_id != current.org_id:
        raise HTTPException(status_code=403, detail={
            "error_code": "SHARED_MEMORY_SCOPE_FORBIDDEN",
            "message": "org_id in request does not match current user",
            "trace_id": body.trace_id,
        })

    org_id = current.org_id
    if not org_id:
        raise HTTPException(status_code=400, detail={
            "error_code": "SHARED_MEMORY_INVALID_REQUEST",
            "message": "missing org_id",
            "trace_id": body.trace_id,
        })

    try:
        vector_svc = _build_vector_service(org_id, current.user_id, body.trace_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail={
            "error_code": "SHARED_MEMORY_EMBEDDER_UNAVAILABLE",
            "message": f"Embedding service unavailable: {exc}",
            "trace_id": body.trace_id,
        })

    service = _get_memory_service(db, org_id, vector_svc)
    try:
        resp = await service.search(body)
    except MemoryVectorServiceError as exc:
        raise HTTPException(status_code=503, detail={
            "error_code": "SHARED_MEMORY_VECTOR_SEARCH_FAILED",
            "message": str(exc),
            "trace_id": body.trace_id,
        })
    except Exception as exc:
        raise HTTPException(status_code=500, detail={
            "error_code": "SHARED_MEMORY_SEARCH_FAILED",
            "message": f"Memory search failed: {exc}",
            "trace_id": body.trace_id,
        })

    return ResponseEnvelope(data=resp)


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

    vector_svc = _build_vector_service(org_id, current.user_id, body.trace_id)
    svc = MemoryRollbackService(db, org_id, vector_svc)
    try:
        resp = await svc.plan_rollback(
            root_memory_id=body.root_memory_id,
            operator_id=body.operator_id,
            operator_role=current.role,
            trace_id=body.trace_id,
            action=body.rollback_action,
            target_memory_ids=body.target_memory_ids,
            reason=body.reason,
            require_human_review=body.require_human_review,
            propagation_graph=body.propagation_graph,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={
            "error_code": "SHARED_MEMORY_INVALID_REQUEST",
            "message": str(exc),
            "trace_id": body.trace_id,
        }) from exc
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
        config=body.config,
        status=body.status,
        version=policy.version,
        updated_at=policy.created_at,
    ))


@router.get("/policies")
async def list_policies(
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """List memory policies for the current org."""
    require_role("memory_governance", current.role)
    from app.repositories.memory_repo import MemoryPolicyRepository

    repo = MemoryPolicyRepository(db, current.org_id)
    policies = await repo.list_all()
    return ResponseEnvelope(data=[
        {
            "policy_key": p.policy_key,
            "policy_type": p.policy_type,
            "status": p.status,
            "version": p.version,
        }
        for p in policies
    ])


# ---------------------------------------------------------------
# Conflict Arbitration (P2 — written for future use)
# ---------------------------------------------------------------

@router.get("/conflicts")
async def list_conflicts(
    product_line: str | None = Query(default=None),
    memory_type: str | None = Query(default=None),
    status: str | None = Query(default="contested"),
    limit: int = Query(default=50, ge=1, le=200),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """List contested memories and their conflict edges."""
    require_role("memory_governance", current.role)

    from app.repositories.memory_repo import MemoryDependencyRepository, MemoryItemRepository
    item_repo = MemoryItemRepository(db, current.org_id)
    dep_repo = MemoryDependencyRepository(db, current.org_id)

    items = await item_repo.list_by_org(
        status=status or "contested",
        memory_type=memory_type,
        limit=limit,
    )

    conflicts: list[dict] = []
    for item in items:
        edges = await dep_repo.list_by_edge_type(
            item.memory_id,
            ["conflicts_with"],
            direction="source",
        )
        for edge in edges:
            target = await item_repo.get_by_memory_id(edge.target_memory_id)
            if target:
                conflicts.append({
                    "edge_id": edge.id,
                    "source_memory": {
                        "memory_id": item.memory_id,
                        "summary": item.content_summary or "",
                        "memory_type": item.memory_type,
                        "confidence": float(item.confidence) if item.confidence else None,
                        "trust_score": float(item.trust_score) if item.trust_score else None,
                    },
                    "target_memory": {
                        "memory_id": target.memory_id,
                        "summary": target.content_summary or "",
                        "memory_type": target.memory_type,
                        "confidence": float(target.confidence) if target.confidence else None,
                        "trust_score": float(target.trust_score) if target.trust_score else None,
                    },
                    "created_at": edge.created_at.isoformat() if edge.created_at else None,
                })

    return ResponseEnvelope(data={"conflicts": conflicts[:limit], "total": len(conflicts)})


@router.get("/conflicts/{memory_id}")
async def get_conflict_detail(
    memory_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """Get all conflict relationships for a specific memory."""
    require_role("memory_governance", current.role)

    from app.repositories.memory_repo import MemoryDependencyRepository, MemoryItemRepository
    item_repo = MemoryItemRepository(db, current.org_id)
    dep_repo = MemoryDependencyRepository(db, current.org_id)

    item = await item_repo.get_by_memory_id(memory_id)
    if not item:
        raise HTTPException(status_code=404, detail={
            "error_code": "SHARED_MEMORY_NOT_FOUND",
            "message": f"Memory {memory_id} not found",
            "trace_id": None,
        })

    edges = await dep_repo.list_by_edge_type(memory_id, ["conflicts_with"], direction="source")
    conflicts = []
    for edge in edges:
        target = await item_repo.get_by_memory_id(edge.target_memory_id)
        if target:
            conflicts.append({
                "edge_id": edge.id,
                "target": {
                    "memory_id": target.memory_id,
                    "summary": target.content_summary or "",
                    "memory_type": target.memory_type,
                    "confidence": float(target.confidence) if target.confidence else None,
                    "trust_score": float(target.trust_score) if target.trust_score else None,
                    "status": target.status,
                },
                "created_at": edge.created_at.isoformat() if edge.created_at else None,
            })

    return ResponseEnvelope(data={
        "memory": {
            "memory_id": item.memory_id,
            "summary": item.content_summary or "",
            "memory_type": item.memory_type,
            "status": item.status,
            "confidence": float(item.confidence) if item.confidence else None,
            "trust_score": float(item.trust_score) if item.trust_score else None,
        },
        "conflicts": conflicts,
    })


@router.post("/conflicts/{memory_id}/resolve")
async def resolve_conflict(
    memory_id: str,
    body: ConflictResolveRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """Resolve a conflict: keep_A / keep_B / merge / dismiss."""
    require_role("memory_governance", current.role)

    from app.repositories.memory_repo import MemoryDependencyRepository, MemoryItemRepository
    item_repo = MemoryItemRepository(db, current.org_id)
    dep_repo = MemoryDependencyRepository(db, current.org_id)

    item = await item_repo.get_by_memory_id(memory_id)
    if not item:
        raise HTTPException(status_code=404, detail={
            "error_code": "SHARED_MEMORY_NOT_FOUND",
            "message": f"Memory {memory_id} not found",
            "trace_id": None,
        })

    edges = await dep_repo.list_by_edge_type(memory_id, ["conflicts_with"], direction="source")
    if not edges:
        raise HTTPException(status_code=404, detail={
            "error_code": "SHARED_MEMORY_NOT_FOUND",
            "message": "No active conflicts found",
            "trace_id": None,
        })

    target_id = edges[0].target_memory_id
    target = await item_repo.get_by_memory_id(target_id)

    merged_id = None
    if body.action == "keep_A":
        await item_repo.update_status(memory_id, "active")
        if target:
            await item_repo.update_status(target_id, "isolated")
    elif body.action == "keep_B":
        if target:
            await item_repo.update_status(target_id, "active")
        await item_repo.update_status(memory_id, "isolated")
    elif body.action == "dismiss":
        await item_repo.update_status(memory_id, "isolated")
        if target:
            await item_repo.update_status(target_id, "isolated")
    elif body.action == "merge":
        await dep_repo.soft_delete_by_memory(memory_id)
        merged_id = f"mem_{uuid.uuid4().hex[:12]}"

    await dep_repo.soft_delete_by_memory(memory_id)

    return ResponseEnvelope(data={
        "resolution": body.action,
        "source_memory_status": "active" if body.action == "keep_A" else "isolated",
        "target_memory_status": "active" if body.action == "keep_B" else "isolated",
        "merged_memory_id": merged_id,
    })
