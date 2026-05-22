from __future__ import annotations

from agent.subgraphs.inspection_task.state import InspectionState
from app.core.datetime import utcnow_iso


async def plan(state: InspectionState) -> InspectionState:
    """生成本次质检的执行计划，供后续阶段和时间线展示使用。"""
    now = utcnow_iso()
    state["plan"] = {
        "task": "vision_inspection",
        "steps": ["vision", "knowledge", "reasoning", "finalize"],
        "image_count": len(state.get("image_urls") or []),
        "created_at": now,
    }
    state.setdefault("timeline", []).append({"stage": "planner", "message": "检测计划已生成", "ts": now})
    return state
