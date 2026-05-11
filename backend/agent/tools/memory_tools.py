"""Memory Agent tools for LangGraph tool-calling agents.

Tools are thin wrappers over services — they never call ORM or Qdrant directly.

Tools:
  - memory_search
  - memory_write_candidate
  - memory_report_conflict
  - memory_build_propagation_graph
  - memory_apply_rollback
  - memory_replay_evaluation
"""
from __future__ import annotations

from typing import Any


async def memory_search(
    query: str,
    org_id: str,
    workspace: str = "app",
    user_id: str | None = None,
    top_k: int = 5,
    memory_types: list[str] | None = None,
    task_id: str | None = None,
    memory_service: Any = None,
) -> dict[str, Any]:
    """Search shared memory with controlled retrieval pipeline.

    Args:
        query: Natural language query for semantic search.
        org_id: Tenant identifier.
        workspace: workspace filter (app/ops/governance).
        user_id: Optional user scoping.
        top_k: Max results to return (capped at 10).
        memory_types: Optional list of memory types to filter.
        task_id: Optional task to scope by.

    Returns:
        A memory_context dict with items, warnings, and degraded flag.
    """
    if not memory_service:
        return {"items": [], "warnings": ["memory_service_unavailable"], "degraded": True}

    from agent.contracts.memory_contracts import MemoryType, ScopeFilter, Workspace, MemorySearchRequest

    ws = Workspace(workspace)
    scope = ScopeFilter(
        memory_type=[MemoryType(mt) for mt in memory_types] if memory_types else None,
        task_id=task_id,
    )
    req = MemorySearchRequest(
        org_id=org_id,
        user_id=user_id,
        workspace=ws,
        query=query,
        scope_filter=scope,
        top_k=min(top_k, 10),
    )
    resp = await memory_service.search(req)
    return {
        "items": [item.model_dump() for item in resp.items],
        "warnings": resp.warnings,
        "degraded": resp.degraded,
    }


async def memory_write_candidate(
    org_id: str,
    workspace: str,
    trace_id: str,
    summary: str,
    memory_type: str = "task_episode",
    user_id: str | None = None,
    task_id: str | None = None,
    confidence: float = 0.5,
    facts: list[str] | None = None,
    warnings: list[str] | None = None,
    evidence_pointers: dict | None = None,
    ttl_policy: str = "90d",
    memory_service: Any = None,
) -> dict[str, Any]:
    """Submit a candidate memory through the write gate.

    Args:
        org_id: Tenant identifier.
        workspace: workspace (app/ops/governance).
        trace_id: Full trace ID for provenance.
        summary: Structured summary text.
        memory_type: One of the frozen memory types.
        user_id: User ID for user-scoped memories.
        task_id: Task ID for task-scoped memories.
        confidence: Write confidence [0, 1].
        facts: List of factual statements.
        warnings: List of known conflict/risk warnings.
        evidence_pointers: Pointers to supporting evidence.
        ttl_policy: Expiry policy (90d, never, task_only).

    Returns:
        Dict with memory_id, status, trust_score, confidence, warnings.
    """
    if not memory_service:
        return {"memory_id": "", "status": "rejected", "warnings": ["memory_service_unavailable"]}

    from agent.contracts.memory_contracts import (
        MemoryContent,
        MemoryScope,
        MemorySource,
        MemoryType,
        MemoryWriteRequest,
        Workspace,
    )

    req = MemoryWriteRequest(
        org_id=org_id,
        user_id=user_id,
        workspace=Workspace(workspace),
        source=MemorySource(kind="tool", task_id=task_id, trace_id=trace_id),
        memory_type=MemoryType(memory_type),
        scope=MemoryScope(task_id=task_id),
        content=MemoryContent(
            summary=summary,
            facts=facts or [],
            warnings=warnings or [],
        ),
        evidence_pointers=evidence_pointers,
        confidence=confidence,
        ttl_policy=ttl_policy,
        created_by_type="agent",
        trace_id=trace_id,
    )
    resp = await memory_service.write_candidate(req)
    return {
        "memory_id": resp.memory_id,
        "status": resp.status.value,
        "trust_score": resp.trust_score,
        "confidence": resp.confidence,
        "warnings": resp.warnings,
    }


async def memory_report_conflict(
    memory_id: str,
    conflict_description: str,
    org_id: str,
    trace_id: str,
    workspace: str = "app",
    memory_service: Any = None,
) -> dict[str, Any]:
    """Report a conflict between a memory and RAG/standard evidence.

    Creates a conflict event and optionally degrades the memory.
    """
    if not memory_service:
        return {"status": "error", "warnings": ["memory_service_unavailable"]}

    from agent.contracts.memory_contracts import EventType, MemoryEventPayload, Workspace

    payload = MemoryEventPayload(
        event_id=f"evt_conflict_{trace_id}",
        org_id=org_id,
        workspace=Workspace(workspace),
        event_type=EventType.MEMORY_CONFLICT_DETECTED,
        trace_id=trace_id,
        memory_id=memory_id,
        payload_json={"conflict_description": conflict_description},
    )
    await memory_service.record_event(payload)
    return {"status": "recorded", "memory_id": memory_id, "conflict": conflict_description}


async def memory_build_propagation_graph(
    root_memory_id: str,
    org_id: str,
    workspace: str = "governance",
    max_depth: int = 4,
    governance_service: Any = None,
) -> dict[str, Any]:
    """Build a contamination propagation subgraph from dependency edges.

    Args:
        root_memory_id: The contamination root node.
        org_id: Tenant identifier.
        workspace: Must be governance.
        max_depth: BFS depth limit (1-10).
        governance_service: MemoryGovernanceService instance.

    Returns:
        Propagation graph with classified nodes.
    """
    if not governance_service:
        return {"error": "governance_service_unavailable"}

    from agent.contracts.memory_contracts import EdgeType, MemoryPropagationRequest

    req = MemoryPropagationRequest(
        org_id=org_id,
        workspace=workspace,
        root_memory_id=root_memory_id,
        max_depth=max_depth,
        include_edge_types=[
            EdgeType.DERIVED_FROM,
            EdgeType.READ_BY,
            EdgeType.USED_AS_TOOL_PARAM,
            EdgeType.VERSION_OF,
        ],
    )
    prop_svc = governance_service
    resp = await prop_svc.build_propagation_graph(
        root_memory_id=req.root_memory_id,
        max_depth=req.max_depth,
        include_edge_types=req.include_edge_types,
    )
    return resp.model_dump()


async def memory_apply_rollback(
    root_memory_id: str,
    org_id: str,
    operator_id: str,
    trace_id: str,
    target_memory_ids: list[str],
    action: str = "isolate",
    reason: str = "",
    require_human_review: bool = False,
    workspace: str = "ops",
    governance_service: Any = None,
) -> dict[str, Any]:
    """Execute a rollback action on contaminated memories.

    Args:
        root_memory_id: Contamination root.
        org_id: Tenant identifier.
        operator_id: User/admin ID performing the rollback.
        trace_id: Audit trace ID.
        target_memory_ids: List of memory IDs to act upon.
        action: delete / degrade / isolate / patch / branch.
        reason: Justification for the rollback.
        require_human_review: If True, rollback enters pending review state.
        workspace: Must be ops or governance.
        governance_service: MemoryGovernanceService instance.

    Returns:
        Rollback response with affected count and review status.
    """
    if not governance_service:
        return {"error": "governance_service_unavailable"}

    from agent.contracts.memory_contracts import MemoryRollbackRequest, RollbackAction, Workspace

    req = MemoryRollbackRequest(
        org_id=org_id,
        workspace=Workspace(workspace),
        operator_id=operator_id,
        trace_id=trace_id,
        root_memory_id=root_memory_id,
        rollback_action=RollbackAction(action),
        target_memory_ids=target_memory_ids,
        reason=reason,
        require_human_review=require_human_review,
    )
    rollback_svc = governance_service
    resp = await rollback_svc.execute_rollback(
        root_memory_id=req.root_memory_id,
        operator_id=req.operator_id,
        workspace=req.workspace.value,
        trace_id=req.trace_id,
        action=req.rollback_action,
        target_memory_ids=req.target_memory_ids,
        reason=req.reason,
        require_human_review=req.require_human_review,
    )
    return resp.model_dump()


async def memory_replay_evaluation(
    rollback_id: str,
    org_id: str,
    workspace: str = "governance",
    task_id: str | None = None,
    trace_id: str | None = None,
    scenario: str | None = None,
    governance_service: Any = None,
) -> dict[str, Any]:
    """Run recovery verification after a rollback.

    Args:
        rollback_id: The rollback to evaluate.
        org_id: Tenant identifier.
        workspace: Must be governance.
        task_id: Optional task to replay.
        trace_id: Audit trace ID.
        scenario: Contamination scenario label.
        governance_service: MemoryGovernanceService instance.

    Returns:
        Evaluation with metrics, replay results, and conclusion.
    """
    if not governance_service:
        return {"error": "governance_service_unavailable"}

    eval_svc = governance_service
    resp = await eval_svc.evaluate_recovery(
        rollback_id=rollback_id,
        task_id=task_id,
        trace_id=trace_id,
        scenario=scenario,
    )
    return resp.model_dump()
