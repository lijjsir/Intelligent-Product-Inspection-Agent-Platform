from __future__ import annotations


def score_evidence(citation_count: int, defect_count: int) -> float:
    if defect_count <= 0:
        return 0.85
    return max(0.0, min(1.0, citation_count / max(defect_count, 1)))
