from __future__ import annotations

from typing import Any

ALLOWED_ASSESSMENT_STATES = {
    "normal_so_far",
    "early_abnormal",
    "uncertain_continue",
    "insufficient_data",
    "manual_review_required",
}

ALLOWED_RISK_LEVELS = {"low", "medium", "high", "critical"}


def clamp_float(value: Any, default: float = 0.0, min_value: float = 0.0, max_value: float = 1.0) -> float:
    try:
        v = float(value)
    except Exception:
        return default
    return max(min_value, min(max_value, v))


def normalize_assessment_state(value: Any) -> str:
    state = str(value or "").strip()
    if state in ALLOWED_ASSESSMENT_STATES:
        return state
    return "uncertain_continue"


def normalize_risk_level(value: Any) -> str:
    risk_level = str(value or "").strip()
    if risk_level in ALLOWED_RISK_LEVELS:
        return risk_level
    return "medium"


def enforce_lab_safety(payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload or {})
    payload["assessment_state"] = normalize_assessment_state(payload.get("assessment_state"))
    payload["risk_level"] = normalize_risk_level(payload.get("risk_level"))
    payload["abnormal_probability"] = clamp_float(payload.get("abnormal_probability"))
    payload["confidence"] = clamp_float(payload.get("confidence"))
    payload["can_make_final_verdict"] = False
    return payload
