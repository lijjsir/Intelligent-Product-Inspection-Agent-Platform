from __future__ import annotations

from typing import Any

from agent.router.errors import make_agent_error


async def input_adapter(state: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize memory governance inputs."""
    task_context = state.get("task_context") or {}
    if not task_context.get("org_id"):
        raise make_agent_error(
            "MEMORY_GOVERNANCE_FAILED",
            message="记忆治理缺少 org_id。",
            source="memory_governance.input_adapter",
            retryable=False,
        )
    return {**state}


async def legacy_memory_manager_node(state: dict[str, Any]) -> dict[str, Any]:
    """Phase-1 compatibility node: wraps old MemoryManagerGraph as formal graph node."""
    try:
        from agent.graphs.memory_manager.graph import MemoryManagerGraph

        graph = MemoryManagerGraph().compile()
        result = await graph.ainvoke({
            "task_context": state.get("task_context") or {},
            "structured_memory": list(state.get("structured_memory") or []),
            "memory_events": list(state.get("memory_events") or []),
        })
        return {**state, "legacy_result": dict(result or {})}
    except Exception as exc:
        raise make_agent_error(
            "MEMORY_GOVERNANCE_FAILED",
            message=f"旧记忆治理图执行失败：{exc}",
            detail={"stage": "legacy_memory_manager_node"},
            debug={"raw_error": str(exc), "error_type": exc.__class__.__name__},
            source="memory_governance.legacy_node",
            cause=exc,
        ) from exc


async def normalize_governance_result(state: dict[str, Any]) -> dict[str, Any]:
    """Normalize legacy MemoryManagerGraph output into standard governance_result."""
    legacy = state.get("legacy_result") or {}
    final = dict(legacy.get("final_result") or {})

    governance_result = {
        "status": final.get("status", "success"),
        "summary": final.get("summary", "记忆治理完成"),
        "memory_sources_used": int(final.get("memory_sources_used") or 0),
        "contamination_nodes": int(final.get("contamination_nodes") or 0),
        "raw": final,
    }
    return {**state, "governance_result": governance_result}


async def finalize(state: dict[str, Any]) -> dict[str, Any]:
    return {**state, "status": "success"}
