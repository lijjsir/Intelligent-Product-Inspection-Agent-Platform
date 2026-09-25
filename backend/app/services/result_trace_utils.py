from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.chat_trust_scoring_service import score_output_rule


def truthy_citation(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value > 0
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def extract_citation_items(citations: Any) -> list[dict[str, Any]]:
    if isinstance(citations, dict):
        items = citations.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    if isinstance(citations, list):
        return [item for item in citations if isinstance(item, dict)]
    return []


def is_verified_rag_citation(item: dict[str, Any]) -> bool:
    return (
        str(item.get("kind") or "").lower() == "rag"
        and bool(str(item.get("quote") or item.get("excerpt") or "").strip())
        and bool(str(item.get("source") or item.get("id") or item.get("source_id") or "").strip())
    )


def build_rag_summary_from_reasoning(
    reasoning_chain: dict[str, Any],
    citations: list[dict[str, Any]],
) -> dict[str, Any]:
    existing = reasoning_chain.get("rag_summary")
    if isinstance(existing, dict) and existing:
        return dict(existing)
    packet = reasoning_chain.get("evidence_packet")
    if not isinstance(packet, dict):
        return {}
    retrieval = dict(packet.get("rag_retrieval") or {})
    rag_source = (packet.get("sources") or {}).get("rag") if isinstance(packet.get("sources"), dict) else None
    containers = list((rag_source or {}).get("items") or []) if isinstance(rag_source, dict) else []
    hits = [
        hit
        for container in containers
        if isinstance(container, dict)
        for hit in list(container.get("hits") or [])
        if isinstance(hit, dict)
    ]
    return {
        **retrieval,
        "attempted": bool(retrieval.get("attempted") or rag_source is not None),
        "hit_count": int(retrieval.get("hit_count") or len(hits)),
        "query": packet.get("query"),
        "used_citation_count": len(citations),
        "affected_verdict": bool(citations),
    }


def trust_score_from_rule_scores(scores: dict[str, Any]) -> float | None:
    if scores.get("trust_score") is not None:
        return float(scores["trust_score"])
    hallucination_risk = scores.get("hallucination_risk")
    overconfidence = scores.get("overconfidence")
    if hallucination_risk is None and overconfidence is None:
        return None
    citation_confidence = 1.0 if truthy_citation(scores.get("has_citation")) else 0.0
    risk_values = [
        float(hallucination_risk or 0.0),
        float(overconfidence or 0.0),
        1.0 - citation_confidence,
    ]
    return round(max(0.0, min(1.0, 1.0 - (sum(risk_values) / len(risk_values)))), 3)


def build_trace_metrics(
    *,
    reasoning_chain: dict[str, Any],
    input_text: str,
    output_text: str,
    citations: list[dict[str, Any]],
    synthesize_missing: bool = True,
) -> dict[str, Any]:
    existing = reasoning_chain.get("trust_scoring")
    trust_scoring = dict(existing) if isinstance(existing, dict) else {}
    if not trust_scoring:
        if not synthesize_missing:
            return {
                "trust_score": None,
                "hallucination_risk": None,
                "overconfidence": None,
                "has_citation": None,
            }
        trust_scoring = score_output_rule(
            input_text=input_text,
            output_text=output_text,
            citations=citations,
        )
    trust_score = trust_score_from_rule_scores(trust_scoring)
    if trust_score is not None:
        trust_scoring["trust_score"] = trust_score
    reasoning_chain["trust_scoring"] = trust_scoring
    return {
        "trust_score": trust_score,
        "hallucination_risk": trust_scoring.get("hallucination_risk"),
        "overconfidence": trust_scoring.get("overconfidence"),
        "has_citation": truthy_citation(trust_scoring.get("has_citation")),
    }


def parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None
    return None


def derive_latency_ms(result_latency_ms: Any, *, task: Any | None = None) -> int | None:
    if result_latency_ms is not None:
        try:
            return int(result_latency_ms)
        except (TypeError, ValueError):
            return None

    started_at = parse_datetime(getattr(task, "started_at", None)) if task is not None else None
    finished_at = parse_datetime(getattr(task, "finished_at", None)) if task is not None else None
    metadata = getattr(task, "meta_data", None) if task is not None else None
    execution = metadata.get("execution") if isinstance(metadata, dict) else None
    if isinstance(execution, dict):
        started_at = started_at or parse_datetime(execution.get("started_at"))
        finished_at = finished_at or parse_datetime(execution.get("finished_at"))

    if started_at and finished_at and finished_at >= started_at:
        return max(1, int(round((finished_at - started_at).total_seconds() * 1000)))
    return None
