from datetime import datetime
from types import SimpleNamespace

import pytest
from app.core.claims import (
    CAPABILITY_CUSTOM_WORKFLOW,
    WORKSPACE_GOVERNANCE,
    WORKSPACE_OPS,
    build_auth_claims,
)
from agent.llm.client import LLMClient
from agent.llm.gateway import LLMGateway
from agent.llm.health_checker import ModelHealthChecker
from agent.llm.model_selector import ModelSelector
from agent.llm.pricing import ModelPricing
from agent.vision.heuristic_detector import build_variable_defects, normalize_defects
from app.services.feedback_service import FeedbackService
from app.services.inspection_standard_service import InspectionStandardService
from app.services.quality_report_service import QualityReportService
from infra.cache.rate_limiter import RateLimiter


class FakeResult:
    def __init__(self, created_at, citations):
        self.created_at = created_at
        self.citations = citations


class FakeFeedback:
    def __init__(self, created_at, feedback_type, result_id="result-1"):
        self.created_at = created_at
        self.feedback_type = feedback_type
        self.result_id = result_id


class FakeLedger:
    def __init__(self, result_id, trace_id, model_key, total_tokens):
        self.result_id = result_id
        self.trace_id = trace_id
        self.model_key = model_key
        self.total_tokens = total_tokens


class FakeTraceResult:
    def __init__(self, result_id, task_id, created_at, verdict, llm_model, reasoning_chain):
        self.id = result_id
        self.task_id = task_id
        self.created_at = created_at
        self.verdict = verdict
        self.llm_model = llm_model
        self.reasoning_chain = reasoning_chain


def test_model_selector_prefers_healthy_then_priority():
    selector = ModelSelector()
    selected = selector.select(
        [
            {"model_key": "slow", "is_active": True, "health_status": "degraded", "priority": 1},
            {"model_key": "fast", "is_active": True, "health_status": "healthy", "priority": 10},
            {"model_key": "best", "is_active": True, "health_status": "healthy", "priority": 2},
        ]
    )
    assert selected["model_key"] == "best"


def test_model_selector_skips_embedding_models_for_inference():
    selector = ModelSelector()
    selected = selector.select(
        [
            {"model_key": "embed-1", "model_type": "embedding", "is_active": True, "health_status": "healthy", "priority": 1},
            {"model_key": "chat-1", "model_type": "chat", "is_active": True, "health_status": "healthy", "priority": 10},
        ]
    )
    assert selected["model_key"] == "chat-1"

@pytest.mark.asyncio
async def test_llm_gateway_returns_runtime_payload():
    RateLimiter.reset()
    runtime = await LLMGateway().select_runtime(
        [
            {
                "id": "cfg-1",
                "provider": "volcengine",
                "model_key": "chat-1",
                "endpoint": "https://example.com/api/v3",
                "api_key": "secret",
                "model_type": "chat",
                "is_active": True,
                "health_status": "healthy",
                "priority": 3,
                "input_price_per_million": 1.2,
                "output_price_per_million": 4.8,
            }
        ]
    )
    assert runtime == {
        "runtime_key": "cfg-1",
        "model_config_id": "cfg-1",
        "model_id": "chat-1",
        "base_url": "https://example.com/api/v3",
        "api_key": "secret",
        "provider": "volcengine",
        "input_price_per_million": 1.2,
        "output_price_per_million": 4.8,
        "rpm_limit": None,
        "failover_depth": 0,
    }


@pytest.mark.asyncio
async def test_llm_gateway_fails_over_when_first_model_hits_rpm_limit():
    RateLimiter.reset()
    gateway = LLMGateway()
    models = [
        {
            "id": "cfg-1",
            "provider": "volcengine",
            "model_key": "chat-1",
            "endpoint": "https://example.com/api/v3",
            "api_key": "secret",
            "model_type": "chat",
            "is_active": True,
            "health_status": "healthy",
            "priority": 1,
            "rpm_limit": 1,
        },
        {
            "id": "cfg-2",
            "provider": "volcengine",
            "model_key": "chat-2",
            "endpoint": "https://example.com/api/v3",
            "api_key": "secret",
            "model_type": "chat",
            "is_active": True,
            "health_status": "healthy",
            "priority": 2,
            "rpm_limit": 10,
        },
    ]

    first = await gateway.select_runtime(models)
    second = await gateway.select_runtime(models)

    assert first["model_id"] == "chat-1"
    assert second["model_id"] == "chat-2"
    assert second["failover_depth"] == 1


@pytest.mark.asyncio
async def test_health_checker_marks_auth_failure_unhealthy(monkeypatch):
    class FakeResponse:
        def __init__(self, status_code: int, text: str = ""):
            self.status_code = status_code
            self.text = text

    class FakeClient:
        def __init__(self, *args, **kwargs):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, path, headers=None):
            return FakeResponse(401, "unauthorized")

    monkeypatch.setattr("agent.llm.health_checker.httpx.AsyncClient", FakeClient)
    checked = await ModelHealthChecker().check(
        [
            {
                "id": "cfg-1",
                "endpoint": "https://example.com/api/v3",
                "model_key": "chat-1",
                "api_key": "secret",
            }
        ]
    )

    assert checked[0]["health_status"] == "unhealthy"
    assert checked[0]["health_message"] == "/models auth failed: 401"


def test_quality_report_result_trend_handles_empty_citations():
    items = [
        FakeResult(datetime(2026, 3, 23, 10, 0, 0), {"items": ["doc-1"]}),
        FakeResult(datetime(2026, 3, 23, 11, 0, 0), {"items": []}),
        FakeResult(datetime(2026, 3, 24, 10, 0, 0), None),
    ]
    trend = QualityReportService._build_result_trend(
        items,
        lambda item: 0 if QualityReportService._has_citations(item.citations) else 1,
    )
    assert trend == [
        {"bucket": "2026-03-23", "value": 0.5},
        {"bucket": "2026-03-24", "value": 1.0},
    ]


def test_quality_report_feedback_trend_counts_thumbs_down_rate():
    items = [
        FakeFeedback(datetime(2026, 3, 23, 9, 0, 0), "down"),
        FakeFeedback(datetime(2026, 3, 23, 10, 0, 0), "up"),
        FakeFeedback(datetime(2026, 3, 24, 10, 0, 0), "down"),
    ]
    trend = QualityReportService._build_feedback_trend(items)
    assert trend == [
        {"bucket": "2026-03-23", "value": 0.5},
        {"bucket": "2026-03-24", "value": 1.0},
    ]


def test_quality_trace_builder_aggregates_tokens_and_scores():
    results = [
        FakeTraceResult(
            "result-1",
            "task-1",
            datetime(2026, 3, 24, 10, 0, 0),
            "fail",
            "model-a",
            {
                "trace": {"trace_id": "trace-1", "model_key": "model-a"},
                "langfuse_scores": [
                    {"value": 1.0, "scored_at": "2026-03-24T11:00:00", "metadata": {"actor_id": "user-1"}}
                ],
            },
        )
    ]
    feedbacks = [
        FakeFeedback(datetime(2026, 3, 24, 11, 0, 0), "down", result_id="result-1"),
        FakeFeedback(datetime(2026, 3, 24, 12, 0, 0), "up", result_id="result-1"),
    ]
    ledger_items = [
        FakeLedger("result-1", "trace-1", "model-a", 120),
        FakeLedger("result-1", "trace-1", "model-a", 30),
    ]

    traces = QualityReportService._build_quality_traces(results, feedbacks, ledger_items, limit=20)

    assert traces == [
        {
            "trace_id": "trace-1",
            "result_id": "result-1",
            "task_id": "task-1",
            "verdict": "fail",
            "model_key": "model-a",
            "total_tokens": 150,
            "feedback_count": 2,
            "thumbs_down_count": 1,
            "last_score_value": 1.0,
            "last_score_at": "2026-03-24T11:00:00",
            "created_at": datetime(2026, 3, 24, 10, 0, 0),
        }
    ]


def test_feedback_service_replaces_actor_score_event():
    chain = {
        "langfuse_scores": [
            {"value": 0.0, "scored_at": "2026-03-24T10:00:00", "metadata": {"actor_id": "user-1"}},
            {"value": 1.0, "scored_at": "2026-03-24T09:00:00", "metadata": {"actor_id": "user-2"}},
        ]
    }
    updated = FeedbackService._append_score_event(
        chain,
        {"value": 0.5, "scored_at": "2026-03-24T12:00:00", "metadata": {"actor_id": "user-1"}},
        "user-1",
    )
    assert updated["langfuse_scores"] == [
        {"value": 0.5, "scored_at": "2026-03-24T12:00:00", "metadata": {"actor_id": "user-1"}},
        {"value": 1.0, "scored_at": "2026-03-24T09:00:00", "metadata": {"actor_id": "user-2"}},
    ]


def test_visual_fallback_is_variable_by_image_source():
    defects_a = build_variable_defects(["https://example.com/a.png"])
    defects_b = build_variable_defects(["https://example.com/b.png"])
    assert defects_a != defects_b
    assert all(0 <= item["bbox"][0] <= 1 for item in defects_a)
    assert all(0 < item["confidence"] < 1 for item in defects_b)


def test_normalize_defects_accepts_alt_keys():
    defects = normalize_defects(
        [
            {
                "label": "scratch",
                "score": 88,
                "box": [0.1, 0.2, 0.3, 0.15],
                "detail": "edge scratch",
            }
        ]
    )
    assert defects == [
        {
            "type": "scratch",
            "confidence": 0.88,
            "bbox": [0.1, 0.2, 0.3, 0.15],
            "description": "edge scratch",
        }
    ]


def test_llm_client_extracts_json_from_markdown_block():
    parsed = LLMClient._extract_json_object(
        """```json\n{\"defects\": [{\"type\": \"dent\", \"confidence\": 0.7, \"bbox\": [0.1, 0.2, 0.3, 0.4]}]}\n```"""
    )
    assert parsed == {"defects": [{"type": "dent", "confidence": 0.7, "bbox": [0.1, 0.2, 0.3, 0.4]}]}


def test_model_pricing_prefers_configured_price():
    cost = ModelPricing.estimate_cost(
        "chat-1",
        1000,
        500,
        input_price_per_million=10.0,
        output_price_per_million=20.0,
    )
    assert cost == 0.02


def test_build_auth_claims_for_agent_operator():
    claims = build_auth_claims("agent_operator", "premium")
    assert claims.role == "agent_operator"
    assert claims.roles == ["agent_operator"]
    assert claims.default_workspace == WORKSPACE_OPS
    assert claims.workspaces == [WORKSPACE_OPS]
    assert CAPABILITY_CUSTOM_WORKFLOW in claims.capabilities


def test_build_auth_claims_for_governance_role():
    claims = build_auth_claims("ai_quality", "expert")
    assert claims.default_workspace == WORKSPACE_GOVERNANCE
    assert WORKSPACE_GOVERNANCE in claims.workspaces


def test_standard_service_blocks_auto_pass_without_spec():
    result = InspectionStandardService._evaluate_loaded_spec(
        spec=SimpleNamespace(
            spec_code="SCREW-A-2026-V1",
            name="螺钉标准",
            version="2026.1",
            product_id="screw",
            required_image_count=1,
            auto_pass_enabled=False,
            ai_gate_confidence_threshold=0.72,
            ai_gate_evidence_threshold=0.5,
            ai_gate_traceability_threshold=0.5,
        ),
        items=[],
        image_urls=["https://example.com/screw.png"],
        defects=[],
        citations=[{"id": "doc-1"}],
        reasoning_chain={"summary": "ok"},
        model_verdict="pass",
        overall_score=0.91,
    )
    assert result["verdict"] == "manual_required"
    assert "ai_gate_blocked_auto_pass" in result["reasons"]


def test_standard_service_rejects_when_rule_matches():
    spec = SimpleNamespace(
        spec_code="SCREW-A-2026-V1",
        name="螺钉标准",
        version="2026.1",
        product_id="screw",
        required_image_count=1,
        auto_pass_enabled=False,
        ai_gate_confidence_threshold=0.72,
        ai_gate_evidence_threshold=0.5,
        ai_gate_traceability_threshold=0.5,
    )
    item = SimpleNamespace(
        defect_type="surface_scratch",
        severity="major",
        disposition="fail",
        confidence_threshold=0.6,
        zone_name="body",
        max_count=1,
        description="划伤直接拒收",
    )
    result = InspectionStandardService._evaluate_loaded_spec(
        spec=spec,
        items=[item],
        image_urls=["https://example.com/screw.png"],
        defects=[{"type": "surface_scratch", "confidence": 0.82}],
        citations=[{"id": "doc-1"}],
        reasoning_chain={"summary": "ok"},
        model_verdict="pass",
        overall_score=0.95,
    )
    assert result["verdict"] == "fail"
    assert result["matched_rules"][0]["disposition"] == "fail"
