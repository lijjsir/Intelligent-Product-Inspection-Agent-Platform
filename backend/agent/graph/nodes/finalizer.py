from __future__ import annotations

from datetime import datetime

from agent.graph.state import InspectionState


async def finalize(state: InspectionState) -> InspectionState:
    now = datetime.utcnow().isoformat()
    state.setdefault("timeline", []).append({"stage": "finalizer", "message": "流程收敛，准备持久化结果", "ts": now})
    return state
