from __future__ import annotations


def should_trigger(report: dict) -> bool:
    return str(report.get("risk_level") or "").lower() in {"high", "critical"}
