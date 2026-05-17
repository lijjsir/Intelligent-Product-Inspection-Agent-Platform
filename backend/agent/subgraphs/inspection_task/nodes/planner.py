from __future__ import annotations

from datetime import datetime

from agent.subgraphs.inspection_task.state import InspectionState


async def plan(state: InspectionState) -> InspectionState:
    now = datetime.utcnow().isoformat()
    state["plan"] = {
        "task": "vision_inspection",
        "steps": ["vision", "knowledge", "reasoning", "finalize"],
        "image_count": len(state.get("image_urls") or []),
        "created_at": now,
    }
    state.setdefault("timeline", []).append({"stage": "planner", "message": "检测计划已生成", "ts": now})
    return state
