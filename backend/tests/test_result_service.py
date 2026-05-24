from datetime import datetime
from types import SimpleNamespace

from app.services.result_service import ResultService


def test_build_result_response_backfills_latency_and_trace_metrics():
    result = SimpleNamespace(
        id="result-1",
        task_id="task-1",
        org_id="org-1",
        verdict="manual_required",
        overall_score=0.1,
        defects=[],
        citations={"items": [{"source": "standard", "quote": "must be traceable"}]},
        reasoning_chain={
            "standard_evaluation": {"summary": "The sample requires manual review."},
            "trace": {"trace_id": "trace-1"},
            "trust_scoring": {
                "trust_score": 0.71,
                "hallucination_risk": 0.22,
                "overconfidence": 0.18,
                "has_citation": 1,
            },
        },
        llm_model="doubao-seed-2-0-lite-260215",
        prompt_version="phase3-v1",
        tokens_used=3918,
        latency_ms=None,
        reviewed_by=None,
        reviewed_at=None,
        review_note=None,
        created_at=None,
    )
    task = SimpleNamespace(
        started_at=datetime(2026, 5, 24, 1, 2, 3),
        finished_at=datetime(2026, 5, 24, 1, 2, 4, 500000),
        meta_data={},
    )

    payload = ResultService.build_result_response_payload(result, task=task)

    assert payload["latency_ms"] == 1500
    assert payload["reasoning_chain"]["trace"]["trace_id"] == "trace-1"
    assert payload["reasoning_chain"]["trace"]["trust_score"] is not None
    assert payload["reasoning_chain"]["trace"]["hallucination_risk"] is not None
    assert payload["reasoning_chain"]["trace"]["overconfidence"] is not None
    assert payload["reasoning_chain"]["trace"]["has_citation"] is True
