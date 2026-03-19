from __future__ import annotations


def score_anomaly(defect_count: int, failed: bool) -> float:
    if failed and defect_count >= 3:
        return 0.35
    if failed:
        return 0.55
    return 0.9
