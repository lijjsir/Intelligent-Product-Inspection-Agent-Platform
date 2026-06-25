import json
from pathlib import Path

from agent.subgraphs.lab_detection.contracts import LabPartialDataContext
from agent.subgraphs.lab_detection.prompts import (
    LAB_EARLY_RISK_SYSTEM_PROMPT,
    build_lab_early_risk_user_prompt,
)


def test_system_prompt_contains_final_verdict_guardrails():
    prompt = LAB_EARLY_RISK_SYSTEM_PROMPT

    assert "Lab Detection Agent" in prompt
    assert "can_make_final_verdict" in prompt
    assert "false" in prompt
    assert "JSON" in prompt
    assert "normal_so_far" in prompt
    assert "manual_review_required" in prompt


def test_user_prompt_is_json_with_required_context_sections():
    context = LabPartialDataContext.model_validate(
        {
            "sample_id": "S-PROMPT-001",
            "test_plan": {
                "total_items": 3,
                "completed_items": 1,
                "pending_items": ["confirmatory_test"],
            },
            "partial_measurements": [
                {
                    "item": "moisture",
                    "value": 18.6,
                    "unit": "%",
                    "standard_limit": "<=15",
                    "normal_range": "10-15",
                }
            ],
        }
    )

    prompt = build_lab_early_risk_user_prompt(
        context=context,
        anomaly_features=[
            {
                "item": "moisture",
                "deviation_type": "above_limit",
                "severity": "high",
            }
        ],
        deterministic_summary={"feature_count": 1},
        standard_limits=[{"item": "moisture", "standard_limit": "<=15"}],
        normal_profile={"similar_samples_count": 12},
    )
    payload = json.loads(prompt)

    assert payload["context"]["sample_id"] == "S-PROMPT-001"
    assert payload["anomaly_features"][0]["deviation_type"] == "above_limit"
    assert payload["deterministic_summary"]["feature_count"] == 1
    schema = payload["required_output_schema"]
    assert schema["can_make_final_verdict"] is False
    assert "assessment_state" in schema
    assert "next_test_priority" in schema


def test_standalone_dev_script_exists():
    script = Path(__file__).parents[1] / "scripts/dev_run_lab_detection_graph.py"

    assert script.exists()
    text = script.read_text(encoding="utf-8")
    assert "LabDetectionGraph" in text
    assert "asyncio.run" in text
