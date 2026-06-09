"""Graph nodes for the MemoryManagerAgent graph.

Node topology:
  request_intake -> memory_context_loader -> manager_route_policy
  -> contamination_monitor_node
  -> {no alert: result_synthesizer}
  -> {alert: provenance_node -> propagation_graph_node -> rollback_planner_node
       -> governance_recovery_agent -> replay_evaluation_node -> result_synthesizer}

Nodes delegate to real service layer (MemoryService, MemoryGovernanceService).
Never write directly to ORM or Qdrant.
"""
from __future__ import annotations

import uuid
from typing import Any

from agent.graphs.memory_manager.state import MemoryAgentState


# ---------------------------------------------------------------------------
# Helper: build a minimal event dict for state events
# ---------------------------------------------------------------------------

def _event(event_type: str, memory_id: str | None = None, trace_id: str | None = None, **kwargs: Any) -> dict:
    return {
        "event_id": f"evt_{uuid.uuid4().hex[:12]}",
        "event_type": event_type,
        "memory_id": memory_id,
        "trace_id": trace_id,
        **kwargs,
    }


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------

async def request_intake(state: MemoryAgentState) -> dict[str, Any]:
    """Record input.received event and normalize task context."""
    ctx = state.get("task_context", {})
    events = list(state.get("memory_events", []))
    events.append(_event(
        "input.received",
        trace_id=ctx.get("trace_id"),
        payload={"context_keys": list(ctx.keys())},
    ))
    return {
        "task_context": ctx,
        "memory_events": events,
    }


async def memory_context_loader(state: MemoryAgentState) -> dict[str, Any]:
    """Load relevant memory context via MemoryService.search()."""
    ctx = state.get("task_context", {})
    events = list(state.get("memory_events", []))

    try:
        from app.schemas.memory import MemorySearchRequest, Workspace as MemWorkspace
        from app.services.memory_service import MemoryService
        from app.services.memory_vector_service import MemoryVectorService
        from infra.database.session import get_session

        org_id = str(ctx.get("org_id") or "")
        query = str(ctx.get("query") or ctx.get("original_query") or "")

        if org_id and query:
            async with get_session() as session:
                vector_svc = MemoryVectorService()
                memory_svc = MemoryService(session, org_id, vector_service=vector_svc)
                req = MemorySearchRequest(
                    org_id=org_id,
                    user_id=ctx.get("user_id"),
                    workspace=MemWorkspace.APP,
                    query=query,
                    top_k=5,
                )
                resp = await memory_svc.search(req)
                mc = {
                    "items": [item.model_dump() for item in resp.items],
                    "policy_version": resp.policy_version,
                    "trace_id": resp.trace_id,
                }
        else:
            mc = {"items": []}
    except Exception:
        mc = {"items": []}

    events.append(_event(
        "memory.retrieval_completed",
        trace_id=ctx.get("trace_id"),
        payload={"item_count": len(mc.get("items", []))},
    ))
    return {"memory_context": mc, "memory_events": events}


async def manager_route_policy(state: MemoryAgentState) -> dict[str, Any]:
    """Pass-through routing node. Professional agents will be added in future iterations."""
    agent_outputs = state.get("agent_outputs", {})
    agent_outputs["manager"] = {
        "decision": "pass_through",
        "routed_agents": [],
        "note": "Professional agents not yet implemented — skipping to governance monitor",
    }
    return {"agent_outputs": agent_outputs}


# ---------------------------------------------------------------------------
# Contamination Monitor
# ---------------------------------------------------------------------------

async def contamination_monitor_node(state: MemoryAgentState) -> dict[str, Any]:
    """Detect contamination signals in recent events and memories.

    Checks for conflict warnings, anomalous trust scores, and failed index status.
    Sets contamination_alerts if issues found.
    """
    alerts = list(state.get("contamination_alerts", []))
    events = state.get("memory_events", [])
    structured = state.get("structured_memory", [])

    # Check for conflict events
    for evt in events:
        if evt.get("event_type") in (
            "memory.conflict_detected",
            "memory.write_rejected",
        ):
            alerts.append({
                "alert_type": "conflict",
                "source_event_id": evt.get("event_id"),
                "memory_id": evt.get("memory_id"),
                "reason": evt.get("payload", {}).get("reason", "unknown"),
            })

    # Check for low trust_score memories
    for item in structured:
        trust = item.get("trust_score", 1.0)
        if trust is not None and trust < 0.4 and item.get("status") == "active":
            alerts.append({
                "alert_type": "low_trust",
                "memory_id": item.get("memory_id"),
                "trust_score": trust,
            })

    # Check for failed index status
    for item in structured:
        if item.get("index_status") == "failed":
            alerts.append({
                "alert_type": "index_failed",
                "memory_id": item.get("memory_id"),
                "index_error": item.get("index_error", "unknown"),
            })

    has_alert = len(alerts) > 0
    return {
        "contamination_alerts": alerts,
        "agent_outputs": {
            **state.get("agent_outputs", {}),
            "manager": {
                **state.get("agent_outputs", {}).get("manager", {}),
                "has_alert": has_alert,
            },
        },
    }


# ---------------------------------------------------------------------------
# Governance branch nodes
# ---------------------------------------------------------------------------

async def provenance_node(state: MemoryAgentState) -> dict[str, Any]:
    """Reconstruct source event chains via MemoryProvenanceService."""
    alerts = state.get("contamination_alerts", [])
    events = list(state.get("memory_events", []))
    ctx = state.get("task_context", {})

    from app.services.memory_governance_service import MemoryProvenanceService
    from infra.database.session import get_session

    org_id = str(ctx.get("org_id") or "")
    provenance = {"chains": []}

    if org_id and alerts:
        async with get_session() as session:
            prov_svc = MemoryProvenanceService(session, org_id)
            for alert in alerts:
                mid = alert.get("memory_id")
                if mid:
                    try:
                        chain = await prov_svc.trace_provenance(mid)
                        provenance["chains"].append(chain)
                    except Exception:
                        provenance["chains"].append({
                            "memory_id": mid,
                            "alert_type": alert.get("alert_type"),
                            "error": "provenance_trace_failed",
                        })
                    events.append(_event(
                        "memory.propagation_graph_created",
                        memory_id=mid,
                        trace_id=ctx.get("trace_id"),
                    ))

    return {
        "memory_events": events,
        "agent_outputs": {
            **state.get("agent_outputs", {}),
            "provenance": provenance,
        },
    }


async def propagation_graph_node(state: MemoryAgentState) -> dict[str, Any]:
    """Build contamination propagation subgraph via MemoryPropagationService."""
    alerts = state.get("contamination_alerts", [])
    events = list(state.get("memory_events", []))
    ctx = state.get("task_context", {})

    from app.services.memory_governance_service import MemoryPropagationService
    from infra.database.session import get_session

    org_id = str(ctx.get("org_id") or "")
    graph: dict[str, Any] = {
        "direct_contaminated": [],
        "indirect_contaminated": [],
        "suspected": [],
        "nodes": [],
    }

    if org_id and alerts:
        async with get_session() as session:
            prop_svc = MemoryPropagationService(session, org_id)
            for alert in alerts:
                mid = alert.get("memory_id")
                if mid:
                    try:
                        from agent.contracts.memory_contracts import EdgeType
                        resp = await prop_svc.build_propagation_graph(
                            root_memory_id=mid,
                            max_depth=4,
                            include_edge_types=[
                                EdgeType.DERIVED_FROM,
                                EdgeType.VERSION_OF,
                                EdgeType.CITED_AS_EVIDENCE,
                            ],
                        )
                        graph["direct_contaminated"].extend(resp.direct_contaminated)
                        graph["indirect_contaminated"].extend(resp.indirect_contaminated)
                        graph["suspected"].extend(resp.suspected)
                        for node in resp.nodes:
                            graph["nodes"].append(node.model_dump())
                    except Exception:
                        pass

    events.append(_event(
        "memory.propagation_graph_created",
        trace_id=ctx.get("trace_id"),
        payload={"node_count": len(graph["nodes"])},
    ))
    return {"propagation_graph": graph, "memory_events": events}


async def rollback_planner_node(state: MemoryAgentState) -> dict[str, Any]:
    """Generate candidate rollback plans from propagation graph with policy-driven review settings."""
    pg = state.get("propagation_graph", {})
    ctx = state.get("task_context", {})
    events = list(state.get("memory_events", []))

    plan: dict[str, Any] = {"actions": []}

    for mid in pg.get("direct_contaminated", []):
        plan["actions"].append({
            "memory_id": mid,
            "action": "isolate",
            "reason": "direct contamination",
            "require_human_review": len(pg.get("direct_contaminated", [])) >= 5,
        })
    for mid in pg.get("indirect_contaminated", []):
        plan["actions"].append({
            "memory_id": mid,
            "action": "degrade",
            "reason": "indirect contamination",
            "require_human_review": False,
        })

    events.append(_event(
        "memory.rollback_planned",
        trace_id=ctx.get("trace_id"),
        payload={"action_count": len(plan["actions"])},
    ))
    return {"rollback_plan": plan, "memory_events": events}


async def governance_recovery_agent(state: MemoryAgentState) -> dict[str, Any]:
    """Execute rollback plan via MemoryRollbackService (two-phase)."""
    plan = state.get("rollback_plan", {})
    ctx = state.get("task_context", {})
    events = list(state.get("memory_events", []))

    from app.schemas.memory import RollbackAction
    from app.services.memory_governance_service import MemoryRollbackService
    from infra.database.session import get_session

    org_id = str(ctx.get("org_id") or "")
    applied = 0

    if org_id and plan.get("actions"):
        async with get_session() as session:
            rollback_svc = MemoryRollbackService(session, org_id)
            for action in plan["actions"]:
                mid = action.get("memory_id")
                act = action.get("action", "isolate")
                require_review = bool(action.get("require_human_review", False))
                try:
                    rb_action_map = {
                        "delete": RollbackAction.DELETE,
                        "degrade": RollbackAction.DEGRADE,
                        "isolate": RollbackAction.ISOLATE,
                        "patch": RollbackAction.PATCH,
                    }
                    rb_action = rb_action_map.get(act, RollbackAction.ISOLATE)
                    resp = await rollback_svc.plan_rollback(
                        root_memory_id=mid or "",
                        operator_id=str(ctx.get("user_id") or "system"),
                        operator_role="admin",
                        workspace=ctx.get("workspace", "app"),
                        trace_id=ctx.get("trace_id", ""),
                        action=rb_action,
                        target_memory_ids=[mid] if mid else [],
                        reason=action.get("reason", "contamination recovery"),
                        require_human_review=require_review,
                    )
                    applied += resp.affected_count
                    events.append(_event(
                        "memory.rollback_applied",
                        memory_id=mid,
                        trace_id=ctx.get("trace_id"),
                        payload={
                            "action": act,
                            "review_status": resp.review_status.value,
                            "rollback_id": resp.rollback_id,
                        },
                    ))
                except Exception:
                    events.append(_event(
                        "memory.rollback_applied",
                        memory_id=mid,
                        trace_id=ctx.get("trace_id"),
                        payload={"action": act, "error": "rollback_failed"},
                    ))

    return {
        "memory_events": events,
        "agent_outputs": {
            **state.get("agent_outputs", {}),
            "governance_recovery": {
                "status": "completed",
                "actions_applied": applied,
            },
        },
    }


async def replay_evaluation_node(state: MemoryAgentState) -> dict[str, Any]:
    """Evaluate recovery effectiveness via MemoryEvaluationService."""
    plan = state.get("rollback_plan", {})
    ctx = state.get("task_context", {})
    events = list(state.get("memory_events", []))

    from app.services.memory_governance_service import MemoryEvaluationService
    from infra.database.session import get_session

    org_id = str(ctx.get("org_id") or "")
    eval_result: dict[str, Any] = {
        "metrics": {"actions_applied": len(plan.get("actions", []))},
        "conclusion": "No evaluation performed.",
    }

    # Find rollback_id from events
    rollback_id = None
    for evt in events:
        if evt.get("event_type") == "memory.rollback_applied":
            payload = evt.get("payload", {})
            rid = payload.get("rollback_id")
            if rid:
                rollback_id = rid
                break

    if org_id and rollback_id:
        async with get_session() as session:
            eval_svc = MemoryEvaluationService(session, org_id)
            try:
                resp = await eval_svc.evaluate_recovery(
                    rollback_id=rollback_id,
                    trace_id=ctx.get("trace_id"),
                )
                eval_result = {
                    "evaluation_id": resp.evaluation_id,
                    "metrics": resp.metrics,
                    "conclusion": resp.conclusion,
                }
            except Exception:
                pass

    events.append(_event(
        "memory.evaluation_completed",
        trace_id=ctx.get("trace_id"),
        payload=eval_result.get("metrics", {}),
    ))
    return {"evaluation_result": eval_result, "memory_events": events}


# ---------------------------------------------------------------------------
# Result Synthesizer
# ---------------------------------------------------------------------------

async def result_synthesizer(state: MemoryAgentState) -> dict[str, Any]:
    """Assemble final result with governance summary."""
    mc = state.get("memory_context", {})
    pg = state.get("propagation_graph", {})
    eval_result = state.get("evaluation_result", {})
    ctx = state.get("task_context", {})

    final = {
        "status": "completed",
        "memory_sources_used": len(mc.get("items", [])),
        "contamination_nodes": len(pg.get("nodes", [])),
        "evaluation": eval_result,
        "trace_id": ctx.get("trace_id"),
    }

    return {"final_result": final}
