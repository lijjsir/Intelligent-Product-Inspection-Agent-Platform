from __future__ import annotations

from agent.stability.dimensions.anomaly import score_anomaly
from agent.stability.dimensions.confidence import score_confidence
from agent.stability.dimensions.consistency import score_consistency
from agent.stability.dimensions.evidence import score_evidence
from agent.stability.dimensions.traceability import score_traceability
from agent.stability.scorer import score


async def analyze(context: dict) -> dict:
    defects = context.get("defects") or []
    citations = context.get("citations") or []
    conclusion = context.get("conclusion") or {}
    verdict = str(conclusion.get("verdict") or "uncertain")
    overall_score = float(conclusion.get("overall_score") or 0.5)
    max_conf = max([float(d.get("confidence") or 0.0) for d in defects], default=0.0)

    dimensions = {
        "evidence_score": score_evidence(len(citations), len(defects)),
        "consistency_score": score_consistency(verdict, max_conf),
        "confidence_score": score_confidence(overall_score),
        "traceability_score": score_traceability(conclusion.get("reasoning_chain") or {}, len(citations)),
        "anomaly_score": score_anomaly(len(defects), verdict == "fail"),
    }
    scored = score(dimensions)
    return {
        **dimensions,
        **scored,
        "dimension_detail": {
            "defect_count": len(defects),
            "citation_count": len(citations),
            "max_defect_confidence": max_conf,
        },
    }
