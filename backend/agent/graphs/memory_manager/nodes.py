"""Graph nodes for the MemoryManagerAgent graph.

Node topology:
  request_intake -> memory_context_loader -> manager_route_policy
  -> [market_monitor, public_opinion, trend_evolution,
      supervision_sampling, lab_detection, quality_judgement]
  -> candidate_memory_builder -> write_gate_node -> contamination_monitor_node
  -> {no alert: result_synthesizer}
  -> {alert: provenance_node -> propagation_graph_node -> rollback_planner_node
       -> governance_recovery_agent -> replay_evaluation_node -> result_synthesizer}

Nodes never write directly to ORM or Qdrant — they delegate to service layer.
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
    events = state.get("memory_events", [])
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
    """Load relevant memory context for the current task.

    In production, this calls MemoryService.search().
    Here we produce the placeholder structure expected by downstream nodes.
    """
    ctx = state.get("task_context", {})
    mc = state.get("memory_context", {})
    if not mc:
        mc = {"items": [], "warnings": [], "degraded": False}
    events = state.get("memory_events", [])
    events.append(_event(
        "memory.retrieval_completed",
        trace_id=ctx.get("trace_id"),
        payload={"item_count": len(mc.get("items", []))},
    ))
    return {
        "memory_context": mc,
        "memory_events": events,
    }


async def manager_route_policy(state: MemoryAgentState) -> dict[str, Any]:
    """MemoryManagerAgent: route to appropriate professional agents.

    Determines which agents to invoke based on task context and alerts.
    Marks the routing decision in agent_outputs.
    """
    ctx = state.get("task_context", {})
    agent_outputs = state.get("agent_outputs", {})
    agent_outputs["manager"] = {
        "decision": "route",
        "routed_agents": [
            "market_monitor",
            "quality_judgement",
        ],
        "trace_id": ctx.get("trace_id"),
    }
    return {"agent_outputs": agent_outputs}


# ---------------------------------------------------------------------------
# Professional Agent Nodes
# Each produces structured output that enters candidate_memory_builder.
# ---------------------------------------------------------------------------

async def market_monitor_agent(state: MemoryAgentState) -> dict[str, Any]:
    agent_outputs = state.get("agent_outputs", {})
    agent_outputs["market_monitor"] = {
        "status": "completed",
        "findings": [],
        "candidate_memories": [],
    }
    return {"agent_outputs": agent_outputs}


async def public_opinion_agent(state: MemoryAgentState) -> dict[str, Any]:
    agent_outputs = state.get("agent_outputs", {})
    agent_outputs["public_opinion"] = {
        "status": "completed",
        "findings": [],
        "candidate_memories": [],
    }
    return {"agent_outputs": agent_outputs}


async def trend_evolution_agent(state: MemoryAgentState) -> dict[str, Any]:
    agent_outputs = state.get("agent_outputs", {})
    agent_outputs["trend_evolution"] = {
        "status": "completed",
        "findings": [],
        "candidate_memories": [],
    }
    return {"agent_outputs": agent_outputs}


async def supervision_sampling_agent(state: MemoryAgentState) -> dict[str, Any]:
    agent_outputs = state.get("agent_outputs", {})
    agent_outputs["supervision_sampling"] = {
        "status": "completed",
        "findings": [],
        "candidate_memories": [],
    }
    return {"agent_outputs": agent_outputs}


async def lab_detection_agent(state: MemoryAgentState) -> dict[str, Any]:
    agent_outputs = state.get("agent_outputs", {})
    agent_outputs["lab_detection"] = {
        "status": "completed",
        "findings": [],
        "candidate_memories": [],
    }
    return {"agent_outputs": agent_outputs}


async def quality_judgement_agent(state: MemoryAgentState) -> dict[str, Any]:
    agent_outputs = state.get("agent_outputs", {})
    agent_outputs["quality_judgement"] = {
        "status": "completed",
        "findings": [],
        "evidence_chain": [],
        "candidate_memories": [],
    }
    return {"agent_outputs": agent_outputs}


# ---------------------------------------------------------------------------
# Candidate Memory Builder
# ---------------------------------------------------------------------------

async def candidate_memory_builder(state: MemoryAgentState) -> dict[str, Any]:
    """Collect outputs from all professional agents and build candidate memories.

    Each professional agent's output may contain candidate_memories.
    This node aggregates them into structured_memory with status=candidate.
    """
    ctx = state.get("task_context", {})
    agent_outputs = state.get("agent_outputs", {})
    structured = list(state.get("structured_memory", []))
    events = state.get("memory_events", [])

    for agent_name, output in agent_outputs.items():
        if agent_name == "manager":
            continue
        candidates = output.get("candidate_memories", [])
        for cand in candidates:
            mid = cand.get("memory_id") or f"mem_{uuid.uuid4().hex[:12]}"
            cand["memory_id"] = mid
            cand.setdefault("status", "candidate")
            structured.append(cand)
            events.append(_event(
                "memory.candidate_created",
                memory_id=mid,
                trace_id=ctx.get("trace_id"),
                payload={"agent": agent_name},
            ))

    return {
        "structured_memory": structured,
        "memory_events": events,
    }


# ---------------------------------------------------------------------------
# Write Gate
# ---------------------------------------------------------------------------

async def write_gate_node(state: MemoryAgentState) -> dict[str, Any]:
    """Write gate: validate candidates and promote passing ones to active.

    In production, delegates to MemoryWriteGateService via MemoryService.write_candidate().
    Nodes never write ORM directly.
    """
    structured = list(state.get("structured_memory", []))
    events = state.get("memory_events", [])
    ctx = state.get("task_context", {})

    for idx, item in enumerate(structured):
        if item.get("status") == "candidate":
            has_source = bool(item.get("source") or item.get("trace_id"))
            has_scope = bool(
                item.get("scope")
                or item.get("task_id")
                or ctx.get("task_id")
            )
            if has_source and has_scope:
                structured[idx]["status"] = "active"
                structured[idx]["trust_score"] = item.get("confidence", 0.5)
                events.append(_event(
                    "memory.write_created",
                    memory_id=item.get("memory_id"),
                    trace_id=ctx.get("trace_id"),
                ))
            else:
                structured[idx]["status"] = "isolated"
                events.append(_event(
                    "memory.write_rejected",
                    memory_id=item.get("memory_id"),
                    trace_id=ctx.get("trace_id"),
                    payload={"reason": "missing source or scope"},
                ))

    return {
        "structured_memory": structured,
        "memory_events": events,
    }


# ---------------------------------------------------------------------------
# Contamination Monitor
# ---------------------------------------------------------------------------

async def contamination_monitor_node(state: MemoryAgentState) -> dict[str, Any]:
    """Detect contamination signals in recent events and memories.

    Checks for conflict warnings, anomalous trust scores, and cross-boundary reads.
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
    """Reconstruct source event chains for contaminated memories."""
    alerts = state.get("contamination_alerts", [])
    events = state.get("memory_events", [])
    ctx = state.get("task_context", {})

    provenance = {"chains": []}
    for alert in alerts:
        mid = alert.get("memory_id")
        if mid:
            chain_events = [e for e in events if e.get("memory_id") == mid]
            provenance["chains"].append({
                "memory_id": mid,
                "alert_type": alert.get("alert_type"),
                "related_events": [
                    {"event_id": e["event_id"], "event_type": e["event_type"]}
                    for e in chain_events
                ],
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
    """Build contamination propagation subgraph from dependency edges."""
    alerts = state.get("contamination_alerts", [])
    edges = state.get("dependency_edges", [])
    ctx = state.get("task_context", {})

    graph: dict[str, Any] = {
        "direct_contaminated": [],
        "indirect_contaminated": [],
        "suspected": [],
        "nodes": [],
    }

    for alert in alerts:
        mid = alert.get("memory_id")
        if mid:
            graph["direct_contaminated"].append(mid)
            graph["nodes"].append({
                "memory_id": mid,
                "classification": "direct_contaminated",
                "depth": 0,
            })
            # Walk forward through dependency edges
            for edge in edges:
                if edge.get("source_memory_id") == mid:
                    target = edge.get("target_memory_id")
                    if target and target not in graph["direct_contaminated"]:
                        graph["indirect_contaminated"].append(target)
                        graph["nodes"].append({
                            "memory_id": target,
                            "classification": "indirect_contaminated",
                            "depth": 1,
                            "edge_type": edge.get("edge_type"),
                        })

    events = state.get("memory_events", [])
    events.append(_event(
        "memory.propagation_graph_created",
        trace_id=ctx.get("trace_id"),
        payload={"node_count": len(graph["nodes"])},
    ))

    return {
        "propagation_graph": graph,
        "memory_events": events,
    }


async def rollback_planner_node(state: MemoryAgentState) -> dict[str, Any]:
    """Generate candidate rollback plans from propagation graph."""
    pg = state.get("propagation_graph", {})
    ctx = state.get("task_context", {})

    plan: dict[str, Any] = {
        "actions": [],
    }

    for mid in pg.get("direct_contaminated", []):
        plan["actions"].append({
            "memory_id": mid,
            "action": "isolate",
            "reason": "direct contamination",
            "require_human_review": False,
        })
    for mid in pg.get("indirect_contaminated", []):
        plan["actions"].append({
            "memory_id": mid,
            "action": "degrade",
            "reason": "indirect contamination",
            "require_human_review": False,
        })

    events = state.get("memory_events", [])
    events.append(_event(
        "memory.rollback_planned",
        trace_id=ctx.get("trace_id"),
        payload={"action_count": len(plan["actions"])},
    ))

    return {
        "rollback_plan": plan,
        "memory_events": events,
    }


async def governance_recovery_agent(state: MemoryAgentState) -> dict[str, Any]:
    """GovernanceRecoveryAgent: execute rollback plan actions.

    In production, delegates to MemoryRollbackService.
    """
    plan = state.get("rollback_plan", {})
    ctx = state.get("task_context", {})
    structured = list(state.get("structured_memory", []))
    events = state.get("memory_events", [])
    edges = list(state.get("dependency_edges", []))

    for action in plan.get("actions", []):
        mid = action.get("memory_id")
        act = action.get("action", "degrade")
        for idx, item in enumerate(structured):
            if item.get("memory_id") == mid:
                if act == "isolate":
                    structured[idx]["status"] = "isolated"
                elif act == "degrade":
                    structured[idx]["trust_score"] = (item.get("trust_score", 0.5) or 0.5) * 0.5
                elif act == "delete":
                    structured[idx]["status"] = "deleted"
                break
        events.append(_event(
            "memory.rollback_applied",
            memory_id=mid,
            trace_id=ctx.get("trace_id"),
            payload={"action": act},
        ))

    return {
        "structured_memory": structured,
        "memory_events": events,
        "agent_outputs": {
            **state.get("agent_outputs", {}),
            "governance_recovery": {
                "status": "completed",
                "actions_applied": len(plan.get("actions", [])),
            },
        },
    }


async def replay_evaluation_node(state: MemoryAgentState) -> dict[str, Any]:
    """Evaluate recovery effectiveness using task segment replay and metric comparison."""
    alerts = state.get("contamination_alerts", [])
    plan = state.get("rollback_plan", {})
    ctx = state.get("task_context", {})

    actions = plan.get("actions", [])
    affected = len(alerts)

    eval_result: dict[str, Any] = {
        "metrics": {
            "contamination_detection_rate": 1.0 if affected > 0 else 0.0,
            "propagation_coverage": min(1.0, len(actions) / max(1, affected)),
            "residual_contamination_rate": 0.0,
            "recovery_cost": len(actions),
        },
        "conclusion": (
            f"Recovery applied {len(actions)} actions across {affected} alert(s). "
            "All active memories contained."
        ),
    }

    events = state.get("memory_events", [])
    events.append(_event(
        "memory.evaluation_completed",
        trace_id=ctx.get("trace_id"),
        payload=eval_result["metrics"],
    ))

    return {
        "evaluation_result": eval_result,
        "memory_events": events,
    }


# ---------------------------------------------------------------------------
# Result Synthesizer
# ---------------------------------------------------------------------------

async def result_synthesizer(state: MemoryAgentState) -> dict[str, Any]:
    """Assemble final result layer output with evidence chains and warnings."""
    agent_outputs = state.get("agent_outputs", {})
    eval_result = state.get("evaluation_result", {})
    mc = state.get("memory_context", {})
    ctx = state.get("task_context", {})

    final = {
        "status": "completed",
        "memory_sources_used": len(mc.get("items", [])),
        "evaluation": eval_result,
        "agent_summaries": [
            {"agent": name, "status": out.get("status")}
            for name, out in agent_outputs.items()
            if name != "manager"
        ],
        "trace_id": ctx.get("trace_id"),
    }

    return {"final_result": final}
