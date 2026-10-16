import copy
import pytest
from app.services.inspection_requirement_engine import evaluate_plan,evaluate_requirement,convert


def rule(**kw):return {"id":"requirement","indicator":"最高车速","measurement_key":"speed","unit":"km/h","method":"7.1",
    "operator":"le","numeric_upper":25,"execution_mode":"numeric","decision_mode":"direct","minimum_observations":1,
    "expected_conditions":{"test_speed_context":"design_max"},**kw}


def obs(**kw):return {"sample_id":"sample","measurement_key":"speed","value":24.0,"unit":"km/h","method":"7.1",
    "conditions":{"test_speed_context":"design_max"},"quality_flag":"valid","validation_status":"accepted","evidence_id":"measurement",**kw}


def test_confirmed_upper_bound_inclusive_and_real_failure():
    assert evaluate_requirement(rule(),[obs(value=25.0)])["status"]=="pass"
    assert evaluate_requirement(rule(),[obs(value=30.8)])["status"]=="fail"


def test_horn_range_and_boundary():
    r=rule(operator="range",numeric_lower=75,numeric_upper=100,unit="dBA")
    assert evaluate_requirement(r,[obs(value=73.0,unit="dB(A)")])["status"]=="fail"
    assert evaluate_requirement(r,[obs(value=75.0,unit="dBA")])["status"]=="pass"


@pytest.mark.parametrize("change",[{"method":"wrong"},{"conditions":{}},{"unit":"V"},{"quality_flag":"suspect"},{"validation_status":"unverified"},{"value":float('nan')},{"value":True}])
def test_incomplete_or_wrong_observation_never_passes(change):
    assert evaluate_requirement(rule(),[obs(**change)])["status"]=="uncertain"


def test_missing_sample_or_item_keeps_plan_incomplete():
    result=evaluate_plan([rule()],["sample","missing-sample"],[obs()])
    assert result["item_verdict"]=="incomplete" and result["product_verdict"]=="not_assessed"


def test_no_limits_inferred_from_text_and_manual_requirement_not_numeric():
    assert evaluate_requirement(rule(numeric_upper=None,requirement="按6.1.1不超过25"),[obs()])["status"]=="manual_required"
    assert evaluate_requirement(rule(execution_mode="manual"),[obs()])["status"]=="manual_required"


def test_matching_units_convert_but_temperature_offset_is_not_assumed():
    assert str(convert(1000,"mm","m"))=="1.000"
    assert convert(298,"K","°C") is None
    assert evaluate_requirement(rule(),[obs(value=6.0,unit="m/s")])["status"]=="pass"


def test_uncertainty_crossing_limit_needs_review():
    assert evaluate_requirement(rule(decision_mode="interval"),[obs(value=24.8,uncertainty=0.5)])["status"]=="uncertain"
    assert evaluate_requirement(rule(decision_mode="interval"),[obs(value=24.0,uncertainty=0.2)])["status"]=="pass"


def test_no_source_or_unpublished_standard_cannot_make_pass():
    result=evaluate_plan([rule()],["sample"],[obs()],source_issues=["尚未发布标准"])
    assert result["item_verdict"]=="incomplete"


def test_all_pass_is_only_selected_items_and_risk_remains_unknown():
    result=evaluate_plan([rule()],["sample"],[obs()])
    assert result["item_verdict"]=="pass" and result["product_verdict"]=="not_assessed"
    assert result["risk_level"]=="unknown" and result["review_status"]=="required"


def test_reported_value_is_recorded_as_transcription_requiring_review():
    result=evaluate_plan([rule()],["sample"],[obs(validation_status="reported")])
    assert "使用了报告转录值，需逐项核对原文" in result["review_reasons"]


def test_duplicates_never_satisfy_minimum_or_bias_mean():
    same=obs()
    result=evaluate_requirement(rule(minimum_observations=2),[same,copy.deepcopy(same)])
    assert result['status']=='uncertain' and result['independent_observation_count']==1
    assert evaluate_requirement(rule(minimum_observations=2),[same,obs(evidence_id='trial-2')])['status']=='pass'
    result=evaluate_requirement(rule(numeric_aggregation='mean'),[same,same,obs(value=30,evidence_id='trial-2')])
    assert result['status']=='fail' and result['findings'][0]['value']=='27.0'


def test_conflicting_duplicate_is_blocked_even_when_one_copy_is_invalid():
    for other in [obs(value=30),obs(quality_flag='suspect'),obs(method='wrong')]:
        result=evaluate_requirement(rule(),[obs(),other])
        assert result['status']=='uncertain' and result['conflicting_evidence_ids']
