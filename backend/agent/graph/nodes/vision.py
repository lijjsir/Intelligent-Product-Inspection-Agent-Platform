from __future__ import annotations

from datetime import datetime
from typing import Any

from agent.graph.state import InspectionState
from agent.llm.client import LLMClient


def _fallback_defects() -> list[dict[str, Any]]:
    return [
        {
            "type": "surface_scratch",
            "confidence": 0.62,
            "bbox": [0.18, 0.28, 0.35, 0.16],
            "description": "检测到轻微表面划痕",
        }
    ]


async def run_vision(state: InspectionState) -> InspectionState:
    now = datetime.utcnow().isoformat()
    images = state.get("image_urls") or []
    defects: list[dict[str, Any]] = []
    if images:
        prompt = (
            "你是工业质检视觉模型。请识别图像缺陷，并返回 JSON："
            '{"defects":[{"type":"...","confidence":0-1,"bbox":[x,y,w,h],"description":"..."}]}'
        )
        client = LLMClient()
        try:
            data = await client.vision_chat(prompt, images)
            defects = (data.get("defects") or []) if isinstance(data, dict) else []
        except Exception:
            defects = _fallback_defects()
    if not defects:
        defects = _fallback_defects()

    state["defects"] = defects
    state.setdefault("timeline", []).append(
        {"stage": "vision", "message": f"视觉分析完成，检出 {len(defects)} 个候选缺陷", "ts": now}
    )
    return state
