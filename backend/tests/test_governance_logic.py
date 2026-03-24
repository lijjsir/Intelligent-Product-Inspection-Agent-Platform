from datetime import datetime

from agent.llm.client import LLMClient
from agent.llm.gateway import LLMGateway
from agent.llm.model_selector import ModelSelector
from agent.llm.pricing import ModelPricing
from agent.vision.heuristic_detector import build_variable_defects, normalize_defects
from app.services.feedback_service import FeedbackService
from app.services.quality_report_service import QualityReportService


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


def test_llm_gateway_returns_runtime_payload():
    runtime = LLMGateway().select_runtime(
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
        "model_config_id": "cfg-1",
        "model_id": "chat-1",
        "base_url": "https://example.com/api/v3",
        "api_key": "secret",
        "provider": "volcengine",
        "input_price_per_million": 1.2,
        "output_price_per_million": 4.8,
    }


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
