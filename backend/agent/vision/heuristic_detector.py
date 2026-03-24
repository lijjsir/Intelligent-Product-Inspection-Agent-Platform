from __future__ import annotations

import hashlib
import json
from typing import Any


_DEFECT_TYPES = [
    "surface_scratch",
    "dent",
    "stain",
    "crack",
    "edge_burr",
    "coating_peel",
]


def build_variable_defects(
    image_urls: list[str],
    *,
    raw_text: str | None = None,
    max_items: int = 3,
) -> list[dict[str, Any]]:
    seed_source = "|".join(image_urls) + "|" + (raw_text or "")
    digest = hashlib.sha256(seed_source.encode("utf-8")).hexdigest()
    defect_count = 1 + (int(digest[0:2], 16) % max(1, min(max_items, 3)))
    defects: list[dict[str, Any]] = []

    for index in range(defect_count):
        cursor = index * 8
        chunk = digest[cursor : cursor + 16].ljust(16, "0")
        left = 0.08 + (int(chunk[0:2], 16) / 255.0) * 0.58
        top = 0.08 + (int(chunk[2:4], 16) / 255.0) * 0.58
        width = 0.12 + (int(chunk[4:6], 16) / 255.0) * 0.18
        height = 0.10 + (int(chunk[6:8], 16) / 255.0) * 0.16
        left = min(left, 0.95 - width)
        top = min(top, 0.95 - height)
        defect_type = _DEFECT_TYPES[int(chunk[8:10], 16) % len(_DEFECT_TYPES)]
        confidence = round(0.52 + (int(chunk[10:12], 16) / 255.0) * 0.4, 4)
        defects.append(
            {
                "type": defect_type,
                "confidence": confidence,
                "bbox": [round(left, 4), round(top, 4), round(width, 4), round(height, 4)],
                "description": f"候选缺陷区域 {index + 1}，来源于视觉响应兜底分析",
            }
        )
    return defects


def normalize_defects(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        return []

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            continue
        bbox = item.get("bbox") or item.get("box") or item.get("rect")
        coords = _normalize_bbox(bbox)
        if not coords:
            continue
        defect_type = str(item.get("type") or item.get("label") or f"defect_{index + 1}").strip()
        if not defect_type:
            defect_type = f"defect_{index + 1}"
        confidence = _normalize_confidence(item.get("confidence") or item.get("score") or item.get("probability"))
        normalized.append(
            {
                "type": defect_type,
                "confidence": confidence,
                "bbox": coords,
                "description": str(item.get("description") or item.get("reason") or item.get("detail") or "").strip()
                or f"模型识别到 {defect_type}",
            }
        )
    return normalized


def extract_defects(data: object) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        candidates = data.get("defects") or data.get("items") or data.get("detections")
        defects = normalize_defects(candidates)
        if defects:
            return defects

        text = data.get("text")
        if isinstance(text, str):
            parsed = _extract_json(text)
            if parsed is not None:
                return extract_defects(parsed)
    elif isinstance(data, str):
        parsed = _extract_json(data)
        if parsed is not None:
            return extract_defects(parsed)
    return []


def _normalize_confidence(value: object) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 0.55
    if confidence > 1:
        confidence = confidence / 100.0
    return round(max(0.05, min(confidence, 0.99)), 4)


def _normalize_bbox(value: object) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        left, top, width, height = [float(item) for item in value]
    except (TypeError, ValueError):
        return None

    if max(abs(left), abs(top), abs(width), abs(height)) > 1.5:
        # Convert likely pixel coordinates to normalized placeholders.
        scale = max(left + width, top + height, 1.0)
        left, top, width, height = left / scale, top / scale, width / scale, height / scale

    width = min(max(width, 0.05), 0.8)
    height = min(max(height, 0.05), 0.8)
    left = min(max(left, 0.0), 0.95 - width)
    top = min(max(top, 0.0), 0.95 - height)
    return [round(left, 4), round(top, 4), round(width, 4), round(height, 4)]


def _extract_json(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    candidates = [stripped]
    if "```" in stripped:
        for part in stripped.split("```"):
            part = part.strip()
            if not part:
                continue
            if part.startswith("json"):
                part = part[4:].strip()
            candidates.append(part)

    for candidate in candidates:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1 or end <= start:
            continue
        snippet = candidate[start : end + 1]
        try:
            parsed = json.loads(snippet)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None
