"""Integration / unit tests for the LabDetectionGraph standalone LangGraph subgraph.

LLM and database calls are mocked so tests run offline and deterministically.
"""

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from agent.subgraphs.lab_detection.graph import LabDetectionGraph


# ── helpers ──────────────────────────────────────────────────────────


def _valid_input():
    return {
        "sample_id": "SAMPLE-001",
        "product_id": "FOOD-001",
        "product_family": "food",
        "spec_code": "GB-XXX",
        "test_plan": {
            "total_items": 6,
            "completed_items": 2,
            "pending_items": ["微生物检测", "重金属检测", "稳定性观察"],
            "critical_items": ["微生物检测"],
        },
        "partial_measurements": [
            {
                "item": "水分",
                "value": 18.6,
                "unit": "%",
                "normal_range": "10-15",
                "standard_limit": "<=15",
            },
            {
                "item": "pH",
                "value": 4.1,
                "unit": "",
                "normal_range": "5.5-7.0",
                "standard_limit": "5.0-8.0",
            },
        ],
        "historical_baseline": {
            "similar_samples_count": 230,
            "normal_response_pattern": "同类样品水分通常稳定在 11%-14%",
            "abnormal_patterns": [
                "水分早期偏高通常与储存异常或包装密封问题相关"
            ],
        },
    }


def _llm_response_normal():
    return {
        "assessment_state": "early_abnormal",
        "abnormal_probability": 0.75,
        "risk_level": "high",
        "early_warning": True,
        "can_make_final_verdict": False,
        "suggested_action": "priority_followup_test",
        "next_test_priority": [
            {
                "item": "微生物检测",
                "priority": "high",
                "reason": "水分偏高可能伴随微生物超标风险",
            }
        ],
        "explanation": "当前水分指标超过标准限值，pH 偏低，存在早期异常趋势。",
        "requires_manual_review": True,
        "confidence": 0.78,
        "__meta__": {"model": "test-model"},
    }


def _install_mocks(monkeypatch, *, llm_response=None, gateway_returns_none=False):
    """Install the standard set of mocks needed for LabDetectionGraph."""

    class FakeSession:
        async def commit(self):
            return None
        async def rollback(self):
            return None
        async def close(self):
            return None

    @asynccontextmanager
    async def fake_get_session():
        yield FakeSession()

    class FakeModelConfigService:
        def __init__(self, session, org_id):
            return None
        async def list_runtime_models(self, model_type=None):
            return [
                {
                    "id": "test-cfg",
                    "provider": "deepseek",
                    "model_key": "deepseek-v4-flash",
                    "endpoint": "https://api.deepseek.com",
                    "api_key": "sk-test",
                    "model_type": "chat",
                    "is_active": True,
                    "health_status": "healthy",
                    "priority": 1,
                }
            ]

    class FakeGateway:
        async def select_runtime(self, models, **kwargs):
            if gateway_returns_none:
                return None
            item = list(models)[0] if models else {}
            return {
                "model_id": item.get("model_key", "test-model"),
                "base_url": item.get("endpoint", "https://test.api"),
                "api_key": item.get("api_key", "sk-test"),
                "provider": item.get("provider", "deepseek"),
                "input_price_per_million": None,
                "output_price_per_million": None,
            }

    class FakeLLMClient:
        def __init__(self, **kwargs):
            return None
        async def chat(self, messages, *args, **kwargs):
            return llm_response or _llm_response_normal()

    monkeypatch.setattr(
        "agent.subgraphs.lab_detection.nodes.get_session", fake_get_session
    )
    monkeypatch.setattr(
        "agent.subgraphs.lab_detection.nodes.ModelConfigService", FakeModelConfigService
    )
    monkeypatch.setattr(
        "agent.subgraphs.lab_detection.nodes.LLMGateway", lambda: FakeGateway()
    )
    monkeypatch.setattr(
        "agent.subgraphs.lab_detection.nodes.LLMClient", FakeLLMClient
    )


# ── tests ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lab_detection_graph_runs(monkeypatch):
    """Smoke test: the graph compiles and runs end-to-end with valid input."""
    _install_mocks(monkeypatch)

    graph = LabDetectionGraph()
    result = await graph.run(
        {
            "request_id": "test-req-001",
            "workflow_run_id": "test-wf-001",
            "session_id": "test-session",
            "org_id": "test-org",
            "user_id": "test-user",
            "input_context": _valid_input(),
        }
    )

    assessment = result.get("assessment") or {}
    assert assessment, "graph must produce an assessment"
    assert "assessment_state" in assessment
    assert "can_make_final_verdict" in assessment
    assert "abnormal_probability" in assessment
    assert "risk_level" in assessment


@pytest.mark.asyncio
async def test_lab_detection_graph_never_makes_final_verdict(monkeypatch):
    """Invariant: can_make_final_verdict must always be False."""
    _install_mocks(monkeypatch, llm_response=_llm_response_normal())

    graph = LabDetectionGraph()
    result = await graph.run(
        {
            "request_id": "test-req-002",
            "org_id": "test-org",
            "input_context": _valid_input(),
        }
    )

    assessment = result.get("assessment") or {}
    assert assessment["can_make_final_verdict"] is False


@pytest.mark.asyncio
async def test_missing_input_returns_insufficient_data(monkeypatch):
    """Empty / invalid input → insufficient_data."""
    _install_mocks(monkeypatch)

    graph = LabDetectionGraph()
    result = await graph.run(
        {
            "request_id": "test-req-003",
            "org_id": "test-org",
            "input_context": {"sample_id": "", "partial_measurements": []},
        }
    )

    assessment = result.get("assessment") or {}
    assert assessment["assessment_state"] == "insufficient_data"
    assert assessment["can_make_final_verdict"] is False
    assert assessment["early_warning"] is False


@pytest.mark.asyncio
async def test_missing_sample_id_returns_insufficient_data(monkeypatch):
    """Missing sample_id in valid-looking input → insufficient_data."""
    _install_mocks(monkeypatch)

    ctx = _valid_input()
    ctx["sample_id"] = ""

    graph = LabDetectionGraph()
    result = await graph.run(
        {
            "request_id": "test-req-004",
            "org_id": "test-org",
            "input_context": ctx,
        }
    )

    assessment = result.get("assessment") or {}
    assert assessment["assessment_state"] == "insufficient_data"


@pytest.mark.asyncio
async def test_limit_violation_generates_anomaly_feature(monkeypatch):
    """A measurement above the upper limit must produce an anomaly feature."""
    _install_mocks(monkeypatch)

    graph = LabDetectionGraph()
    result = await graph.run(
        {
            "request_id": "test-req-005",
            "org_id": "test-org",
            "input_context": _valid_input(),
        }
    )

    # anomaly_features are computed BEFORE the LLM node and preserved
    # in the final assessment's deterministic_summary
    assessment = result.get("assessment") or {}
    det_summary = assessment.get("deterministic_summary") or {}
    assert det_summary.get("feature_count", 0) >= 1
    assert det_summary.get("limit_violation_count", 0) >= 1

    # Also check the anomaly_features in the state
    features = result.get("anomaly_features") or []
    assert len(features) >= 1
    above_limit = [f for f in features if f.get("deviation_type") == "above_limit"]
    assert len(above_limit) == 1
    assert above_limit[0]["item"] == "水分"


@pytest.mark.asyncio
async def test_model_unavailable_returns_manual_review(monkeypatch):
    """When LLMGateway returns no runtime, assessment → manual_review_required."""
    _install_mocks(monkeypatch, gateway_returns_none=True)

    graph = LabDetectionGraph()
    result = await graph.run(
        {
            "request_id": "test-req-006",
            "org_id": "test-org",
            "input_context": _valid_input(),
        }
    )

    assessment = result.get("assessment") or {}
    assert assessment["assessment_state"] == "manual_review_required"
    assert assessment["requires_manual_review"] is True
    assert assessment["can_make_final_verdict"] is False


@pytest.mark.asyncio
async def test_next_test_priority_has_reason(monkeypatch):
    """Every recommended next-test item must include a reason."""
    _install_mocks(monkeypatch)

    graph = LabDetectionGraph()
    result = await graph.run(
        {
            "request_id": "test-req-007",
            "org_id": "test-org",
            "input_context": _valid_input(),
        }
    )

    assessment = result.get("assessment") or {}
    priorities = assessment.get("next_test_priority") or []
    assert len(priorities) > 0
    for item in priorities:
        assert "item" in item
        assert "priority" in item
        assert "reason" in item
        assert isinstance(item["reason"], str)
        assert len(item["reason"]) > 0


@pytest.mark.asyncio
async def test_allowed_assessment_states_only(monkeypatch):
    """The assessment_state must be one of the 5 allowed values."""
    _install_mocks(monkeypatch)

    graph = LabDetectionGraph()
    result = await graph.run(
        {
            "request_id": "test-req-008",
            "org_id": "test-org",
            "input_context": _valid_input(),
        }
    )

    assessment = result.get("assessment") or {}
    assert assessment["assessment_state"] in {
        "normal_so_far",
        "early_abnormal",
        "uncertain_continue",
        "insufficient_data",
        "manual_review_required",
    }


@pytest.mark.asyncio
async def test_probability_and_confidence_in_range(monkeypatch):
    """abnormal_probability and confidence must be in [0, 1]."""
    _install_mocks(monkeypatch)

    graph = LabDetectionGraph()
    result = await graph.run(
        {
            "request_id": "test-req-009",
            "org_id": "test-org",
            "input_context": _valid_input(),
        }
    )

    assessment = result.get("assessment") or {}
    assert 0.0 <= assessment["abnormal_probability"] <= 1.0
    assert 0.0 <= assessment["confidence"] <= 1.0


@pytest.mark.asyncio
async def test_metadata_includes_latency(monkeypatch):
    """Graph run metadata must include agent, graph_name, and latency_ms."""
    _install_mocks(monkeypatch)

    graph = LabDetectionGraph()
    result = await graph.run(
        {
            "request_id": "test-req-010",
            "org_id": "test-org",
            "input_context": _valid_input(),
        }
    )

    metadata = result.get("metadata") or {}
    assert metadata.get("agent") == "lab_detection"
    assert metadata.get("graph_name") == "LabDetectionGraph"
    assert isinstance(metadata.get("latency_ms"), (int, float))
    assert metadata["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_llm_error_graceful_degradation(monkeypatch):
    """When LLMClient.chat raises, the graph returns manual_review_required
    with anomaly features preserved."""
    _install_mocks(monkeypatch)

    class CrashingLLMClient:
        def __init__(self, **kwargs):
            return None
        async def chat(self, *args, **kwargs):
            raise RuntimeError("simulated LLM crash")

    monkeypatch.setattr(
        "agent.subgraphs.lab_detection.nodes.LLMClient", CrashingLLMClient
    )

    graph = LabDetectionGraph()
    result = await graph.run(
        {
            "request_id": "test-req-011",
            "org_id": "test-org",
            "input_context": _valid_input(),
        }
    )

    assessment = result.get("assessment") or {}
    assert assessment["assessment_state"] == "manual_review_required"
    assert assessment["requires_manual_review"] is True
    assert assessment["can_make_final_verdict"] is False
    # anomaly features should still be present from the rule layer
    det_summary = assessment.get("deterministic_summary") or {}
    assert det_summary.get("feature_count", 0) >= 1


@pytest.mark.asyncio
async def test_validation_errors_block_llm_call(monkeypatch):
    """When validation fails, LLM must NOT be called and state blocked."""
    llm_called = False

    class SpyLLMClient:
        def __init__(self, **kwargs):
            return None
        async def chat(self, *args, **kwargs):
            nonlocal llm_called
            llm_called = True
            return _llm_response_normal()

    _install_mocks(monkeypatch)
    monkeypatch.setattr(
        "agent.subgraphs.lab_detection.nodes.LLMClient", SpyLLMClient
    )

    graph = LabDetectionGraph()
    result = await graph.run(
        {
            "request_id": "test-req-012",
            "org_id": "test-org",
            "input_context": {},
        }
    )

    assessment = result.get("assessment") or {}
    assert assessment["assessment_state"] == "insufficient_data"
    assert not llm_called, "LLM must NOT be called when validation fails"


@pytest.mark.asyncio
async def test_no_measurements_completeness_zero_blocks(monkeypatch):
    """Zero completeness + no features → insufficient_data block."""
    _install_mocks(monkeypatch)

    ctx = {
        "sample_id": "S-EMPTY",
        "test_plan": {
            "total_items": 6,
            "completed_items": 0,
            "pending_items": ["A", "B"],
        },
        "partial_measurements": [],
    }

    graph = LabDetectionGraph()
    result = await graph.run(
        {
            "request_id": "test-req-013",
            "org_id": "test-org",
            "input_context": ctx,
        }
    )

    assessment = result.get("assessment") or {}
    assert assessment["assessment_state"] == "insufficient_data"


@pytest.mark.asyncio
async def test_normal_llm_response_produces_early_abnormal(monkeypatch):
    """With a normal LLM response indicating abnormality, check full output."""
    _install_mocks(monkeypatch)

    graph = LabDetectionGraph()
    result = await graph.run(
        {
            "request_id": "test-req-014",
            "session_id": "s-14",
            "workflow_run_id": "wf-14",
            "org_id": "test-org",
            "user_id": "test-user",
            "input_context": _valid_input(),
        }
    )

    assessment = result.get("assessment") or {}
    assert assessment["assessment_state"] == "early_abnormal"
    assert assessment["early_warning"] is True
    assert assessment["risk_level"] == "high"
    assert assessment["requires_manual_review"] is True
    assert "水分" in assessment["explanation"]
    assert len(assessment.get("next_test_priority") or []) >= 1
    assert assessment.get("suggested_action") == "priority_followup_test"


@pytest.mark.asyncio
async def test_normal_range_quality_flag_and_environment_generate_features(monkeypatch):
    _install_mocks(
        monkeypatch,
        llm_response={
            "assessment_state": "manual_review_required",
            "abnormal_probability": 0.6,
            "risk_level": "medium",
            "early_warning": True,
            "can_make_final_verdict": True,
            "next_test_priority": [],
            "requires_manual_review": False,
            "confidence": 0.6,
        },
    )

    ctx = {
        "sample_id": "S-RANGE-001",
        "test_plan": {
            "total_items": 4,
            "completed_items": 2,
            "pending_items": ["confirmatory_test"],
        },
        "partial_measurements": [
            {
                "item": "viscosity",
                "value": 22.0,
                "unit": "cP",
                "normal_range": "10-15",
                "standard_limit": "<=30",
                "quality_flag": "instrument_drift",
                "instrument_id": "INST-01",
            }
        ],
        "environment": {
            "temperature_alarm": True,
            "note": "incubator temperature fluctuated",
        },
    }

    graph = LabDetectionGraph()
    result = await graph.run(
        {
            "request_id": "test-req-015",
            "org_id": "test-org",
            "input_context": ctx,
        }
    )

    features = result.get("anomaly_features") or []
    deviation_types = {item.get("deviation_type") for item in features}
    assert "out_of_normal_range" in deviation_types
    assert "instrument_suspected" in deviation_types
    assert "environment_suspected" in deviation_types

    assessment = result.get("assessment") or {}
    summary = assessment.get("deterministic_summary") or {}
    assert summary.get("normal_range_deviation_count") == 1
    assert summary.get("instrument_suspected_count") == 1
    assert summary.get("environment_suspected_count") == 1
    assert assessment["requires_manual_review"] is True
    assert assessment["can_make_final_verdict"] is False


@pytest.mark.asyncio
async def test_invalid_llm_risk_level_is_safely_normalized(monkeypatch):
    _install_mocks(
        monkeypatch,
        llm_response={
            "assessment_state": "normal_so_far",
            "abnormal_probability": 1.7,
            "risk_level": "definitely_bad",
            "early_warning": False,
            "can_make_final_verdict": True,
            "next_test_priority": [],
            "requires_manual_review": False,
            "confidence": -2,
        },
    )

    graph = LabDetectionGraph()
    result = await graph.run(
        {
            "request_id": "test-req-016",
            "org_id": "test-org",
            "input_context": _valid_input(),
        }
    )

    assessment = result.get("assessment") or {}
    assert assessment["risk_level"] == "medium"
    assert assessment["abnormal_probability"] == 1.0
    assert assessment["confidence"] == 0.0
    assert assessment["can_make_final_verdict"] is False


@pytest.mark.asyncio
async def test_runtime_model_lookup_error_returns_manual_review(monkeypatch):
    _install_mocks(monkeypatch)

    class FailingModelConfigService:
        def __init__(self, session, org_id):
            return None

        async def list_runtime_models(self, model_type=None):
            raise RuntimeError("database not ready")

    monkeypatch.setattr(
        "agent.subgraphs.lab_detection.nodes.ModelConfigService",
        FailingModelConfigService,
    )

    graph = LabDetectionGraph()
    result = await graph.run(
        {
            "request_id": "test-req-017",
            "org_id": "00000000-0000-0000-0000-000000000001",
            "input_context": _valid_input(),
        }
    )

    assessment = result.get("assessment") or {}
    assert assessment["assessment_state"] == "manual_review_required"
    assert assessment["requires_manual_review"] is True
    assert assessment["can_make_final_verdict"] is False
    assert result["blocked_reason"] == "model_unavailable"
