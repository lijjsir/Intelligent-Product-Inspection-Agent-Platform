"""Unit tests for lab_detection normalizers, parsers, and validators.

These tests do NOT require any LLM or database — they exercise pure logic.
"""

from agent.subgraphs.lab_detection.contracts import (
    LabMeasurement,
    LabTestPlan,
    LabAnomalyFeature,
    LabEarlyRiskAssessment,
)
from agent.subgraphs.lab_detection.normalizers import (
    normalize_item_name,
    normalize_lab_measurements,
    compute_data_completeness,
)
from agent.subgraphs.lab_detection.parsers import (
    parse_lower_limit,
    parse_numeric_range,
    parse_upper_limit,
)
from agent.subgraphs.lab_detection.validators import (
    clamp_float,
    normalize_assessment_state,
    normalize_risk_level,
    enforce_lab_safety,
    ALLOWED_ASSESSMENT_STATES,
)


# ── normalizers ──────────────────────────────────────────────────────


def test_normalize_item_name_known_alias():
    assert normalize_item_name("moisture") == "水分"
    assert normalize_item_name("water") == "水分"
    assert normalize_item_name("ph") == "pH"
    assert normalize_item_name("PH") == "pH"


def test_normalize_item_name_passthrough_unknown():
    assert normalize_item_name("重金属") == "重金属"
    assert normalize_item_name("微生物检测") == "微生物检测"


def test_normalize_item_name_empty():
    assert normalize_item_name("") == ""
    assert normalize_item_name("  ") == ""


def test_normalize_lab_measurements_preserves_count():
    items = [
        LabMeasurement(item="moisture", value=15.0, unit="%"),
        LabMeasurement(item="重金属", value=3.2, unit="mg/kg"),
    ]
    result = normalize_lab_measurements(items)
    assert len(result) == 2
    assert result[0].item == "水分"
    assert result[1].item == "重金属"


def test_compute_data_completeness_full():
    plan = LabTestPlan(total_items=10, completed_items=10)
    assert compute_data_completeness(plan) == 1.0


def test_compute_data_completeness_half():
    plan = LabTestPlan(total_items=10, completed_items=5)
    assert compute_data_completeness(plan) == 0.5


def test_compute_data_completeness_zero():
    plan = LabTestPlan(total_items=0, completed_items=0)
    assert compute_data_completeness(plan) == 0.0


def test_compute_data_completeness_clamped():
    plan = LabTestPlan(total_items=10, completed_items=15)
    assert compute_data_completeness(plan) == 1.0


# ── parsers ──────────────────────────────────────────────────────────


def test_parse_upper_limit_with_lt_eq():
    assert parse_upper_limit("<=15") == 15.0


def test_parse_upper_limit_with_chinese():
    assert parse_upper_limit("不大于 20.5") == 20.5
    assert parse_upper_limit("小于等于 10") == 10.0


def test_parse_upper_limit_none():
    assert parse_upper_limit(None) is None
    assert parse_upper_limit("") is None


def test_parse_upper_limit_no_match():
    assert parse_upper_limit(">=5") is None
    assert parse_upper_limit("5-10") is None


def test_parse_lower_limit_with_gt_eq():
    assert parse_lower_limit(">=5") == 5.0


def test_parse_lower_limit_with_chinese():
    assert parse_lower_limit("不小于 3.5") == 3.5
    assert parse_lower_limit("大于等于 2") == 2.0


def test_parse_lower_limit_none():
    assert parse_lower_limit(None) is None
    assert parse_lower_limit("") is None


def test_parse_numeric_range_with_dash():
    assert parse_numeric_range("10-15") == (10.0, 15.0)
    assert parse_numeric_range("5.5 - 7.0") == (5.5, 7.0)


def test_parse_numeric_range_with_tilde_or_to():
    assert parse_numeric_range("11~14") == (11.0, 14.0)
    assert parse_numeric_range("3.2 to 4.8") == (3.2, 4.8)


def test_parse_numeric_range_none_or_invalid():
    assert parse_numeric_range(None) is None
    assert parse_numeric_range("") is None
    assert parse_numeric_range("<=15") is None


# ── validators ───────────────────────────────────────────────────────


def test_clamp_float_normal():
    assert clamp_float(0.5) == 0.5
    assert clamp_float(0.0) == 0.0
    assert clamp_float(1.0) == 1.0


def test_clamp_float_out_of_range():
    assert clamp_float(1.5) == 1.0
    assert clamp_float(-0.5) == 0.0


def test_clamp_float_invalid():
    assert clamp_float("abc") == 0.0
    assert clamp_float(None) == 0.0
    assert clamp_float({}) == 0.0


def test_normalize_assessment_state_valid():
    for state in ALLOWED_ASSESSMENT_STATES:
        assert normalize_assessment_state(state) == state


def test_normalize_assessment_state_invalid():
    assert normalize_assessment_state("pass") == "uncertain_continue"
    assert normalize_assessment_state("fail") == "uncertain_continue"
    assert normalize_assessment_state("") == "uncertain_continue"


def test_normalize_risk_level_invalid_defaults_medium():
    assert normalize_risk_level("critical") == "critical"
    assert normalize_risk_level("definitely_bad") == "medium"
    assert normalize_risk_level("") == "medium"


def test_enforce_lab_safety_forces_can_make_final_verdict_false():
    payload = {
        "assessment_state": "early_abnormal",
        "abnormal_probability": 0.9,
        "confidence": 0.8,
        "can_make_final_verdict": True,
    }
    safe = enforce_lab_safety(payload)
    assert safe["can_make_final_verdict"] is False
    assert safe["assessment_state"] == "early_abnormal"
    assert 0.0 <= safe["abnormal_probability"] <= 1.0
    assert 0.0 <= safe["confidence"] <= 1.0


def test_enforce_lab_safety_clamps_bad_values():
    payload = {
        "assessment_state": "invalid_state",
        "abnormal_probability": 1.5,
        "confidence": -0.5,
    }
    safe = enforce_lab_safety(payload)
    assert safe["assessment_state"] == "uncertain_continue"
    assert safe["abnormal_probability"] == 1.0
    assert safe["confidence"] == 0.0


# ── LabEarlyRiskAssessment contract invariants ───────────────────────


def test_assessment_defaults_never_final_verdict():
    assessment = LabEarlyRiskAssessment(assessment_state="normal_so_far")
    assert assessment.can_make_final_verdict is False
    assert assessment.abnormal_probability == 0.0
    assert assessment.risk_level == "low"
    assert assessment.early_warning is False


def test_anomaly_feature_defaults():
    feature = LabAnomalyFeature(item="水分")
    assert feature.deviation_type == "unknown"
    assert feature.severity == "low"
    assert feature.confidence == 0.0
