"""Stable, auditable contract for user-facing agent answers.

The protocol contains execution summaries and evidence locators only.  It is
intentionally not a dump of hidden model reasoning or the full prompt.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


TRUST_PROTOCOL_VERSION = "trust-answer-v1"
TrustStatus = Literal["trusted", "degraded", "blocked", "failed", "unavailable"]
BoundaryStatus = Literal["in_domain", "boundary", "out_of_domain", "unknown"]


class TrustEvidenceRef(BaseModel):
    ref: str
    source_type: str = "unknown"
    source_id: str | None = None
    scope: dict[str, str] | None = None
    used: bool = True
    confidence: float | None = Field(default=None, ge=0, le=1)


class TrustReasoningStep(BaseModel):
    step_id: str
    capability: str = ""
    status: Literal["success", "failed", "blocked", "skipped"]
    summary: str = ""
    evidence_refs: list[str] = Field(default_factory=list)


class TrustAnswerProtocol(BaseModel):
    protocol_version: Literal["trust-answer-v1"] = TRUST_PROTOCOL_VERSION
    question: str
    conclusion: str
    status: TrustStatus
    confidence: float = Field(default=0, ge=0, le=1)
    capability_boundary: BoundaryStatus = "unknown"
    evidence_refs: list[TrustEvidenceRef] = Field(default_factory=list)
    reasoning_steps: list[TrustReasoningStep] = Field(default_factory=list)
    citation_coverage: float = Field(default=0, ge=0, le=1)
    semantic_metrics: dict[str, float | int] = Field(default_factory=dict)
    refusal_reason: str | None = None
    degrade_reasons: list[str] = Field(default_factory=list)
    trace_id: str | None = None


def build_trust_answer_protocol(
    *,
    question: str,
    answer: str,
    status: str,
    citations: list[dict[str, Any]] | None = None,
    route_trace: dict[str, Any] | None = None,
    trace_id: str | None = None,
    route_confidence: float | None = None,
    capability_boundary: BoundaryStatus | None = None,
    refusal_reason: str | None = None,
    degrade_reasons: list[str] | None = None,
    citation_coverage: float | None = None,
) -> TrustAnswerProtocol:
    """Normalize existing manager output into the trust protocol.

    A citation is represented by a stable locator, while route observations are
    reduced to one-line summaries suitable for audit and UI display.
    """

    normalized_status = str(status or "completed").strip().lower()
    status_map: dict[str, TrustStatus] = {
        "completed": "trusted",
        "success": "trusted",
        "trusted": "trusted",
        "degraded": "degraded",
        "blocked": "blocked",
        "failed": "failed",
        "unavailable": "unavailable",
    }
    protocol_status = status_map.get(normalized_status, "degraded")
    trace = dict(route_trace or {})

    evidence: list[TrustEvidenceRef] = []
    seen_refs: set[str] = set()
    for index, raw in enumerate(citations or [], start=1):
        if not isinstance(raw, dict):
            continue
        ref = str(
            raw.get("ref")
            or raw.get("citation_ref")
            or raw.get("id")
            or raw.get("source_id")
            or f"evidence-{index}"
        ).strip()
        if not ref or ref in seen_refs:
            continue
        seen_refs.add(ref)
        source_type = str(raw.get("source_type") or raw.get("type") or "unknown")
        source_id = str(raw.get("source_id") or raw.get("id") or "").strip() or None
        scope_raw = raw.get("scope")
        scope = (
            {"scope_type": str(scope_raw.get("scope_type")), "scope_id": str(scope_raw.get("scope_id"))}
            if isinstance(scope_raw, dict) and scope_raw.get("scope_type") and scope_raw.get("scope_id")
            else None
        )
        raw_confidence = raw.get("confidence")
        try:
            confidence = max(0.0, min(1.0, float(raw_confidence))) if raw_confidence is not None else None
        except (TypeError, ValueError):
            confidence = None
        evidence.append(
            TrustEvidenceRef(
                ref=ref,
                source_type=source_type,
                source_id=source_id,
                scope=scope,
                used=bool(raw.get("used", True)),
                confidence=confidence,
            )
        )

    steps: list[TrustReasoningStep] = []
    observations = [item for item in list(trace.get("observations") or []) if isinstance(item, dict)]
    for index, observation in enumerate(observations, start=1):
        step_id = str(observation.get("step_id") or f"observation-{index}")
        step_status = str(observation.get("status") or "success")
        if step_status not in {"success", "failed", "blocked", "skipped"}:
            step_status = "failed"
        artifact_refs = [
            str(item)
            for item in list(observation.get("artifact_ids") or [])
            if str(item).strip()
        ]
        steps.append(
            TrustReasoningStep(
                step_id=step_id,
                capability=str(observation.get("capability_key") or ""),
                status=step_status,  # type: ignore[arg-type]
                summary=str(observation.get("summary") or "")[:500],
                evidence_refs=artifact_refs,
            )
        )

    route_reason = str(trace.get("reason") or "")
    if capability_boundary is None:
        if protocol_status == "blocked" or route_reason in {"action_blocked", "rag_ingest"}:
            capability_boundary = "boundary"
        elif protocol_status == "trusted":
            capability_boundary = "in_domain"
        else:
            capability_boundary = "unknown"

    raw_coverage = citation_coverage
    if raw_coverage is None:
        rag_summary = trace.get("rag_summary")
        raw_coverage = rag_summary.get("citation_coverage") if isinstance(rag_summary, dict) else None
    try:
        coverage = max(0.0, min(1.0, float(raw_coverage))) if raw_coverage is not None else (1.0 if evidence else 0.0)
    except (TypeError, ValueError):
        coverage = 0.0

    try:
        confidence = max(0.0, min(1.0, float(route_confidence))) if route_confidence is not None else coverage
    except (TypeError, ValueError):
        confidence = coverage
    if protocol_status in {"blocked", "failed", "unavailable"}:
        confidence = 0.0
    elif protocol_status == "degraded":
        confidence = min(confidence, 0.5)
    if not evidence:
        # A fluent answer without a locator is not allowed to claim high
        # confidence, even for an otherwise in-domain route.
        confidence = min(confidence, 0.5)

    reasons = [str(item)[:500] for item in list(degrade_reasons or []) if str(item).strip()]
    if protocol_status in {"blocked", "failed", "unavailable"} and refusal_reason:
        reasons = list(dict.fromkeys([*reasons, str(refusal_reason)[:500]]))

    semantic_metrics = build_semantic_signal_metrics(
        citations=citations,
        route_trace=trace,
        citation_coverage=coverage,
    )

    return TrustAnswerProtocol(
        question=str(question or ""),
        conclusion=str(answer or ""),
        status=protocol_status,
        confidence=confidence,
        capability_boundary=capability_boundary,
        evidence_refs=evidence,
        reasoning_steps=steps,
        citation_coverage=coverage,
        semantic_metrics=semantic_metrics,
        refusal_reason=str(refusal_reason or "").strip() or None,
        degrade_reasons=list(dict.fromkeys(reasons)),
        trace_id=str(trace_id or "").strip() or None,
    )


def build_semantic_signal_metrics(
    *,
    citations: list[dict[str, Any]] | None = None,
    route_trace: dict[str, Any] | None = None,
    citation_coverage: float = 0.0,
) -> dict[str, float | int]:
    """Return explainable signal/noise counters for a response.

    The counters are deliberately conservative: missing evidence is counted as
    noise rather than inferred to be useful knowledge.
    """

    raw_citations = [item for item in list(citations or []) if isinstance(item, dict)]
    counts: dict[str, int] = {
        "effective_facts": 0,
        "standards": 0,
        "expert_knowledge": 0,
        "rules": 0,
        "conflicts": 0,
        "redundant_context": 0,
        "irrelevant_context": 0,
        "error_knowledge": 0,
    }
    seen_sources: set[str] = set()
    for item in raw_citations:
        source_type = str(item.get("source_type") or item.get("type") or "").lower()
        source_id = str(item.get("source_id") or item.get("id") or item.get("ref") or "").strip()
        if source_id and source_id in seen_sources:
            counts["redundant_context"] += 1
        elif source_id:
            seen_sources.add(source_id)
        if any(token in source_type for token in ("standard", "spec", "norm")):
            counts["standards"] += 1
        elif any(token in source_type for token in ("rule", "policy", "constraint")):
            counts["rules"] += 1
        elif any(token in source_type for token in ("expert", "human", "review")):
            counts["expert_knowledge"] += 1
        elif source_type:
            counts["effective_facts"] += 1
        if bool(item.get("conflict") or item.get("is_conflict")) or "conflict" in source_type:
            counts["conflicts"] += 1
        if bool(item.get("irrelevant") or item.get("rejected")):
            counts["irrelevant_context"] += 1
        if bool(item.get("error_knowledge") or item.get("invalid")):
            counts["error_knowledge"] += 1

    trace = dict(route_trace or {})
    observations = [item for item in list(trace.get("observations") or []) if isinstance(item, dict)]
    counts["conflicts"] += sum(
        1
        for item in observations
        if "conflict" in str(item.get("capability_key") or "").lower()
        or str(item.get("status") or "") in {"failed", "blocked"}
    )
    rag_summary = trace.get("rag_summary") if isinstance(trace.get("rag_summary"), dict) else {}
    candidate_count = int(rag_summary.get("hit_count") or rag_summary.get("candidate_count") or len(raw_citations))
    candidate_count = max(candidate_count, len(raw_citations))
    effective = sum(counts[key] for key in ("effective_facts", "standards", "expert_knowledge", "rules"))
    counts["irrelevant_context"] += max(candidate_count - effective, 0)
    noise = sum(counts[key] for key in ("conflicts", "redundant_context", "irrelevant_context", "error_knowledge"))
    signal = effective
    counts["signal"] = signal
    counts["noise"] = noise
    counts["signal_to_noise_ratio"] = round(signal / max(noise, 1), 4)
    counts["citation_coverage_pct"] = round(max(0.0, min(1.0, float(citation_coverage))) * 100, 2)
    return counts


__all__ = [
    "BoundaryStatus",
    "TRUST_PROTOCOL_VERSION",
    "TrustAnswerProtocol",
    "TrustEvidenceRef",
    "TrustReasoningStep",
    "build_semantic_signal_metrics",
    "build_trust_answer_protocol",
]
