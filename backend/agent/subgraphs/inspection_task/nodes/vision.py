from __future__ import annotations

from typing import Any

from agent.llm.client import LLMClient
from agent.subgraphs.inspection_task.state import InspectionState
from agent.vision.detector_client import VisionDetectorClient
from agent.vision.heuristic_detector import extract_defects
from app.core.datetime import utcnow_iso


def _has_structured_defect_payload(data: object) -> bool:
    """判断视觉服务或大模型返回值里是否包含可标准化的缺陷列表。"""
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
    """优先调用专用视觉检测服务，失败时回退到多模态大模型识别候选缺陷。"""
    now = utcnow_iso()
    images = state.get("image_urls") or []
    image_items = state.get("image_items") or []
    all_defects: list[dict[str, Any]] = []
    vision_summaries: list[str] = []

    for img_idx, url in enumerate(images):
        # Look up hash from image_items for this index.
        img_hash = ""
        for item in image_items:
            if isinstance(item, dict) and item.get("index") == img_idx:
                img_hash = str(item.get("hash", ""))
                break

        img_defects: list[dict[str, Any]] = []

        # 1) Try dedicated vision detector (per-image).
        detector = VisionDetectorClient()
        if detector.enabled:
            try:
                detector_data = await detector.detect(
                    image_urls=[url],
                    product_id=state.get("product_id"),
                    spec_code=state.get("spec_code"),
                )
                img_defects = extract_defects(detector_data)
            except Exception:
                pass

        # 2) Fallback: per-image multimodal LLM call.
        if not img_defects:
            prompt = (
                "你是工业质检视觉模型，正在检查第 {idx} 张产品图像。"
                "请只输出 JSON 对象，不要输出 Markdown。"
                "字段格式为："
                '{{"defects":[{{"type":"surface_scratch|dent|stain|crack|edge_burr|coating_peel","confidence":0.0,"bbox":[x,y,w,h],"description":"中文描述"}}],'
                '"image_summary":"一句话说明图中工件和异常位置"}}。'
                "bbox 必须是 0-1 之间的归一化坐标 [左,上,宽,高]。"
                "如果没有明显缺陷，也要返回 defects: [] 和 image_summary。"
            ).format(idx=img_idx + 1)

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
                    [{"role": "user", "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": url}},
                    ]}],
                    temperature=0.1,
                    observation_name="inspection.vision",
                    observation_metadata={"stage": "vision", "image_index": img_idx, "image_count": 1},
                )
                img_defects = extract_defects(data)
                if isinstance(data, dict) and isinstance(data.get("image_summary"), str):
                    vision_summaries.append(f"[图{img_idx + 1}] {data.get('image_summary')}")
                if isinstance(data, dict):
                    meta = data.get("__meta__") or {}
                    usage = meta.get("usage") if isinstance(meta, dict) else None
                    if isinstance(usage, dict):
                        state.setdefault("usage_events", []).append(
                            {
                                "stage": "vision",
                                "image_index": img_idx,
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
                        "image_index": img_idx,
                        "model_id": state.get("model_id"),
                        "message": str(exc),
                    }
                )

        # Tag every defect with its source image index and hash.
        for defect in img_defects:
            defect["image_index"] = img_idx
            if img_hash:
                defect["image_hash"] = img_hash
        all_defects.extend(img_defects)

    state["defects"] = all_defects
    state.setdefault("reasoning_chain", {})["vision_summary"] = "; ".join(vision_summaries)
    state.setdefault("timeline", []).append(
        {"stage": "vision", "message": f"逐张视觉分析完成，{len(images)} 张图共检出 {len(all_defects)} 个候选缺陷", "ts": now}
    )
    return state
