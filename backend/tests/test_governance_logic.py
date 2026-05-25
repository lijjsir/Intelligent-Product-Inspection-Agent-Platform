from datetime import datetime
import json

import httpx
from types import SimpleNamespace

import pytest
from app.core.claims import (
    CAPABILITY_CUSTOM_WORKFLOW,
    WORKSPACE_GOVERNANCE,
    WORKSPACE_OPS,
    build_auth_claims,
)
from app.core.exceptions import NotFoundError
from agent.subgraphs.inspection_task import InspectionGraph
from agent.subgraphs.inspection_task.nodes.vision import run_vision
from agent.llm.client import LLMClient
from agent.llm.gateway import LLMGateway
from agent.llm.health_checker import ModelHealthChecker
from agent.llm.langfuse_tracer import LangfuseTracer
from agent.llm.model_selector import ModelSelector
from agent.llm.pricing import ModelPricing
from agent.rag.embedder import Embedder
from agent.vision.heuristic_detector import build_variable_defects, normalize_defects
from app.services.feedback_service import FeedbackService
from app.services.inspection_standard_service import InspectionStandardService
from app.services.quality_report_service import QualityReportService
from app.repositories.analytics_repo import AnalyticsRepository
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
            {"model_key": "slow", "provider": "deepseek", "endpoint": "https://api.deepseek.com", "api_key": "secret", "is_active": True, "health_status": "degraded", "priority": 1},
            {"model_key": "fast", "provider": "deepseek", "endpoint": "https://api.deepseek.com", "api_key": "secret", "is_active": True, "health_status": "healthy", "priority": 10},
            {"model_key": "best", "provider": "deepseek", "endpoint": "https://api.deepseek.com", "api_key": "secret", "is_active": True, "health_status": "healthy", "priority": 2},
        ]
    )
    assert selected["model_key"] == "best"


def test_model_selector_skips_embedding_models_for_inference():
    selector = ModelSelector()
    selected = selector.select(
        [
            {"model_key": "embed-1", "provider": "volcengine", "endpoint": "https://ark.cn-beijing.volces.com/api/v3", "api_key": "secret", "model_type": "embedding", "is_active": True, "health_status": "healthy", "priority": 1},
            {"model_key": "chat-1", "provider": "deepseek", "endpoint": "https://api.deepseek.com", "api_key": "secret", "model_type": "chat", "is_active": True, "health_status": "healthy", "priority": 10},
        ]
    )
    assert selected["model_key"] == "chat-1"


def test_model_config_schema_rejects_unsupported_model_type():
    with pytest.raises(ValueError):
        from app.schemas.governance import ModelConfigCreate

        ModelConfigCreate(
            provider="deepseek",
            model_key="test-model",
            display_name="Test Model",
            endpoint="https://api.example.com",
            model_type="vision",
        )


def test_model_selector_can_select_embedding_models_for_embedding_runtime():
    selector = ModelSelector()
    selected = selector.select(
        [
            {"model_key": "chat-1", "provider": "deepseek", "endpoint": "https://api.deepseek.com", "api_key": "secret", "model_type": "chat", "is_active": True, "health_status": "healthy", "priority": 1},
            {"model_key": "embed-1", "provider": "local_openai", "endpoint": "http://localhost:11434/v1", "api_key": None, "model_type": "embedding", "is_active": True, "health_status": "healthy", "priority": 10},
        ],
        model_types={"embedding"},
    )
    assert selected["model_key"] == "embed-1"


def test_model_selector_skips_remote_models_missing_api_key():
    selector = ModelSelector()
    selected = selector.select(
        [
            {
                "model_key": "embed-seed",
                "provider": "volcengine",
                "model_type": "embedding",
                "is_active": True,
                "health_status": "healthy",
                "priority": 1,
                "api_key": None,
            },
            {
                "model_key": "embed-live",
                "provider": "volcengine",
                "model_type": "embedding",
                "is_active": True,
                "health_status": "healthy",
                "priority": 10,
                "api_key": "secret",
                "endpoint": "https://ark.cn-beijing.volces.com/api/v3",
            },
        ],
        model_types={"embedding"},
    )
    assert selected["model_key"] == "embed-live"


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
async def test_llm_gateway_returns_embedding_runtime_payload():
    RateLimiter.reset()
    runtime = await LLMGateway().select_runtime(
        [
            {
                "id": "chat-cfg",
                "provider": "deepseek",
                "model_key": "deepseek-v4-flash",
                "endpoint": "https://api.deepseek.com",
                "api_key": "chat-key",
                "model_type": "chat",
                "is_active": True,
                "health_status": "healthy",
                "priority": 1,
            },
            {
                "id": "embed-cfg",
                "provider": "local_openai",
                "model_key": "bge-m3",
                "endpoint": "http://localhost:11434/v1",
                "api_key": None,
                "model_type": "embedding",
                "is_active": True,
                "health_status": "healthy",
                "priority": 20,
            },
        ],
        model_types={"embedding"},
    )

    assert runtime["model_config_id"] == "embed-cfg"
    assert runtime["model_id"] == "bge-m3"
    assert runtime["provider"] == "local_openai"


@pytest.mark.asyncio
async def test_llm_gateway_returns_none_when_no_models_available():
    RateLimiter.reset()
    runtime = await LLMGateway().select_runtime([])
    assert runtime is None


@pytest.mark.asyncio
async def test_llm_gateway_returns_none_when_all_models_excluded():
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
                "priority": 1,
            }
        ],
        excluded_runtime_ids={"cfg-1"},
    )
    assert runtime is None


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
        def __init__(self, status_code: int, text: str = "", payload=None):
            self.status_code = status_code
            self.text = text
            self._payload = payload if payload is not None else []

        def json(self):
            return self._payload

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


@pytest.mark.asyncio
async def test_health_checker_requires_model_key_in_models_list(monkeypatch):
    class FakeResponse:
        def __init__(self, status_code: int, text: str = "", payload=None):
            self.status_code = status_code
            self.text = text
            self._payload = payload if payload is not None else []

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, path, headers=None):
            return FakeResponse(200, payload=[{"id": "other-model"}])

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
    assert checked[0]["health_message"] == "GET /models missing model_key: chat-1"


@pytest.mark.asyncio
async def test_health_checker_accepts_volcengine_endpoint_model_when_chat_probe_succeeds(monkeypatch):
    class FakeResponse:
        def __init__(self, status_code: int, text: str = "", payload=None):
            self.status_code = status_code
            self.text = text
            self._payload = payload if payload is not None else []

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, path, headers=None):
            return FakeResponse(200, payload=[{"id": "deepseek-r1"}, {"id": "deepseek-r1-250120"}])

        async def post(self, path, json=None, headers=None):
            assert path == "/chat/completions"
            assert json["model"] == "ep-20260325082100-v7vs6"
            return FakeResponse(200, payload={"id": "resp-1", "choices": [{"message": {"content": "pong"}}]})

    monkeypatch.setattr("agent.llm.health_checker.httpx.AsyncClient", FakeClient)
    checked = await ModelHealthChecker().check(
        [
            {
                "id": "cfg-1",
                "provider": "volcengine",
                "endpoint": "https://ark.cn-beijing.volces.com/api/v3",
                "model_key": "ep-20260325082100-v7vs6",
                "model_type": "chat",
                "api_key": "secret",
            }
        ]
    )

    assert checked[0]["health_status"] == "healthy"
    assert checked[0]["health_message"] is not None
    assert "/chat/completions accepted model_key: ep-20260325082100-v7vs6" in checked[0]["health_message"]


@pytest.mark.asyncio
async def test_health_checker_healthy_when_models_list_contains_model_key(monkeypatch):
    class FakeResponse:
        def __init__(self, status_code: int, text: str = "", payload=None):
            self.status_code = status_code
            self.text = text
            self._payload = payload if payload is not None else []

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, path, headers=None):
            return FakeResponse(200, payload=[{"id": "chat-1"}, {"id": "other-model"}])

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

    assert checked[0]["health_status"] == "healthy"
    assert checked[0]["health_message"] == "GET /models contains model_key"


@pytest.mark.asyncio
async def test_embedder_uses_embedding_runtime_from_model_config(monkeypatch):
    created_clients: list[dict] = []

    class FakeLLMClient:
        def __init__(self, **kwargs):
            created_clients.append(kwargs)

        async def embed(self, text, **kwargs):
            return [0.1, 0.2, 0.3]

    monkeypatch.setattr("agent.rag.embedder.LLMClient", FakeLLMClient)

    embedder = Embedder(
        org_id="org-1",
        runtime_models=[
            {
                "id": "chat-cfg",
                "provider": "deepseek",
                "model_key": "deepseek-v4-flash",
                "endpoint": "https://api.deepseek.com",
                "api_key": "chat-key",
                "model_type": "chat",
                "is_active": True,
                "health_status": "healthy",
                "priority": 1,
            },
            {
                "id": "embed-cfg",
                "provider": "local_openai",
                "model_key": "bge-m3",
                "endpoint": "http://localhost:11434/v1",
                "api_key": None,
                "model_type": "embedding",
                "is_active": True,
                "health_status": "healthy",
                "priority": 2,
            },
        ],
    )

    assert await embedder.embed("hello") == [0.1, 0.2, 0.3]
    assert created_clients == [
        {
            "api_key": None,
            "base_url": "http://localhost:11434/v1",
            "model_id": "bge-m3",
            "embed_model": "bge-m3",
            "trace_id": None,
            "task_id": None,
            "org_id": "org-1",
            "provider": "local_openai",
            "input_price_per_million": None,
            "output_price_per_million": None,
        }
    ]


@pytest.mark.asyncio
async def test_embedder_reports_missing_model_config_page_embedding_model():
    embedder = Embedder(org_id="org-1", runtime_models=[])
    with pytest.raises(RuntimeError, match="embedding model.*model config page"):
        await embedder.embed("hello")


@pytest.mark.asyncio
async def test_embedder_falls_back_to_pseudo_vector_when_runtime_embedding_fails(monkeypatch):
    class FakeLLMClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def embed(self, text, **kwargs):
            raise RuntimeError("embedding api not supported")

    monkeypatch.setattr("agent.rag.embedder.LLMClient", FakeLLMClient)

    embedder = Embedder(
        org_id="org-1",
        runtime_models=[
            {
                "id": "embed-cfg",
                "provider": "volcengine",
                "model_key": "glm-4-7-251222",
                "endpoint": "https://ark.example.com/api/v3",
                "api_key": "secret",
                "model_type": "embedding",
                "is_active": True,
                "health_status": "healthy",
                "priority": 1,
            },
        ],
    )

    vector = await embedder.embed("pseudo fallback sample")

    assert isinstance(vector, list)
    assert len(vector) == 256
    assert any(abs(value) > 0 for value in vector)


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
                "trace": {"trace_id": "trace-1", "trace_url": "https://langfuse.local/trace/trace-1", "model_key": "model-a"},
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
            "source_type": "inspection",
            "trace_id": "trace-1",
            "trace_url": "https://langfuse.local/trace/trace-1",
            "result_id": "result-1",
            "task_id": "task-1",
            "assistant_message_id": None,
            "session_id": None,
            "observation_id": None,
            "verdict": "fail",
            "model_key": "model-a",
            "total_tokens": 150,
            "feedback_count": 2,
            "thumbs_down_count": 1,
            "thumbs_up_count": 1,
            "last_score_value": 1.0,
            "last_score_at": "2026-03-24T11:00:00",
            "trust_score": 1.0,
            "hallucination_risk": 1.0,
            "overconfidence": None,
            "has_citation": False,
            "score_status": None,
            "review_model": None,
            "langfuse_status": "synced",
            "langfuse_synced": True,
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


@pytest.mark.asyncio
async def test_feedback_service_saves_message_feedback_for_visible_target(monkeypatch):
    saved_payloads = []

    class FakeScalarResult:
        def scalar_one_or_none(self):
            return object()

    class FakeSession:
        async def execute(self, _stmt):
            return FakeScalarResult()

    class FakeRepo:
        def __init__(self, _session):
            return None

        async def save_message_feedback(self, payload):
            saved_payloads.append(payload)
            return SimpleNamespace(**payload)

    monkeypatch.setattr("app.services.feedback_service.FeedbackRepository", FakeRepo)

    service = FeedbackService(FakeSession(), "org-1")
    feedback = await service.submit_message_feedback(
        "CHAT",
        "message-1",
        "user-1",
        {
            "feedback_type": "down",
            "rating": 1,
            "category": "not_helpful",
            "comment": "from action bar",
        },
    )

    assert feedback.target_type == "chat"
    assert feedback.target_id == "message-1"
    assert feedback.actor_id == "user-1"
    assert saved_payloads[0]["org_id"] == "org-1"
    assert saved_payloads[0]["feedback_type"] == "down"


@pytest.mark.asyncio
async def test_feedback_service_rejects_message_feedback_without_visible_target(monkeypatch):
    class FakeScalarResult:
        def scalar_one_or_none(self):
            return None

    class FakeSession:
        async def execute(self, _stmt):
            return FakeScalarResult()

    class FakeRepo:
        def __init__(self, _session):
            return None

        async def save_message_feedback(self, _payload):
            raise AssertionError("invisible messages must not be saved")

    monkeypatch.setattr("app.services.feedback_service.FeedbackRepository", FakeRepo)

    service = FeedbackService(FakeSession(), "org-1")
    with pytest.raises(NotFoundError):
        await service.submit_message_feedback(
            "meeting",
            "message-1",
            "user-1",
            {
                "feedback_type": "up",
                "rating": 5,
                "category": "helpful",
                "comment": None,
            },
        )


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


def test_build_auth_claims_for_app_developer():
    claims = build_auth_claims("app_developer", "premium")
    assert claims.role == "app_developer"
    assert claims.roles == ["app_developer"]
    assert claims.default_workspace == WORKSPACE_OPS
    assert claims.workspaces == [WORKSPACE_OPS]
    assert CAPABILITY_CUSTOM_WORKFLOW in claims.capabilities


def test_build_auth_claims_for_governance_role():
    claims = build_auth_claims("algorithm_engineer", "expert")
    assert claims.default_workspace == WORKSPACE_GOVERNANCE
    assert WORKSPACE_GOVERNANCE in claims.workspaces


def test_standard_service_blocks_auto_pass_without_spec():
    result = InspectionStandardService._evaluate_loaded_spec(
        spec=SimpleNamespace(
            spec_code="SCREW-A-2026-V1",
            name="螺钉标准",
            version="2026.1",
            product_id="screw",
            product_family="fastener",
            applicable_skus=[],
            required_views=[],
            effective_from=None,
            effective_to=None,
            required_image_count=1,
            aggregation_rules={},
            ai_gate_rules={},
            manual_review_policies={},
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
        product_family="fastener",
        applicable_skus=[],
        required_views=[],
        effective_from=None,
        effective_to=None,
        required_image_count=1,
        aggregation_rules={},
        ai_gate_rules={},
        manual_review_policies={},
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


def test_analytics_normalizes_color_risk_levels():
    assert AnalyticsRepository._normalize_risk_level("green") == "low"
    assert AnalyticsRepository._normalize_risk_level("yellow") == "medium"
    assert AnalyticsRepository._normalize_risk_level("orange") == "high"
    assert AnalyticsRepository._normalize_risk_level("red") == "critical"
    assert AnalyticsRepository._normalize_risk_level("severe") == "critical"


def test_analytics_risk_distribution_trend_maps_historical_colors():
    repo = AnalyticsRepository(None)
    items = [
        SimpleNamespace(created_at=datetime(2026, 4, 5, 10, 0, 0), risk_level="green"),
        SimpleNamespace(created_at=datetime(2026, 4, 5, 10, 5, 0), risk_level="red"),
        SimpleNamespace(created_at=datetime(2026, 4, 5, 10, 10, 0), risk_level="yellow"),
        SimpleNamespace(created_at=datetime(2026, 4, 5, 10, 20, 0), risk_level="orange"),
    ]

    trend = repo._build_risk_distribution_trend(items, lambda item: item.created_at)

    assert trend == [
        {
            "bucket": "2026-04-05",
            "low": 1.0,
            "medium": 1.0,
            "high": 1.0,
            "critical": 1.0,
        }
    ]


def test_langfuse_tracer_starts_trace_and_syncs_score(monkeypatch):
    class FakeLangfuseClient:
        def __init__(self):
            self.trace_calls = []
            self.score_calls = []
            self.flushed = False

        def create_trace_id(self, seed=None):
            return "trace-123"

        def get_trace_url(self, trace_id=None):
            return f"https://langfuse.local/trace/{trace_id}"

        def trace(self, **kwargs):
            self.trace_calls.append(kwargs)

        def create_score(self, **kwargs):
            self.score_calls.append(kwargs)

        def flush(self):
            self.flushed = True

    fake = FakeLangfuseClient()
    monkeypatch.setattr("agent.llm.langfuse_tracer._get_langfuse_client", lambda: fake)

    tracer = LangfuseTracer()
    trace = tracer.start_trace(task_id="task-1", org_id="org-1", model_key="model-a")
    assert trace["trace_id"] == "trace-123"
    assert trace["trace_url"] == "https://langfuse.local/trace/trace-123"
    assert fake.trace_calls[0]["id"] == "trace-123"

    score = tracer.score(trace_id="trace-123", name="user_feedback", value=0.8, comment="ok")
    synced = tracer.sync_score(score)
    assert synced["synced"] is True
    assert fake.score_calls[0]["trace_id"] == "trace-123"
    assert fake.flushed is True


def test_langfuse_tracer_trace_exists_uses_trace_api(monkeypatch):
    class FakeTraceApi:
        def __init__(self):
            self.calls = []

        def get(self, trace_id, fields=None):
            self.calls.append({"trace_id": trace_id, "fields": fields})
            return {"id": trace_id}

    fake_trace_api = FakeTraceApi()
    fake = SimpleNamespace(api=SimpleNamespace(trace=fake_trace_api))
    monkeypatch.setattr("agent.llm.langfuse_tracer._get_langfuse_client", lambda: fake)

    assert LangfuseTracer().trace_exists("trace-123") is True
    assert fake_trace_api.calls == [{"trace_id": "trace-123", "fields": "id"}]


def test_langfuse_tracer_trace_exists_returns_false_for_not_found(monkeypatch):
    class NotFoundError(Exception):
        status_code = 404

    class FakeTraceApi:
        def get(self, trace_id, fields=None):
            raise NotFoundError("trace not found")

    fake = SimpleNamespace(api=SimpleNamespace(trace=FakeTraceApi()))
    monkeypatch.setattr("agent.llm.langfuse_tracer._get_langfuse_client", lambda: fake)

    assert LangfuseTracer().trace_exists("deleted-trace") is False


def test_langfuse_tracer_trace_exists_returns_none_without_client(monkeypatch):
    monkeypatch.setattr("agent.llm.langfuse_tracer._get_langfuse_client", lambda: None)

    assert LangfuseTracer().trace_exists("trace-123") is None


@pytest.mark.asyncio
async def test_llm_client_chat_records_langfuse_metadata(monkeypatch):
    class FakeObservation:
        def __init__(self):
            self.updates = []

        def update(self, **kwargs):
            self.updates.append(kwargs)

    class FakeObservationContext:
        def __init__(self, observation):
            self._observation = observation

        def __enter__(self):
            return self._observation

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeTracer:
        enabled = True

        def __init__(self):
            self.observation = FakeObservation()
            self.observe_calls = []

        def create_trace_id(self):
            return "trace-generated"

        def observe(self, **kwargs):
            self.observe_calls.append(kwargs)
            return FakeObservationContext(self.observation)

        def current_observation_id(self):
            return "obs-1"

        def get_trace_url(self, trace_id):
            return f"https://langfuse.local/trace/{trace_id}"

    class FakeResponse:
        def __init__(self):
            self.status_code = 200
            self.is_error = False
            self.request = object()

        def json(self):
            return {
                "id": "resp-1",
                "model": "chat-1",
                "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
                "choices": [
                    {
                        "message": {
                            "content": '{"verdict":"pass","overall_score":0.9,"reasoning_chain":{"summary":"ok"}}'
                        }
                    }
                ],
            }

    class FakeHttpClient:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, path, json=None, headers=None):
            self.path = path
            self.json_payload = json
            self.headers = headers
            return FakeResponse()

    fake_tracer = FakeTracer()
    monkeypatch.setattr("agent.llm.client.LangfuseTracer", lambda: fake_tracer)
    monkeypatch.setattr("agent.llm.client.httpx.AsyncClient", FakeHttpClient)

    client = LLMClient(
        api_key="secret",
        base_url="https://example.com/api/v3",
        model_id="chat-1",
        trace_id="trace-1",
        task_id="task-1",
        org_id="org-1",
        provider="volcengine",
    )
    data = await client.chat(
        [{"role": "user", "content": "hi"}],
        observation_name="inspection.reasoning",
    )

    assert data["__meta__"]["langfuse"] == {
        "trace_id": "trace-1",
        "trace_url": "https://langfuse.local/trace/trace-1",
        "observation_id": "obs-1",
    }
    assert fake_tracer.observe_calls[0]["trace_id"] == "trace-1"
    assert fake_tracer.observe_calls[0]["name"] == "inspection.reasoning"
    assert fake_tracer.observation.updates[0]["metadata"]["usage"]["total_tokens"] == 10


@pytest.mark.asyncio
async def test_llm_client_chat_no_response_format(monkeypatch):
    """chat() payloads must NOT include response_format – it breaks tool use and non-OpenAI models."""

    class FakeObservation:
        def update(self, **kwargs):
            return None

    class FakeObservationContext:
        def __enter__(self):
            return FakeObservation()

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeTracer:
        enabled = True

        def create_trace_id(self):
            return "trace-generated"

        def observe(self, **kwargs):
            return FakeObservationContext()

        def current_observation_id(self):
            return "obs-1"

        def get_trace_url(self, trace_id):
            return f"https://langfuse.local/trace/{trace_id}"

    class FakeResponse:
        status_code = 200
        is_error = False
        request = object()

        def json(self):
            return {
                "id": "resp-1",
                "model": "chat-1",
                "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
                "choices": [
                    {
                        "message": {
                            "content": '{"verdict":"pass","overall_score":0.9}'
                        }
                    }
                ],
            }

    class FakeHttpClient:
        calls: list[dict] = []

        def __init__(self, *args, **kwargs):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, path, json=None, headers=None):
            self.calls.append({"path": path, "json": json, "headers": headers})
            return FakeResponse()

    monkeypatch.setattr("agent.llm.client.LangfuseTracer", lambda: FakeTracer())
    monkeypatch.setattr("agent.llm.client.httpx.AsyncClient", FakeHttpClient)

    client = LLMClient(
        api_key="secret",
        base_url="https://example.com/api/v3",
        model_id="chat-1",
        trace_id="trace-1",
    )
    data = await client.chat([{"role": "user", "content": "hi"}])

    assert data["verdict"] == "pass"
    assert "response_format" not in FakeHttpClient.calls[0]["json"]
    assert FakeHttpClient.calls[0]["json"]["model"] == "chat-1"


@pytest.mark.asyncio
async def test_llm_client_chat_with_tools_no_response_format(monkeypatch):
    """chat_with_tools payload must include tools but NOT response_format."""

    class FakeObservation:
        def update(self, **kwargs):
            return None

    class FakeObservationContext:
        def __enter__(self):
            return FakeObservation()

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeTracer:
        enabled = True

        def create_trace_id(self):
            return "trace-generated"

        def observe(self, **kwargs):
            return FakeObservationContext()

        def current_observation_id(self):
            return "obs-1"

        def get_trace_url(self, trace_id):
            return f"https://langfuse.local/trace/{trace_id}"

    class FakeResponse:
        status_code = 200
        is_error = False
        request = object()

        def json(self):
            return {
                "id": "resp-1",
                "model": "chat-1",
                "choices": [{"message": {"content": '{"answer":"ok"}'}}],
            }

    class FakeHttpClient:
        calls: list[dict] = []

        def __init__(self, *args, **kwargs):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, path, json=None, headers=None):
            self.calls.append({"path": path, "json": json, "headers": headers})
            return FakeResponse()

    monkeypatch.setattr("agent.llm.client.LangfuseTracer", lambda: FakeTracer())
    monkeypatch.setattr("agent.llm.client.httpx.AsyncClient", FakeHttpClient)

    client = LLMClient(api_key="secret", base_url="https://example.com/api/v3", model_id="chat-1")
    await client.chat_with_tools(
        [{"role": "system", "content": "你是智能助手。"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "web.search",
                    "description": "search",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
    )

    payload = FakeHttpClient.calls[0]["json"]
    assert "response_format" not in payload
    assert payload["tools"][0]["type"] == "function"
    assert payload["tool_choice"] == "auto"


@pytest.mark.asyncio
async def test_llm_client_embed_raises_on_connect_error(monkeypatch):
    class FakeHttpClient:
        def __init__(self, *args, **kwargs):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, path, json=None, headers=None):
            raise httpx.ConnectError("connect failed")

    monkeypatch.setattr("agent.llm.client.httpx.AsyncClient", FakeHttpClient)

    client = LLMClient(api_key="secret", base_url="https://example.com/api/v3", embed_model="embed-1")
    with pytest.raises(httpx.ConnectError):
        await client.embed("hello")


@pytest.mark.asyncio
async def test_run_vision_records_runtime_error_on_invalid_payload(monkeypatch):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            return None

        @staticmethod
        def _extract_json_object(text: str):
            return None

        async def chat(self, *args, **kwargs):
            return {"text": "not a structured defect payload"}

    monkeypatch.setattr("agent.subgraphs.inspection_task.nodes.vision.LLMClient", FakeClient)

    state = await run_vision(
        {
            "task_id": "task-1",
            "org_id": "org-1",
            "image_urls": ["https://example.com/a.png"],
            "model_id": "chat-1",
            "model_base_url": "https://example.com/api/v3",
            "model_api_key": "secret",
            "model_provider": "volcengine",
            "trace_id": "trace-1",
            "timeline": [],
            "usage_events": [],
            "runtime_errors": [],
        }
    )

    assert state["defects"] == []
    assert state["runtime_errors"][0]["stage"] == "vision"
    assert "structured defects payload" in state["runtime_errors"][0]["message"]


@pytest.mark.asyncio
async def test_inspection_graph_stops_after_runtime_error(monkeypatch):
    calls: list[str] = []

    async def fake_plan(state):
        calls.append("planner")
        return state

    async def fake_vision(state):
        calls.append("vision")
        state.setdefault("runtime_errors", []).append({"stage": "vision", "message": "boom"})
        return state

    async def fake_knowledge(state):
        calls.append("knowledge")
        return state

    async def fake_reasoning(state):
        calls.append("reasoning")
        return state

    async def fake_finalize(state):
        calls.append("finalizer")
        return state

    monkeypatch.setattr("agent.subgraphs.inspection_task.graph.plan", fake_plan)
    monkeypatch.setattr("agent.subgraphs.inspection_task.graph.run_vision", fake_vision)
    monkeypatch.setattr("agent.subgraphs.inspection_task.graph.run_knowledge", fake_knowledge)
    monkeypatch.setattr("agent.subgraphs.inspection_task.graph.run_reasoning", fake_reasoning)
    monkeypatch.setattr("agent.subgraphs.inspection_task.graph.finalize", fake_finalize)

    state = await InspectionGraph().run({"timeline": [], "runtime_errors": []})

    assert state["runtime_errors"][0]["message"] == "boom"
    assert calls == ["planner", "vision"]


@pytest.mark.asyncio
async def test_inspection_graph_event_stream_follows_stage_execution_order(monkeypatch):
    async def fake_node(stage: str):
        async def _run(state):
            state.setdefault("timeline", []).append({"stage": stage, "message": f"{stage} done"})
            return state

        return _run

    monkeypatch.setattr("agent.subgraphs.inspection_task.graph.plan", await fake_node("planner"))
    monkeypatch.setattr("agent.subgraphs.inspection_task.graph.run_vision", await fake_node("vision"))
    monkeypatch.setattr("agent.subgraphs.inspection_task.graph.run_knowledge", await fake_node("knowledge"))
    monkeypatch.setattr("agent.subgraphs.inspection_task.graph.run_reasoning", await fake_node("reasoning"))
    monkeypatch.setattr("agent.subgraphs.inspection_task.graph.finalize", await fake_node("finalizer"))

    events: list[dict] = []

    async def on_event(event):
        events.append(event)

    state = await InspectionGraph().run({"timeline": [], "runtime_errors": []}, on_event=on_event)

    assert [item["stage"] for item in state["timeline"]] == [
        "planner",
        "vision",
        "knowledge",
        "reasoning",
        "finalizer",
    ]
    assert [(item["type"], item["stage"]) for item in events] == [
        ("stage_start", "planner"),
        ("stage_end", "planner"),
        ("stage_start", "vision"),
        ("stage_end", "vision"),
        ("stage_start", "knowledge"),
        ("stage_end", "knowledge"),
        ("stage_start", "reasoning"),
        ("stage_end", "reasoning"),
        ("stage_start", "finalizer"),
        ("stage_end", "finalizer"),
    ]


def test_langfuse_trace_to_item_parses_inspection_trace():
    trace = {
        "id": "trace-1",
        "timestamp": "2026-05-16T10:00:00Z",
        "sessionId": "task-1",
        "metadata": {
            "source_type": "inspection",
            "verdict": "fail",
            "model_key": "model-a",
            "task_id": "task-1",
            "org_id": "org-1",
        },
        "scores": [
            {"name": "trust_score", "value": 0.85, "timestamp": "2026-05-16T10:01:00Z"},
            {"name": "hallucination_risk", "value": 0.1, "timestamp": "2026-05-16T10:01:00Z"},
            {"name": "overconfidence", "value": 0.15, "timestamp": "2026-05-16T10:01:00Z"},
            {"name": "user_feedback", "value": 0.8, "timestamp": "2026-05-16T10:02:00Z"},
        ],
        "observations": [
            {"id": "obs-1", "type": "GENERATION", "model": "model-a", "usage": {"total": 150}}
        ],
    }
    item = QualityReportService._langfuse_trace_to_item(trace, api_client=None)
    assert item is not None
    assert item["trace_id"] == "trace-1"
    assert item["source_type"] == "inspection"
    assert item["verdict"] == "fail"
    assert item["model_key"] == "model-a"
    assert item["trust_score"] == 0.85
    assert item["hallucination_risk"] == 0.1
    assert item["overconfidence"] == 0.15
    assert item["total_tokens"] == 150
    assert item["feedback_count"] == 1
    assert item["langfuse_status"] == "synced"
    assert item["langfuse_synced"] is True


def test_langfuse_trace_to_item_parses_chat_trace():
    trace = {
        "id": "trace-2",
        "timestamp": "2026-05-16T11:00:00Z",
        "sessionId": "session-1",
        "metadata": {"source_type": "chat", "model_key": "quality_chat_v2"},
        "scores": [
            {
                "name": "trust_score",
                "value": 0.61,
                "timestamp": "2026-05-16T11:01:00Z",
                "comment": '{"review_model":"doubao-seed-2-0-mini-260428"}',
            },
            {"name": "has_citation", "value": 1, "timestamp": "2026-05-16T11:01:00Z"},
        ],
        "observations": [
            {"id": "obs-1", "type": "GENERATION", "model": "doubao-seed-2-0-mini-260428", "usage": {"total": 88}}
        ],
    }
    item = QualityReportService._langfuse_trace_to_item(trace, api_client=None)
    assert item is not None
    assert item["source_type"] == "chat"
    assert item["model_key"] == "doubao-seed-2-0-mini-260428"
    assert item["has_citation"] is True
    assert item["total_tokens"] == 88
    assert item["trust_score"] == 0.61
    assert item["review_model"] == "doubao-seed-2-0-mini-260428"


def test_langfuse_trace_to_item_accepts_observation_ids_from_list_api():
    trace = {
        "id": "trace-ids",
        "timestamp": "2026-05-16T11:30:00Z",
        "metadata": {"source_type": "chat", "model_key": "chat-model-c"},
        "scores": [],
        "observations": ["obs-id-1"],
    }

    item = QualityReportService._langfuse_trace_to_item(trace, api_client=None)

    assert item is not None
    assert item["trace_id"] == "trace-ids"
    assert item["observation_id"] == "obs-id-1"
    assert item["total_tokens"] == 0


def test_langfuse_trace_to_item_accepts_score_ids_from_list_api():
    trace = {
        "id": "trace-score-ids",
        "timestamp": "2026-05-16T11:40:00Z",
        "metadata": {"source_type": "chat", "model_key": "chat-model-d"},
        "scores": ["score-id-1"],
        "observations": ["obs-id-1"],
    }

    item = QualityReportService._langfuse_trace_to_item(trace, api_client=None)

    assert item is not None
    assert item["trace_id"] == "trace-score-ids"
    assert item["observation_id"] == "obs-id-1"
    assert item["trust_score"] is None
    assert item["score_status"] is None


def test_start_trace_includes_source_type_and_tags(monkeypatch):
    class FakeClient:
        def __init__(self):
            self.trace_calls = []

        def create_trace_id(self, seed=None):
            return "trace-t1"

        def get_trace_url(self, trace_id=None):
            return f"https://langfuse.local/trace/{trace_id}"

        def trace(self, **kwargs):
            self.trace_calls.append(kwargs)

    fake = FakeClient()
    monkeypatch.setattr("agent.llm.langfuse_tracer._get_langfuse_client", lambda: fake)

    tracer = LangfuseTracer()
    trace = tracer.start_trace(
        task_id="task-1", org_id="org-1", model_key="model-a",
        source_type="inspection", verdict="pass",
    )
    assert trace["source_type"] == "inspection"
    call = fake.trace_calls[0]
    assert call["metadata"]["source_type"] == "inspection"
    assert call["metadata"]["verdict"] == "pass"
    assert "source_type:inspection" in call["tags"]
    assert "org_id:org-1" in call["tags"]


def test_start_trace_creates_v4_observation_when_trace_factory_missing(monkeypatch):
    class FakeObservation:
        def update(self, **kwargs):
            self.updated = kwargs

    class FakeObservationContext:
        def __init__(self, owner, kwargs):
            self.owner = owner
            self.kwargs = kwargs

        def __enter__(self):
            self.owner.observation_calls.append(self.kwargs)
            return FakeObservation()

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeClient:
        def __init__(self):
            self.observation_calls = []
            self.flushed = False

        def create_trace_id(self, seed=None):
            return "trace-v4"

        def get_trace_url(self, trace_id=None):
            return f"https://langfuse.local/trace/{trace_id}"

        def start_as_current_observation(self, **kwargs):
            return FakeObservationContext(self, kwargs)

        def flush(self):
            self.flushed = True

    fake = FakeClient()
    monkeypatch.setattr("agent.llm.langfuse_tracer._get_langfuse_client", lambda: fake)

    trace = LangfuseTracer().start_trace(
        task_id="session-1",
        org_id="org-1",
        model_key="quality_chat_v2",
        name="quality_chat_v2",
        source_type="chat",
        input={"query": "hello"},
    )

    assert trace["trace_id"] == "trace-v4"
    assert fake.flushed is True
    assert fake.observation_calls == [
        {
            "name": "quality_chat_v2",
            "as_type": "span",
            "trace_context": {"trace_id": "trace-v4"},
            "input": {"query": "hello"},
            "metadata": {
                "task_id": "session-1",
                "org_id": "org-1",
                "model_key": "quality_chat_v2",
                "source_type": "chat",
                "agent": "",
                "sub_route": "",
                "intent": "",
                "prompt_version": "",
                "workflow_version": "",
                "session_id": "",
                "route_source": "",
                "route_confidence": 0.0,
            },
        }
    ]
