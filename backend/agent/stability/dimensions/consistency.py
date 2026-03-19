from __future__ import annotations


def score_consistency(verdict: str, max_defect_confidence: float) -> float:
    if verdict == "pass" and max_defect_confidence > 0.7:
        return 0.25
    if verdict == "fail" and max_defect_confidence < 0.45:
        return 0.35
    return 0.82
