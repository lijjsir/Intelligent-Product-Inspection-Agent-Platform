from __future__ import annotations


def _risk_level_from_score(score_0_100: float) -> str:
    if score_0_100 <= 30:
        return "low"
    if score_0_100 <= 60:
        return "medium"
    if score_0_100 <= 80:
        return "high"
    return "critical"


def score(dimensions: dict[str, float]) -> dict:
    # 正向分转风险分：风险 = (1 - 维度分) * 权重
    weights = {
        "evidence_score": 0.30,
        "consistency_score": 0.25,
        "confidence_score": 0.20,
        "traceability_score": 0.15,
        "anomaly_score": 0.10,
    }
    risk_0_100 = 0.0
    for key, weight in weights.items():
        value = max(0.0, min(1.0, float(dimensions.get(key) or 0.0)))
        risk_0_100 += (1.0 - value) * 100 * weight

    return {
        "risk_score": round(risk_0_100 / 100, 4),  # 0~1 for frontend display to 10-point scale
        "risk_score_100": round(risk_0_100, 2),
        "risk_level": _risk_level_from_score(risk_0_100),
    }
