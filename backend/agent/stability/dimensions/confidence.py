from __future__ import annotations


def score_confidence(overall_score: float) -> float:
    return max(0.0, min(1.0, overall_score))
