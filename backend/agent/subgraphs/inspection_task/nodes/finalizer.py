from __future__ import annotations

from app.core.datetime import utcnow_iso
from agent.subgraphs.inspection_task.state import InspectionState


async def finalize(state: InspectionState) -> InspectionState:
    """在图执行结束前写入收尾时间线，提示后续即将持久化结果。"""
    now = utcnow_iso()
    state.setdefault("timeline", []).append({"stage": "finalizer", "message": "流程收敛，准备持久化结果", "ts": now})
    return state
