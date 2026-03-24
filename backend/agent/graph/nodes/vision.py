from __future__ import annotations

from datetime import datetime
from typing import Any

from agent.graph.state import InspectionState
from agent.llm.client import LLMClient
from agent.vision.detector_client import VisionDetectorClient
from agent.vision.heuristic_detector import build_variable_defects, extract_defects


def _fallback_defects(images: list[str], raw_text: str | None = None) -> list[dict[str, Any]]:
    return build_variable_defects(images, raw_text=raw_text)


async def run_vision(state: InspectionState) -> InspectionState:
    now = datetime.utcnow().isoformat()
    images = state.get("image_urls") or []
    defects: list[dict[str, Any]] = []
    raw_text: str | None = None
    if images:
        detector = VisionDetectorClient()
        if detector.enabled:
            try:
                detector_data = await detector.detect(
                    image_urls=images,
                    product_id=state.get("product_id"),
                    spec_id=state.get("spec_id"),
                )
                defects = extract_defects(detector_data)
                if defects:
                    state.setdefault("timeline", []).append(
                        {"stage": "vision-detector", "message": f"专用视觉服务返回 {len(defects)} 个候选缺陷", "ts": now}
                    )
            except Exception:
                defects = []

        prompt = (
            "你是工业质检视觉模型，正在检查产品图像。"
            "请只输出 JSON 对象，不要输出 Markdown。"
            "字段格式为："
            '{"defects":[{"type":"surface_scratch|dent|stain|crack|edge_burr|coating_peel","confidence":0.0,"bbox":[x,y,w,h],"description":"中文描述"}],'
            '"image_summary":"一句话说明图中工件和异常位置"}。'
            "bbox 必须是 0-1 之间的归一化坐标 [左,上,宽,高]。"
            "如果没有明显缺陷，也要返回 defects: [] 和 image_summary。"
        )
        if not defects:
            client = LLMClient(
                api_key=state.get("model_api_key"),
                base_url=state.get("model_base_url"),
                model_id=state.get("model_id"),
            )
            try:
                data = await client.vision_chat(prompt, images)
                defects = extract_defects(data)
                if isinstance(data, dict):
                    raw_text = data.get("text") if isinstance(data.get("text"), str) else None
                    if isinstance(data.get("image_summary"), str):
                        state.setdefault("reasoning_chain", {})["vision_summary"] = data.get("image_summary")
                if isinstance(data, dict):
                    meta = data.get("__meta__") or {}
                    usage = meta.get("usage") if isinstance(meta, dict) else None
                    if isinstance(usage, dict):
                        state.setdefault("usage_events", []).append(
                            {
                                "stage": "vision",
                                "model_key": str(meta.get("model") or state.get("model_id") or client.model_id),
                                "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                                "completion_tokens": int(usage.get("completion_tokens") or 0),
                                "total_tokens": int(usage.get("total_tokens") or 0),
                            }
                        )
            except Exception:
                defects = _fallback_defects(images, raw_text)
    if not defects:
        defects = _fallback_defects(images, raw_text)

    state["defects"] = defects
    state.setdefault("timeline", []).append(
        {"stage": "vision", "message": f"视觉分析完成，检出 {len(defects)} 个候选缺陷", "ts": now}
    )
    return state
