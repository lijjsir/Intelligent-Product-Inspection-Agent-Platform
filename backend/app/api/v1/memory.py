"""Memory governance API endpoints.

POST /api/v1/memory/candidates         - write candidate memory
POST /api/v1/memory/search             - controlled retrieval
POST /api/v1/memory/contamination/graph - propagation graph
POST /api/v1/memory/rollback           - execute rollback
POST /api/v1/memory/evaluation/replay  - recovery verification
PUT  /api/v1/memory/policies/{key}     - policy configuration
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.v1.deps import get_current_user, get_db
from app.api.v1.memory_helpers import (
    build_vector_service,
    embedder_unavailable_error,
    get_memory_service,
    invalid_memory_request,
    memory_api_error,
    memory_operation_error,
    missing_org_error,
    not_found_error,
    require_uuid,
    scope_forbidden_error,
    validate_optional_uuid,
    vector_error,
)
from app.core.exceptions import MemoryVectorServiceError as AppMemoryVectorServiceError
from app.core.permissions import require_role
from app.schemas.common import ResponseEnvelope
from app.schemas.memory import (
    CandidateListItem,
    CandidateSupportCreate,
    ConflictCheckInput,
    ConflictCheckOutput,
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
    MemoryStatus,
    MemoryWriteRequest,
    MemoryWriteResponse,
    PromotionEvaluationResponse,
    SearchWithConflictGuardRequest,
    SearchWithConflictGuardResponse,
)
from app.schemas.user import CurrentUser
from app.services.memory_vector_service import (
    CANDIDATE_MEMORY_COLLECTION,
    MemoryVectorServiceError,
)
from app.services.memory_governance_service import (
    MemoryPropagationService,
    MemoryRollbackService,
    MemoryEvaluationService,
)
from app.services.retrieval_conflict_guard import RetrievalConflictGuard

router = APIRouter()


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
        raise scope_forbidden_error(body.trace_id)

    org_id = current.org_id
    if not org_id:
        raise missing_org_error(body.trace_id)
    require_uuid(current.user_id, "current.user_id", body.trace_id)
    validate_optional_uuid(body.user_id, "user_id", body.trace_id)

    try:
        vector_svc = build_vector_service(org_id, current.user_id, body.trace_id)
    except Exception as exc:
        raise embedder_unavailable_error(exc, body.trace_id, "candidate_write") from exc

    candidate_vector_svc = build_vector_service(
        org_id,
        current.user_id,
        body.trace_id,
        collection=CANDIDATE_MEMORY_COLLECTION,
    )
    service = get_memory_service(db, org_id, vector_svc, candidate_vector_svc, trace_id=body.trace_id)
    try:
        resp = await service.write_candidate(body)
    except MemoryVectorServiceError as exc:
        raise vector_error(exc, body.trace_id, "Memory write")
    except Exception as exc:
        raise memory_operation_error(exc, body.trace_id, "Memory write")

    await db.commit()
    return ResponseEnvelope(data=resp)


@router.get("/candidates", response_model=ResponseEnvelope[list[CandidateListItem]])
async def list_candidates(
    status: str = Query(default=MemoryStatus.CANDIDATE.value),
    memory_type: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """List candidate memories for governance review."""
    require_role("memory_governance", current.role)
    service = get_memory_service(db, current.org_id)
    resp = await service.list_candidates(
        status=status,
        memory_type=memory_type,
        user_id=user_id,
        limit=limit,
        offset=offset,
    )
    return ResponseEnvelope(data=resp)


@router.post("/candidates/{memory_id}/support", response_model=ResponseEnvelope[PromotionEvaluationResponse | None])
async def support_candidate(
    memory_id: str,
    body: CandidateSupportCreate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """Append support evidence and evaluate promotion."""
    require_role("memory_governance", current.role)
    vector_svc = build_vector_service(current.org_id, current.user_id, body.trace_id)
    candidate_vector_svc = build_vector_service(
        current.org_id,
        current.user_id,
        body.trace_id,
        collection=CANDIDATE_MEMORY_COLLECTION,
    )
    service = get_memory_service(db, current.org_id, vector_svc, candidate_vector_svc, trace_id=body.trace_id)
    try:
        resp = await service.add_candidate_support(memory_id, body)
    except MemoryVectorServiceError as exc:
        raise vector_error(exc, body.trace_id, "Candidate support")
    except Exception as exc:
        raise memory_operation_error(exc, body.trace_id, "Candidate support")
    await db.commit()
    return ResponseEnvelope(data=resp)


@router.post("/candidates/{memory_id}/approve", response_model=ResponseEnvelope[PromotionEvaluationResponse])
async def approve_candidate(
    memory_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """Human approval: candidate can promote immediately if not blocked."""
    require_role("memory_governance", current.role)
    vector_svc = build_vector_service(current.org_id, current.user_id, None)
    candidate_vector_svc = build_vector_service(
        current.org_id,
        current.user_id,
        None,
        collection=CANDIDATE_MEMORY_COLLECTION,
    )
    trace_id = f"memory-approve-{memory_id}"
    service = get_memory_service(db, current.org_id, vector_svc, candidate_vector_svc, trace_id=trace_id)
    try:
        resp = await service.approve_candidate(
            memory_id,
            reviewer_id=current.user_id,
            trace_id=trace_id,
        )
    except MemoryVectorServiceError as exc:
        raise vector_error(exc, trace_id, "Candidate approval")
    except Exception as exc:
        raise memory_operation_error(exc, trace_id, "Candidate approval")
    await db.commit()
    return ResponseEnvelope(data=resp)


@router.post("/candidates/{memory_id}/reject", response_model=ResponseEnvelope[PromotionEvaluationResponse])
async def reject_candidate(
    memory_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """Reject a candidate and disable it."""
    require_role("memory_governance", current.role)
    trace_id = f"memory-reject-{memory_id}"
    service = get_memory_service(db, current.org_id, trace_id=trace_id)
    try:
        resp = await service.reject_candidate(
            memory_id,
            reviewer_id=current.user_id,
            trace_id=trace_id,
            reason="manual_reject",
        )
    except Exception as exc:
        raise memory_operation_error(exc, trace_id, "Candidate rejection")
    await db.commit()
    return ResponseEnvelope(data=resp)


@router.post("/candidates/{memory_id}/isolate", response_model=ResponseEnvelope[PromotionEvaluationResponse])
async def isolate_candidate(
    memory_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """Isolate a candidate from promotion and retrieval."""
    require_role("memory_governance", current.role)
    candidate_vector_svc = build_vector_service(
        current.org_id,
        current.user_id,
        None,
        collection=CANDIDATE_MEMORY_COLLECTION,
    )
    trace_id = f"memory-isolate-{memory_id}"
    service = get_memory_service(db, current.org_id, candidate_vector_svc=candidate_vector_svc, trace_id=trace_id)
    try:
        resp = await service.isolate_candidate(memory_id, trace_id=trace_id)
    except MemoryVectorServiceError as exc:
        raise vector_error(exc, trace_id, "Candidate isolation")
    except Exception as exc:
        raise memory_operation_error(exc, trace_id, "Candidate isolation")
    await db.commit()
    return ResponseEnvelope(data=resp)


@router.post("/candidates/{memory_id}/contest", response_model=ResponseEnvelope[PromotionEvaluationResponse])
async def contest_candidate(
    memory_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """Mark a candidate as contested."""
    require_role("memory_governance", current.role)
    trace_id = f"memory-contest-{memory_id}"
    service = get_memory_service(db, current.org_id, trace_id=trace_id)
    try:
        resp = await service.contest_candidate(memory_id, trace_id=trace_id)
    except Exception as exc:
        raise memory_operation_error(exc, trace_id, "Candidate contest")
    await db.commit()
    return ResponseEnvelope(data=resp)


@router.post("/candidates/{memory_id}/evaluate-promotion", response_model=ResponseEnvelope[PromotionEvaluationResponse])
async def evaluate_candidate_promotion(
    memory_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """Evaluate one candidate for promotion."""
    require_role("memory_governance", current.role)
    vector_svc = build_vector_service(current.org_id, current.user_id, None)
    candidate_vector_svc = build_vector_service(
        current.org_id,
        current.user_id,
        None,
        collection=CANDIDATE_MEMORY_COLLECTION,
    )
    trace_id = f"memory-evaluate-{memory_id}"
    service = get_memory_service(db, current.org_id, vector_svc, candidate_vector_svc, trace_id=trace_id)
    try:
        resp = await service.evaluate_candidate_promotion(memory_id)
    except MemoryVectorServiceError as exc:
        raise vector_error(exc, trace_id, "Candidate promotion evaluation")
    except Exception as exc:
        raise memory_operation_error(exc, trace_id, "Candidate promotion evaluation")
    await db.commit()
    return ResponseEnvelope(data=resp)


@router.post("/candidates/evaluate-batch", response_model=ResponseEnvelope[list[PromotionEvaluationResponse]])
async def evaluate_candidate_batch(
    limit: int = Query(default=100, ge=1, le=500),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """Evaluate recent candidates for promotion."""
    require_role("memory_governance", current.role)
    vector_svc = build_vector_service(current.org_id, current.user_id, None)
    candidate_vector_svc = build_vector_service(
        current.org_id,
        current.user_id,
        None,
        collection=CANDIDATE_MEMORY_COLLECTION,
    )
    trace_id = "memory-evaluate-batch"
    service = get_memory_service(db, current.org_id, vector_svc, candidate_vector_svc, trace_id=trace_id)
    try:
        resp = await service.evaluate_batch_candidates(limit=limit)
    except MemoryVectorServiceError as exc:
        raise vector_error(exc, trace_id, "Candidate batch promotion evaluation")
    except Exception as exc:
        raise memory_operation_error(exc, trace_id, "Candidate batch promotion evaluation")
    await db.commit()
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
        raise scope_forbidden_error(body.trace_id)

    org_id = current.org_id
    if not org_id:
        raise missing_org_error(body.trace_id)
    require_uuid(current.user_id, "current.user_id", body.trace_id)
    validate_optional_uuid(body.user_id, "user_id", body.trace_id)

    try:
        vector_svc = build_vector_service(org_id, current.user_id, body.trace_id)
    except Exception as exc:
        raise embedder_unavailable_error(exc, body.trace_id, "memory_search") from exc

    service = get_memory_service(db, org_id, vector_svc, trace_id=body.trace_id)
    try:
        resp = await service.search(body)
    except MemoryVectorServiceError as exc:
        raise AppMemoryVectorServiceError(
            message=str(exc),
            code="SHARED_MEMORY_VECTOR_SEARCH_FAILED",
            detail={"operation": "memory_search"},
            trace_id=body.trace_id,
            suggestion="Check Qdrant and embedding service availability.",
        ) from exc
    except Exception as exc:
        raise memory_api_error(
            code="SHARED_MEMORY_SEARCH_FAILED",
            message=f"Memory search failed: {exc}",
            trace_id=body.trace_id,
            status_code=500,
            detail={"operation": "memory_search"},
        ) from exc

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
    service = get_memory_service(db, current.org_id)
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
        raise missing_org_error(None)

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
        raise missing_org_error(body.trace_id)
    require_uuid(body.operator_id, "operator_id", body.trace_id)

    vector_svc = build_vector_service(org_id, current.user_id, body.trace_id)
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
        raise invalid_memory_request(str(exc), body.trace_id, detail={"operation": "rollback"}) from exc
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
        raise missing_org_error(body.trace_id)

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
        raise not_found_error(f"Memory {memory_id} not found")

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
    require_uuid(body.reviewer_id, "reviewer_id", None)

    from app.repositories.memory_repo import MemoryDependencyRepository, MemoryItemRepository
    item_repo = MemoryItemRepository(db, current.org_id)
    dep_repo = MemoryDependencyRepository(db, current.org_id)

    item = await item_repo.get_by_memory_id(memory_id)
    if not item:
        raise not_found_error(f"Memory {memory_id} not found")

    edges = await dep_repo.list_by_edge_type(memory_id, ["conflicts_with"], direction="source")
    if not edges:
        raise not_found_error("No active conflicts found")

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
        vector_svc = build_vector_service(
            current.org_id,
            user_id=current.user_id,
            trace_id=None,
        )
        svc = get_memory_service(db, current.org_id, vector_svc=vector_svc)
        result = await svc.merge_conflicting_memories(
            source_memory_id=memory_id,
            target_memory_id=target_id,
            reviewer_id=body.reviewer_id,
            trace_id=None,
            merged_summary=body.merged_summary,
        )
        return ResponseEnvelope(data={"resolution": body.action, **result})
    else:
        raise invalid_memory_request(
            f"Unsupported conflict resolution action: {body.action}",
            None,
            detail={"operation": "resolve_conflict", "action": body.action},
        )

    if hasattr(dep_repo, "soft_delete_edges_between"):
        await dep_repo.soft_delete_edges_between(memory_id, target_id, "conflicts_with")
    else:
        await dep_repo.soft_delete_by_memory(memory_id)

    return ResponseEnvelope(data={
        "resolution": body.action,
        "source_memory_status": "active" if body.action == "keep_A" else "isolated",
        "target_memory_status": "active" if body.action == "keep_B" else "isolated",
        "merged_memory_id": merged_id,
    })


# ---------------------------------------------------------------
# Search with Conflict Guard
# ---------------------------------------------------------------

@router.post("/search-with-conflict-guard", response_model=ResponseEnvelope[SearchWithConflictGuardResponse])
async def search_with_conflict_guard(
    body: SearchWithConflictGuardRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """Enhanced memory search with retrieval-phase conflict detection.

    Runs RAG + Memory retrieval, then applies RetrievalConflictGuard
    to filter/suppress/downrank conflicting memories before returning context.
    """
    require_role("memory_governance", current.role)

    org_id = current.org_id
    if not org_id:
        raise missing_org_error(body.trace_id)
    require_uuid(current.user_id, "current.user_id", body.trace_id)
    validate_optional_uuid(body.user_id, "user_id", body.trace_id)

    # 1. RAG retrieval (if rag_space_id provided)
    rag_hits: list[dict] = []
    if body.rag_space_id and body.enable_conflict_guard:
        from app.services.rag_retrieval_service import RagRetrievalService
        rag_svc = RagRetrievalService(db, org_id=org_id, user_id=body.user_id)
        rag_result = await rag_svc.search(
            rag_space_id=body.rag_space_id,
            query=body.query,
            top_k=body.top_k_rag,
        )
        rag_hits = rag_result.get("hits", [])

    # 2. Memory retrieval
    vector_svc = build_vector_service(org_id, current.user_id, body.trace_id)
    memory_svc = get_memory_service(db, org_id, vector_svc, trace_id=body.trace_id)
    memory_search = MemorySearchRequest(
        org_id=body.org_id or org_id,
        user_id=body.user_id,
        query=body.query,
        scope_filter=body.scope_filter,
        top_k=body.top_k_memory,
        trace_id=body.trace_id,
    )
    try:
        memory_result = await memory_svc.search(memory_search)
    except MemoryVectorServiceError as exc:
        raise vector_error(exc, body.trace_id, "Conflict-guard memory search")
    except Exception as exc:
        raise memory_operation_error(exc, body.trace_id, "Conflict-guard memory search")
    memory_hits = [
        {
            "memory_id": item.memory_id,
            "memory_type": item.memory_type,
            "summary": item.summary,
            "score": item.score,
            "confidence": item.confidence,
            "trust_score": item.trust_score,
            "source": item.source,
            "usage_policy": item.usage_policy,
            "warnings": item.warnings,
        }
        for item in memory_result.items
    ]

    # 3. Conflict guard
    guard_output: dict = {
        "rag_hits": rag_hits,
        "memory_hits": memory_hits,
        "conflicts": [],
        "suppressed_memory_ids": [],
        "downranked_memory_ids": [],
        "warnings": [],
    }
    if body.enable_conflict_guard and (rag_hits or memory_hits):
        guard = RetrievalConflictGuard(
            org_id=org_id,
            user_id=body.user_id,
            trace_id=body.trace_id,
        )
        guard_output = await guard.check(
            query=body.query,
            rag_hits=rag_hits,
            memory_hits=memory_hits,
            session_facts=body.session_facts,
            tool_results=body.tool_results,
        )

    return ResponseEnvelope(data=SearchWithConflictGuardResponse(
        rag_hits=guard_output["rag_hits"],
        memory_hits=guard_output["memory_hits"],
        conflicts=guard_output["conflicts"],
        suppressed_memory_ids=guard_output["suppressed_memory_ids"],
        downranked_memory_ids=guard_output.get("downranked_memory_ids", []),
        policy={
            "rag_over_memory": True,
            "session_over_memory": True,
            "tool_over_memory": True,
        },
        trace_id=body.trace_id,
    ))


# ---------------------------------------------------------------
# Conflict Check (Debug)
# ---------------------------------------------------------------

@router.post("/conflicts/check", response_model=ResponseEnvelope[ConflictCheckOutput])
async def check_single_conflict(
    body: ConflictCheckInput,
    current: CurrentUser = Depends(get_current_user),
):
    """Debug endpoint: check if a single memory conflicts with given RAG hits.

    Does NOT modify database state.
    """
    guard = RetrievalConflictGuard(
        org_id=current.org_id,
        user_id=None,
        trace_id=None,
    )
    result = await guard.check(
        query=body.query,
        rag_hits=body.rag_hits,
        memory_hits=[{
            "memory_id": body.memory_id,
            "summary": body.memory_summary,
            "memory_type": "unknown",
            "score": 1.0,
            "confidence": None,
            "trust_score": None,
            "source": {},
        }],
        session_facts=body.session_facts,
    )

    conflicts = result.get("conflicts", [])
    if conflicts:
        top = conflicts[0]
        verdict = top.get("verdict", "uncertain")
        confidence = float(top.get("confidence", 0))
        reason = top.get("reason", "")
    else:
        verdict = "support"
        confidence = 0.0
        reason = None

    return ResponseEnvelope(data=ConflictCheckOutput(
        memory_id=body.memory_id,
        verdict=verdict,
        confidence=confidence,
        reason=reason,
        conflicts=conflicts,
    ))
