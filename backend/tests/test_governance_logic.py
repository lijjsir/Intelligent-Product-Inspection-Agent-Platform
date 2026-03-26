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
from agent.graph.inspection_graph import InspectionGraph
from agent.graph.nodes.vision import run_vision
from agent.llm.client import LLMClient
from agent.llm.gateway import LLMGateway
from agent.llm.health_checker import ModelHealthChecker
from agent.llm.langfuse_tracer import LangfuseTracer
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
            "trace_id": "trace-1",
            "trace_url": "https://langfuse.local/trace/trace-1",
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
    assert fake_tracer.observation.updates[0]["usage_details"]["total_tokens"] == 10


@pytest.mark.asyncio
async def test_llm_client_chat_retries_without_response_format(monkeypatch):
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
        def __init__(self, status_code: int, body: dict, text: str | None = None):
            self.status_code = status_code
            self._body = body
            self._text = text or json.dumps(body)
            self.is_error = status_code >= 400
            self.request = object()

        def json(self):
            return self._body

        @property
        def text(self):
            return self._text

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
            if len(self.calls) == 1:
                return FakeResponse(
                    400,
                    {
                        "error": {
                            "code": "InvalidParameter",
                            "message": "The parameter `response_format.type` specified in the request are not valid: `json_object` is not supported by this model.",
                        }
                    },
                    text='{"error":{"code":"InvalidParameter","message":"The parameter `response_format.type` specified in the request are not valid: `json_object` is not supported by this model."}}',
                )
            return FakeResponse(
                200,
                {
                    "id": "resp-2",
                    "model": "chat-1",
                    "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
                    "choices": [
                        {
                            "message": {
                                "content": '{"verdict":"pass","overall_score":0.9,"reasoning_chain":{"summary":"ok"}}'
                            }
                        }
                    ],
                },
            )

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
    assert FakeHttpClient.calls[0]["json"]["response_format"] == {"type": "json_object"}
    assert "response_format" not in FakeHttpClient.calls[1]["json"]


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

    monkeypatch.setattr("agent.graph.nodes.vision.LLMClient", FakeClient)

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

    monkeypatch.setattr("agent.graph.inspection_graph.plan", fake_plan)
    monkeypatch.setattr("agent.graph.inspection_graph.run_vision", fake_vision)
    monkeypatch.setattr("agent.graph.inspection_graph.run_knowledge", fake_knowledge)
    monkeypatch.setattr("agent.graph.inspection_graph.run_reasoning", fake_reasoning)
    monkeypatch.setattr("agent.graph.inspection_graph.finalize", fake_finalize)

    state = await InspectionGraph().run({"timeline": [], "runtime_errors": []})

    assert state["runtime_errors"][0]["message"] == "boom"
    assert calls == ["planner", "vision"]
