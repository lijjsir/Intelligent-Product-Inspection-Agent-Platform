from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from app.services.chat_context_service import ChatContextService


def test_serialize_row_includes_defects_and_failure_reasons():
    task = SimpleNamespace(
        id="019ececf-acba-7fba-b349-48cb5e8dc9cf",
        product_id="screw",
        spec_code="SCREW-A-2026-V1",
        status="completed",
        priority=5,
        created_at=datetime(2026, 6, 16, 5, 0, 0),
        finished_at=datetime(2026, 6, 16, 5, 3, 0),
    )
    result = SimpleNamespace(
        verdict="manual_required",
        overall_score=0.08,
        prompt_version="phase3-v1",
        llm_model="doubao-seed-2-0-lite-260215",
        tokens_used=2770,
        latency_ms=34830,
        defects=[
            {
                "type": "surface_scratch",
                "confidence": 0.92,
                "bbox": [0.39, 0.42, 0.1, 0.05],
                "description": "螺杆上部靠近螺纹起始位置存在一处表面划痕",
                "image_index": 0,
            }
        ],
        reasoning_chain={
            "standard_evaluation": {
                "summary": "检出表面划痕，当前判定需要人工复核。",
                "reasons": ["unmapped_detected_defects"],
                "unmatched_defects": ["surface_scratch"],
                "matched_rules": [],
                "ai_gate": {"reasons": ["ai_gate_blocked_auto_pass"]},
            },
            "trust_scoring": {
                "hallucination_risk": 0.12,
                "overconfidence": 0.41,
                "has_citation": True,
            },
            "trace": {"trace_id": "trace-1"},
        },
        reviewed_by=None,
        reviewed_at=None,
        review_note=None,
    )
    stability = SimpleNamespace(risk_level="medium", risk_score=0.61, root_cause="缺陷置信度较高，需复核")

    payload = ChatContextService._serialize_row(task, result, stability)

    assert payload["task_id"] == "019ececf-acba-7fba-b349-48cb5e8dc9cf"
    assert payload["product_id"] == "screw"
    assert payload["spec_code"] == "SCREW-A-2026-V1"
    assert payload["defects"][0]["type"] == "surface_scratch"
    assert "surface_scratch 92.0%" in payload["defect_summary"]
    assert "检出表面划痕" in payload["failure_reasons"][0]
    assert any("未映射缺陷: surface_scratch" in item for item in payload["failure_reasons"])
    assert payload["manual_review"]["required"] is True
    assert payload["latency_ms"] == 34830
