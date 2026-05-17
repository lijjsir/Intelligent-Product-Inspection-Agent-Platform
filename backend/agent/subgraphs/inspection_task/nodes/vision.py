from __future__ import annotations

from datetime import datetime
from typing import Any

from agent.llm.client import LLMClient
from agent.subgraphs.inspection_task.state import InspectionState
from agent.vision.detector_client import VisionDetectorClient
from agent.vision.heuristic_detector import extract_defects


def _has_structured_defect_payload(data: object) -> bool:
    if isinstance(data, dict):
        for key in ("defects", "items", "detections"):
            if isinstance(data.get(key), list):
                return True
        text = data.get("text")
        if isinstance(text, str):
            parsed = LLMClient._extract_json_object(text)
            if isinstance(parsed, dict):
                return _has_structured_defect_payload(parsed)
    elif isinstance(data, str):
        parsed = LLMClient._extract_json_object(data)
        if isinstance(parsed, dict):
            return _has_structured_defect_payload(parsed)
    return False


async def run_vision(state: InspectionState) -> InspectionState:
    now = datetime.utcnow().isoformat()
    images = state.get("image_urls") or []
    defects: list[dict[str, Any]] = []
    if images:
        detector = VisionDetectorClient()
        if detector.enabled:
            try:
                detector_data = await detector.detect(
                    image_urls=images,
                    product_id=state.get("product_id"),
                    spec_code=state.get("spec_code"),
                )
                defects = extract_defects(detector_data)
                if defects:
                    state.setdefault("timeline", []).append(
                        {"stage": "vision-detector", "message": f"专用视觉服务返回 {len(defects)} 个候选缺陷", "ts": now}
                    )
            except Exception as exc:
                state.setdefault("timeline", []).append(
                    {"stage": "vision-detector", "message": f"专用视觉服务不可用，回退到大模型视觉: {exc}", "ts": now}
                )
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
                trace_id=state.get("trace_id"),
                task_id=state.get("task_id"),
                org_id=state.get("org_id"),
                provider=state.get("model_provider"),
            )
            try:
                data = await client.chat(
                    [{"role": "user", "content": [{"type": "text", "text": prompt}, *[{"type": "image_url", "image_url": {"url": url}} for url in images]]}],
                    temperature=0.1,
                    observation_name="inspection.vision",
                    observation_metadata={"stage": "vision", "image_count": len(images)},
                )
                if not _has_structured_defect_payload(data):
                    raise RuntimeError("vision model returned no structured defects payload")
                defects = extract_defects(data)
                if isinstance(data, dict) and isinstance(data.get("image_summary"), str):
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
            except Exception as exc:
                state.setdefault("runtime_errors", []).append(
                    {
                        "stage": "vision",
                        "model_id": state.get("model_id"),
                        "message": str(exc),
                    }
                )
                state.setdefault("timeline", []).append(
                    {"stage": "vision", "message": f"视觉分析失败: {exc}", "ts": now}
                )
                state["defects"] = []
                return state

    state["defects"] = defects
    state.setdefault("timeline", []).append(
        {"stage": "vision", "message": f"视觉分析完成，检出 {len(defects)} 个候选缺陷", "ts": now}
    )
    return state
