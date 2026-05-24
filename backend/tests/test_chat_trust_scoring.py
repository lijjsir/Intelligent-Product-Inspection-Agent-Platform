from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from agent.llm.client import LLMClient
from agent.llm.pricing import ModelPricing
from app.services.chat_trust_scoring_service import (
    ChatTrustScoringService,
    build_pending_trust_score,
    combine_trust_scores,
    extract_json_object,
    normalize_llm_score,
    score_output_rule,
    trust_payload_from_score,
)
from worker.tasks.chat_trust_scoring_task import _resolve_review_config
from app.services.langfuse_api_client import LangfuseApiError
from app.services.analytics_service import AnalyticsService
from app.services.quality_report_service import QualityReportService


def test_rule_score_flags_certain_answer_without_citations():
    score = score_output_rule(
        input_text="Is this product acceptable?",
        output_text="It is absolutely compliant. The defect count is 100% within limit.",
        citations=[],
    )

    assert score["has_citation"] == 0
    assert score["hallucination_risk"] >= 0.5
    assert score["overconfidence"] >= 0.5


def test_rule_score_matches_utf8_chinese_certainty_and_citation_terms():
    score = score_output_rule(
        input_text="这批产品是否合格？",
        output_text="该批次绝对符合标准，所有检测项完全正确。来源：GB/T 2828.1。",
        citations=[],
    )

    assert score["has_citation"] == 1
    assert score["overconfidence"] >= 0.5


def test_extract_json_object_accepts_markdown_wrapped_reviewer_output():
    parsed = extract_json_object(
        """The review is below.
```json
{"hallucination_risk_llm": 0.7, "overconfidence_llm": 0.4, "has_citation_llm": 1, "reasons": ["missing source detail"]}
```"""
    )

    assert parsed["hallucination_risk_llm"] == 0.7


def test_normalize_llm_score_clamps_values_and_reasons():
    normalized = normalize_llm_score(
        {
            "hallucination_risk_llm": 9,
            "overconfidence_llm": -3,
            "has_citation_llm": "true",
            "reasons": ["a", "b", "c", "d"],
        }
    )

    assert normalized == {
        "hallucination_risk_llm": 1.0,
        "overconfidence_llm": 0.0,
        "has_citation_llm": 1,
        "reasons": ["a", "b", "c"],
    }


def test_combine_trust_scores_returns_lightweight_payload():
    combined = combine_trust_scores(
        rule_score={"hallucination_risk": 0.6, "overconfidence": 0.4, "has_citation": 0},
        llm_score={"hallucination_risk_llm": 0.2, "overconfidence_llm": 0.8, "has_citation_llm": 1},
    )

    assert combined["trust_score"] == 0.5
    assert combined["risk_level"] == "medium"
    assert combined["hallucination_risk"] == 0.4
    assert combined["overconfidence"] == 0.6
    assert combined["has_citation"] == 1


def test_model_pricing_covers_current_chat_and_review_models():
    assert ModelPricing.estimate_cost("deepseek-v4-flash", 1000, 1000) > 0


def test_pending_trust_score_keeps_final_score_empty_while_preserving_rule_signal(monkeypatch):
    monkeypatch.setattr("app.services.chat_trust_scoring_service.LangfuseTracer", lambda: None)

    score = build_pending_trust_score(
        org_id="11111111-1111-1111-1111-111111111111",
        session_id="22222222-2222-2222-2222-222222222222",
        user_id="33333333-3333-3333-3333-333333333333",
        assistant_message_id="44444444-4444-4444-4444-444444444444",
        input_text="这批产品是否合格？",
        output_text="该批次绝对符合标准，所有检测项完全正确。",
        citations=[],
        trace_id="trace-1",
        observation_id="obs-1",
        model_key="local-model",
    )

    assert score["status"] == "reviewing"
    assert score["trust_score"] is None
    assert score["rule_scores"]["overconfidence"] >= 0.5
    assert trust_payload_from_score(score)["trust_score"] is None


@pytest.mark.asyncio
async def test_trust_scoring_service_falls_back_to_rule_only_when_reviewer_fails(monkeypatch):
    async def fail_review(*args, **kwargs):
        raise RuntimeError("ollama unavailable")

    synced_scores: list[dict] = []

    class FakeTracer:
        def get_trace_url(self, trace_id):
            return f"http://127.0.0.1:3000/project/x/traces/{trace_id}"

        def score(self, **kwargs):
            return dict(kwargs, ok=True, synced=False)

        def sync_score(self, payload):
            synced_scores.append(payload)
            return dict(payload, synced=True, trace_url="http://127.0.0.1:3000/project/x/traces/trace-1")

    monkeypatch.setattr(ChatTrustScoringService, "_call_reviewer", fail_review)
    monkeypatch.setattr("app.services.chat_trust_scoring_service.LangfuseTracer", lambda: FakeTracer())

    result = await ChatTrustScoringService().score_answer(
        org_id="11111111-1111-1111-1111-111111111111",
        session_id="22222222-2222-2222-2222-222222222222",
        user_id="33333333-3333-3333-3333-333333333333",
        assistant_message_id="44444444-4444-4444-4444-444444444444",
        input_text="Question",
        output_text="This is definitely correct.",
        citations=[],
        trace_id="trace-1",
        observation_id="obs-1",
        model_key="local-model",
    )

    assert result["status"] == "rule_only"
    assert result["trust_score"] is None
    assert result["hallucination_risk"] is None
    assert result["overconfidence"] is None
    assert result["has_citation"] is None
    assert result["trace_url"] == "http://127.0.0.1:3000/project/x/traces/trace-1"
    assert synced_scores == []


@pytest.mark.asyncio
async def test_trust_scoring_service_passes_runtime_model_config_to_reviewer(monkeypatch):
    created_clients: list[dict] = []

    class FakeLLMClient:
        def __init__(self, **kwargs):
            created_clients.append(kwargs)

        async def chat(self, *_args, **_kwargs):
            return {
                "hallucination_risk_llm": 0.2,
                "overconfidence_llm": 0.3,
                "has_citation_llm": 1,
                "reasons": ["configured reviewer used"],
            }

    class FakeTracer:
        def score(self, **kwargs):
            return dict(kwargs, ok=True, synced=False)

        def sync_score(self, payload):
            return dict(payload, synced=False)

    monkeypatch.setattr("app.services.chat_trust_scoring_service.LLMClient", FakeLLMClient)
    monkeypatch.setattr("app.services.chat_trust_scoring_service.LangfuseTracer", lambda: FakeTracer())

    result = await ChatTrustScoringService(
        review_provider="deepseek",
        review_model="deepseek-v4-flash",
        review_base_url="https://api.deepseek.com",
        review_api_key="sk-test",
        input_price_per_million=1.0,
        output_price_per_million=2.0,
    ).score_answer(
        org_id="11111111-1111-1111-1111-111111111111",
        session_id="22222222-2222-2222-2222-222222222222",
        user_id="33333333-3333-3333-3333-333333333333",
        assistant_message_id="44444444-4444-4444-4444-444444444444",
        input_text="Question",
        output_text="Answer with source: test.",
        citations=[],
        trace_id="trace-1",
        observation_id="obs-1",
        model_key="answer-model",
    )

    assert result["status"] == "scored"
    assert result["review_model"] == "deepseek-v4-flash"
    assert created_clients == [
        {
            "provider": "deepseek",
            "model_id": "deepseek-v4-flash",
            "base_url": "https://api.deepseek.com",
            "api_key": "sk-test",
            "input_price_per_million": 1.0,
            "output_price_per_million": 2.0,
        }
    ]


@pytest.mark.asyncio
async def test_trust_scoring_resolves_reviewer_from_tenant_model_config(monkeypatch):
    seen: dict[str, object] = {}

    class FakeModelConfigService:
        def __init__(self, session, org_id):
            seen["org_id"] = org_id

        async def list_runtime_models(self):
            return [
                {
                    "id": "deepseek-cfg",
                    "provider": "deepseek",
                    "model_key": "deepseek-v4-flash",
                    "endpoint": "https://api.deepseek.com",
                    "api_key": "sk-db",
                    "model_type": "chat",
                    "is_active": True,
                    "health_status": "healthy",
                    "priority": 1,
                    "input_price_per_million": 0.8,
                    "output_price_per_million": 1.6,
                }
            ]

    class FakeGateway:
        async def select_runtime(self, models, *, model_types=None, reserve=True, excluded_runtime_ids=None):
            seen["model_types"] = set(model_types or [])
            seen["reserve"] = reserve
            item = list(models)[0]
            return {
                "runtime_key": item["id"],
                "model_config_id": item["id"],
                "model_id": item["model_key"],
                "base_url": item["endpoint"],
                "api_key": item["api_key"],
                "provider": item["provider"],
                "input_price_per_million": item["input_price_per_million"],
                "output_price_per_million": item["output_price_per_million"],
                "rpm_limit": None,
                "failover_depth": 0,
            }

    monkeypatch.setattr("app.services.chat_trust_scoring_service.ModelConfigService", FakeModelConfigService)
    monkeypatch.setattr("app.services.chat_trust_scoring_service.LLMGateway", lambda: FakeGateway())

    resolved = await ChatTrustScoringService.resolve_review_model(object(), "org-1")

    assert seen == {"org_id": "org-1", "model_types": {"chat", "llm"}, "reserve": False}
    assert resolved == {
        "review_provider": "deepseek",
        "review_model": "deepseek-v4-flash",
        "review_base_url": "https://api.deepseek.com",
        "review_api_key": "sk-db",
        "input_price_per_million": 0.8,
        "output_price_per_million": 1.6,
    }


@pytest.mark.asyncio
async def test_worker_retries_review_model_resolution_after_transient_session_failure(monkeypatch):
    attempts = 0

    class FailingSessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            raise RuntimeError("Event loop is closed")

    class WorkingSessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    def fake_get_session():
        nonlocal attempts
        attempts += 1
        return FailingSessionContext() if attempts == 1 else WorkingSessionContext()

    async def fake_resolve(_session, org_id):
        return {"review_model": f"resolved-for-{org_id}"}

    monkeypatch.setattr("worker.tasks.chat_trust_scoring_task.get_session", fake_get_session)
    monkeypatch.setattr(ChatTrustScoringService, "resolve_review_model", fake_resolve)

    assert await _resolve_review_config("org-1") == {"review_model": "resolved-for-org-1"}
    assert attempts == 2


@pytest.mark.asyncio
async def test_llm_client_local_openai_allows_missing_api_key(monkeypatch):
    observation_updates: list[dict] = []

    class FakeObservation:
        def update(self, **kwargs):
            observation_updates.append(kwargs)

    class FakeObservationContext:
        def __enter__(self):
            return FakeObservation()

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeTracer:
        enabled = False

        def create_trace_id(self):
            return "trace-1"

        def observe(self, **kwargs):
            return FakeObservationContext()

        def current_observation_id(self):
            return "obs-1"

        def get_trace_url(self, trace_id):
            return f"http://langfuse.local/traces/{trace_id}"

    class FakeResponse:
        status_code = 200
        is_error = False
        request = object()

        def json(self):
            return {
                "id": "local-1",
                "model": "qwen2.5:7b-instruct",
                "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
                "choices": [{"message": {"content": '{"answer":"ok","summary":"done"}'}}],
            }

    class FakeHttpClient:
        calls: list[dict] = []

        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, path, json=None, headers=None):
            self.calls.append({"path": path, "json": json, "headers": headers, "base_url": self.kwargs.get("base_url")})
            return FakeResponse()

    monkeypatch.setattr("agent.llm.client.httpx.AsyncClient", FakeHttpClient)
    monkeypatch.setattr("agent.llm.client.LangfuseTracer", lambda: FakeTracer())

    client = LLMClient(provider="local_openai", base_url="http://localhost:11434/v1", model_id="qwen2.5:7b-instruct")
    data = await client.chat([{"role": "user", "content": "hi"}])

    assert data["answer"] == "ok"
    assert FakeHttpClient.calls[0]["base_url"] == "http://localhost:11434/v1"
    assert FakeHttpClient.calls[0]["headers"] == {}
    assert observation_updates[-1]["usage_details"] == {
        "prompt_tokens": 3,
        "completion_tokens": 4,
        "total_tokens": 7,
    }


@pytest.mark.asyncio
async def test_llm_client_cost_details_use_runtime_pricing(monkeypatch):
    observation_updates: list[dict] = []

    class FakeObservation:
        def update(self, **kwargs):
            observation_updates.append(kwargs)

    class FakeObservationContext:
        def __enter__(self):
            return FakeObservation()

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeTracer:
        enabled = False

        def create_trace_id(self):
            return "trace-1"

        def observe(self, **kwargs):
            return FakeObservationContext()

        def current_observation_id(self):
            return "obs-1"

        def get_trace_url(self, trace_id):
            return f"http://langfuse.local/traces/{trace_id}"

    class FakeResponse:
        status_code = 200
        is_error = False
        request = object()

        def json(self):
            return {
                "id": "runtime-1",
                "model": "custom-priced-model",
                "usage": {"prompt_tokens": 1000, "completion_tokens": 1000, "total_tokens": 2000},
                "choices": [{"message": {"content": '{"answer":"ok","summary":"done"}'}}],
            }

    class FakeHttpClient:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, path, json=None, headers=None):
            return FakeResponse()

    monkeypatch.setattr("agent.llm.client.httpx.AsyncClient", FakeHttpClient)
    monkeypatch.setattr("agent.llm.client.LangfuseTracer", lambda: FakeTracer())

    client = LLMClient(
        provider="local_openai",
        base_url="http://localhost:11434/v1",
        model_id="custom-priced-model",
        input_price_per_million=10.0,
        output_price_per_million=20.0,
    )
    await client.chat([{"role": "user", "content": "hi"}])

    assert observation_updates[-1]["cost_details"] == {"total_cost": 0.03}


def test_quality_trace_builder_merges_chat_scores():
    class Score:
        org_id = "org-1"
        assistant_message_id = "msg-1"
        session_id = "session-1"
        user_id = "user-1"
        trace_id = "trace-chat"
        observation_id = "obs-chat"
        trace_url = "http://127.0.0.1:3000/project/p/traces/trace-chat"
        model_key = "qwen2.5:7b-instruct"
        review_model = "qwen2.5:7b-instruct"
        trust_score = 0.82
        hallucination_risk = 0.2
        overconfidence = 0.1
        has_citation = True
        status = "scored"
        langfuse_synced_at = datetime(2026, 5, 13, 12, 0, 0)
        created_at = datetime(2026, 5, 13, 11, 0, 0)

    traces = QualityReportService._build_quality_traces([], [], [], limit=20, chat_scores=[Score()])

    assert traces == [
        {
            "source_type": "chat",
            "trace_id": "trace-chat",
            "trace_url": "http://127.0.0.1:3000/project/p/traces/trace-chat",
            "result_id": None,
            "task_id": None,
            "assistant_message_id": "msg-1",
            "session_id": "session-1",
            "observation_id": "obs-chat",
            "verdict": None,
            "model_key": "qwen2.5:7b-instruct",
            "total_tokens": 0,
            "feedback_count": 0,
            "thumbs_down_count": 0,
            "thumbs_up_count": 0,
            "last_score_value": 0.82,
            "last_score_at": datetime(2026, 5, 13, 12, 0, 0),
            "trust_score": 0.82,
            "hallucination_risk": 0.2,
            "overconfidence": 0.1,
            "has_citation": True,
            "score_status": "scored",
            "review_model": "qwen2.5:7b-instruct",
            "langfuse_status": "synced",
            "langfuse_synced": True,
            "created_at": datetime(2026, 5, 13, 11, 0, 0),
        }
    ]


def test_quality_trace_builder_marks_deleted_langfuse_trace_missing():
    class Score:
        org_id = "org-1"
        assistant_message_id = "msg-1"
        session_id = "session-1"
        user_id = "user-1"
        trace_id = "trace-chat"
        observation_id = "obs-chat"
        trace_url = "http://127.0.0.1:3000/project/p/traces/trace-chat"
        model_key = "qwen2.5:7b-instruct"
        review_model = "qwen2.5:7b-instruct"
        trust_score = 0.82
        hallucination_risk = 0.2
        overconfidence = 0.1
        has_citation = True
        status = "scored"
        langfuse_synced_at = datetime(2026, 5, 13, 12, 0, 0)
        created_at = datetime(2026, 5, 13, 11, 0, 0)

    traces = QualityReportService._build_quality_traces(
        [],
        [],
        [],
        limit=20,
        chat_scores=[Score()],
        langfuse_trace_exists=lambda trace_id: False,
    )

    assert traces[0]["langfuse_status"] == "missing"
    assert traces[0]["langfuse_synced"] is False
    assert traces[0]["trace_url"] is None


def test_quality_trace_builder_attaches_chat_token_ledger_by_trace():
    class Score:
        org_id = "org-1"
        assistant_message_id = "msg-1"
        session_id = "session-1"
        user_id = "user-1"
        trace_id = "trace-chat"
        observation_id = "obs-chat"
        trace_url = "http://127.0.0.1:3000/project/p/traces/trace-chat"
        model_key = "deepseek-v4-flash"
        review_model = "deepseek-v4-flash"
        trust_score = 0.82
        hallucination_risk = 0.2
        overconfidence = 0.1
        has_citation = True
        status = "scored"
        langfuse_synced_at = datetime(2026, 5, 13, 12, 0, 0)
        created_at = datetime(2026, 5, 13, 11, 0, 0)

    class Ledger:
        result_id = None
        trace_id = "trace-chat"
        total_tokens = 123

    traces = QualityReportService._build_quality_traces([], [], [Ledger()], limit=20, chat_scores=[Score()])

    assert traces[0]["total_tokens"] == 123


@pytest.mark.asyncio
async def test_quality_trace_list_uses_langfuse_api_for_chat_source(monkeypatch):
    class FakeApiClient:
        enabled = True

        async def list_traces(self, *, page=1, limit=50, tags=None):
            return {
                "data": [
                    {
                        "id": "trace-chat",
                        "timestamp": "2026-05-14T08:00:00Z",
                        "sessionId": "session-1",
                        "metadata": {"source_type": "chat", "model_key": "doubao-seed-2-0-pro-260215"},
                        "scores": [
                            {"name": "trust_score", "value": 0.355},
                            {"name": "hallucination_risk", "value": 0.725},
                            {"name": "overconfidence", "value": 0.21},
                        ],
                        "observations": [
                            {"id": "obs-1", "type": "GENERATION", "model": "doubao-seed-2-0-pro-260215", "usage": {"total": 327}}
                        ],
                    }
                ],
                "meta": {"page": 1, "limit": 50, "totalItems": 1, "totalPages": 1},
            }

        def build_trace_url(self, trace_id):
            return f"http://127.0.0.1:3000/project/p/traces/{trace_id}"

    monkeypatch.setattr(
        "app.services.quality_report_service.LangfuseApiClient",
        lambda: FakeApiClient(),
    )

    class EmptyRepo:
        async def list_by_range(self, *_args, **_kwargs):
            return []

        async def list_message_by_range(self, *_args, **_kwargs):
            return []

    class EmptyLedgerRepo:
        async def list_filtered(self, *_args, **_kwargs):
            return []

    class EmptyChatMessageRepo:
        async def list_assistant_for_org(self, *_args, **_kwargs):
            return []

    service = QualityReportService(session=object(), org_id="org-1")
    service._result_repo = EmptyRepo()
    service._feedback_repo = EmptyRepo()
    service._token_ledger_repo = EmptyLedgerRepo()
    service._chat_score_repo = EmptyRepo()
    service._chat_message_repo = EmptyChatMessageRepo()
    traces = await service.list_traces(source="chat")

    assert len(traces) == 1
    assert traces[0]["source_type"] == "chat"
    assert traces[0]["total_tokens"] == 327
    assert traces[0]["trust_score"] == 0.355


@pytest.mark.asyncio
async def test_quality_trace_list_hydrates_score_ids_from_langfuse_api(monkeypatch):
    class FakeApiClient:
        enabled = True

        async def list_traces(self, *, page=1, limit=50, tags=None):
            return {
                "data": [
                    {
                        "id": "trace-chat",
                        "timestamp": "2026-05-14T08:00:00Z",
                        "sessionId": "session-1",
                        "metadata": {"source_type": "chat", "model_key": "chat-model"},
                        "scores": ["score-trust", "score-risk"],
                        "observations": ["obs-1"],
                    }
                ],
                "meta": {"page": 1, "limit": 50, "totalItems": 1, "totalPages": 1},
            }

        async def get_trace(self, trace_id):
            return {
                "id": trace_id,
                "timestamp": "2026-05-14T08:00:00Z",
                "sessionId": "session-1",
                "metadata": {"source_type": "chat", "model_key": "chat-model"},
                "scores": [
                    {"name": "trust_score", "value": 0.72, "timestamp": "2026-05-14T08:01:00Z"},
                    {"name": "hallucination_risk", "value": 0.22, "timestamp": "2026-05-14T08:01:00Z"},
                ],
                "observations": [
                    {"id": "obs-1", "type": "GENERATION", "model": "chat-model", "usage": {"total": 321}},
                ],
            }

        async def list_scores(self, *, trace_id=None, page=1, limit=50, **_kwargs):
            assert trace_id == "trace-chat"
            return {
                "data": [
                    {"traceId": "other-trace", "name": "trust_score", "value": 0.11},
                ],
                "meta": {"page": 1, "limit": 50, "totalItems": 1, "totalPages": 1},
            }

        async def list_observations(self, *, trace_id=None, page=1, limit=50, **_kwargs):
            raise AssertionError("trace detail should hydrate observations")

        def build_trace_url(self, trace_id):
            return f"http://127.0.0.1:3000/project/p/traces/{trace_id}"

    monkeypatch.setattr("app.services.quality_report_service.LangfuseApiClient", lambda: FakeApiClient())

    class EmptyRepo:
        async def list_by_range(self, *_args, **_kwargs):
            return []

        async def list_message_by_range(self, *_args, **_kwargs):
            return []

    class EmptyLedgerRepo:
        async def list_filtered(self, *_args, **_kwargs):
            return []

    class EmptyChatMessageRepo:
        async def list_assistant_for_org(self, *_args, **_kwargs):
            return []

    service = QualityReportService(session=object(), org_id="org-1")
    service._result_repo = EmptyRepo()
    service._feedback_repo = EmptyRepo()
    service._token_ledger_repo = EmptyLedgerRepo()
    service._chat_score_repo = EmptyRepo()
    service._chat_message_repo = EmptyChatMessageRepo()
    traces = await service.list_traces(source="chat")

    assert traces[0]["trust_score"] == 0.72
    assert traces[0]["hallucination_risk"] == 0.22
    assert traces[0]["total_tokens"] == 321


@pytest.mark.asyncio
async def test_quality_trace_list_merges_local_rows_when_langfuse_is_ok_but_empty(monkeypatch):
    class FakeApiClient:
        enabled = True

        async def list_traces(self, *, page=1, limit=50, tags=None):
            return {
                "data": [],
                "meta": {"page": 1, "limit": 50, "totalItems": 0, "totalPages": 1},
            }

    class ChatScoreRepo:
        async def list_by_range(self, *_args, **_kwargs):
            return [
                SimpleNamespace(
                    org_id="org-1",
                    assistant_message_id="msg-1",
                    session_id="session-1",
                    user_id="user-1",
                    trace_id="deleted-langfuse-trace",
                    observation_id="obs-chat",
                    trace_url="http://127.0.0.1:3000/project/p/traces/deleted-langfuse-trace",
                    model_key="deepseek-v4-flash",
                    review_model="deepseek-v4-flash",
                    trust_score=0.82,
                    hallucination_risk=0.2,
                    overconfidence=0.1,
                    has_citation=True,
                    status="scored",
                    langfuse_synced_at=datetime(2026, 5, 13, 12, 0, 0),
                    created_at=datetime(2026, 5, 13, 11, 0, 0),
                )
            ]

    class EmptyRepo:
        async def list_by_range(self, *_args, **_kwargs):
            return []

        async def list_message_by_range(self, *_args, **_kwargs):
            return []

    class EmptyLedgerRepo:
        async def list_filtered(self, *_args, **_kwargs):
            return []

    class EmptyChatMessageRepo:
        async def list_assistant_for_org(self, *_args, **_kwargs):
            return []

    monkeypatch.setattr("app.services.quality_report_service.LangfuseApiClient", lambda: FakeApiClient())

    service = QualityReportService(session=object(), org_id="org-1")
    service._result_repo = EmptyRepo()
    service._feedback_repo = EmptyRepo()
    service._token_ledger_repo = EmptyLedgerRepo()
    service._chat_score_repo = ChatScoreRepo()
    service._chat_message_repo = EmptyChatMessageRepo()
    result = await service.list_traces_with_meta(source="chat")

    assert result["meta"]["langfuse_status"] == "ok"
    assert result["meta"]["canonical_source"] == "hybrid"
    assert len(result["items"]) == 1
    assert result["items"][0]["trace_id"] == "deleted-langfuse-trace"


@pytest.mark.asyncio
async def test_quality_trace_list_returns_error_meta_with_local_fallback_when_langfuse_api_fails(monkeypatch):
    class FakeApiClient:
        enabled = True

        async def list_traces(self, *, page=1, limit=50, tags=None):
            raise LangfuseApiError("Langfuse API error 401: unauthorized")

        def build_trace_url(self, trace_id):
            return f"http://127.0.0.1:3000/project/project-test/traces/{trace_id}"

    class EmptyRepo:
        async def list_by_range(self, *_args, **_kwargs):
            return []

        async def list_message_by_range(self, *_args, **_kwargs):
            return []

    class EmptyLedgerRepo:
        async def list_filtered(self, *_args, **_kwargs):
            return []

    class ChatScoreRepo:
        async def list_by_range(self, *_args, **_kwargs):
            return [
                SimpleNamespace(
                    org_id="org-1",
                    assistant_message_id="msg-1",
                    session_id="session-1",
                    user_id="user-1",
                    trace_id="trace-chat",
                    observation_id="obs-chat",
                    trace_url="http://127.0.0.1:3000/project/project-test/traces/trace-chat",
                    model_key="qwen2.5:7b-instruct",
                    review_model="qwen2.5:7b-instruct",
                    trust_score=0.82,
                    hallucination_risk=0.2,
                    overconfidence=0.1,
                    has_citation=True,
                    status="scored",
                    langfuse_synced_at=datetime(2026, 5, 13, 12, 0, 0),
                    created_at=datetime(2026, 5, 13, 11, 0, 0),
                )
            ]

    class EmptyChatMessageRepo:
        async def list_assistant_for_org(self, *_args, **_kwargs):
            return []

    class FakeTracer:
        def trace_exists(self, trace_id):
            return None

        def get_trace_url(self, trace_id):
            return f"http://127.0.0.1:3000/project/project-test/traces/{trace_id}"

    monkeypatch.setattr("app.services.quality_report_service.LangfuseApiClient", lambda: FakeApiClient())
    monkeypatch.setattr("app.services.quality_report_service.LangfuseTracer", lambda: FakeTracer())

    service = QualityReportService(session=object(), org_id="org-1")
    service._result_repo = EmptyRepo()
    service._feedback_repo = EmptyRepo()
    service._token_ledger_repo = EmptyLedgerRepo()
    service._chat_score_repo = ChatScoreRepo()
    service._chat_message_repo = EmptyChatMessageRepo()

    result = await service.list_traces_with_meta(source="chat")

    assert result["meta"]["langfuse_status"] == "error"
    assert "401" in result["meta"]["langfuse_error"]
    assert result["meta"]["canonical_source"] == "local_fallback"
    assert len(result["items"]) == 1
    assert result["items"][0]["trace_id"] == "trace-chat"


@pytest.mark.asyncio
async def test_quality_trace_delete_reports_langfuse_failure_without_claiming_deleted(monkeypatch):
    class FakeApiClient:
        enabled = True

        async def delete_trace(self, trace_id):
            raise LangfuseApiError("Langfuse API error 401: unauthorized")

    class EmptyLedgerRepo:
        async def find_by_trace_id(self, trace_id):
            return []

    class EmptyScoreRepo:
        async def find_by_trace_id(self, trace_id):
            return []

    class ResultRepo:
        async def soft_delete(self, result_id):
            raise AssertionError("no result should be deleted for this trace")

    monkeypatch.setattr("app.services.quality_report_service.LangfuseApiClient", lambda: FakeApiClient())

    service = QualityReportService(session=object(), org_id="org-1")
    service._token_ledger_repo = EmptyLedgerRepo()
    service._chat_score_repo = EmptyScoreRepo()
    service._result_repo = ResultRepo()

    result = await service.delete_trace("trace-chat")

    assert result["deleted"] is False
    assert result["langfuse_deleted"] is False
    assert result["local_cleaned"] is False
    assert result["status"] == "langfuse_failed"
    assert "401" in result["message"]


@pytest.mark.asyncio
async def test_quality_report_filters_chat_source_without_inspection_counts():
    class ResultRepo:
        async def list_by_range(self, *_args, **_kwargs):
            return [
                SimpleNamespace(
                    id="result-1",
                    llm_model="inspection-model",
                    verdict="pass",
                    citations=[],
                    created_at=datetime(2026, 5, 14, 8, 0, 0),
                )
            ]

    class FeedbackRepo:
        async def list_by_range(self, *_args, **_kwargs):
            return [SimpleNamespace(result_id="result-1", feedback_type="down", category="bad", created_at=datetime(2026, 5, 14, 8, 0, 0))]

        async def list_message_by_range(self, *_args, **_kwargs):
            return []

    class StabilityRepo:
        async def list_by_range(self, *_args, **_kwargs):
            return [SimpleNamespace(risk_score=0.9)]

    class ChatScoreRepo:
        async def list_by_range(self, *_args, **_kwargs):
            return [
                SimpleNamespace(
                    trust_score=0.4,
                    hallucination_risk=0.7,
                    overconfidence=0.2,
                    has_citation=False,
                    assistant_message_id="msg-1",
                    created_at=datetime(2026, 5, 14, 9, 0, 0),
                )
            ]

    class ChatMessageRepo:
        async def list_assistant_for_org(self, *_args, **_kwargs):
            return [
                SimpleNamespace(
                    id="msg-1",
                    payload={"llm_meta": {"model": "chat-model"}},
                    created_at=datetime(2026, 5, 14, 9, 0, 0),
                )
            ]

    class EmptyLedgerRepo:
        async def list_filtered(self, *_args, **_kwargs):
            return []

    service = QualityReportService(session=object(), org_id="org-1")
    service._result_repo = ResultRepo()
    service._feedback_repo = FeedbackRepo()
    service._stability_repo = StabilityRepo()
    service._token_ledger_repo = EmptyLedgerRepo()
    service._chat_score_repo = ChatScoreRepo()
    service._chat_message_repo = ChatMessageRepo()

    report = await service.build_report(source="chat")

    assert report["total_results"] == 1
    assert report["hallucination_rate"] == 1.0
    assert report["thumbs_down_rate"] == 0.0
    assert report["thumbs_up_rate"] == 0.0
    assert report["thumbs_down_count"] == 0
    assert report["thumbs_up_count"] == 0
    assert report["feedback_total_count"] == 0
    assert report["model_metrics"] == [
        {
            "model_key": "chat-model",
            "result_count": 1,
            "pass_rate": 0.0,
            "hallucination_rate": 1.0,
            "thumbs_down_rate": 0.0,
            "thumbs_up_rate": 0.0,
        }
    ]
    assert report["chat_message_count"] == 1
    assert report["chat_score_count"] == 1
    assert report["chat_unscored_count"] == 0
    assert report["chat_scored_rate"] == 1.0
    assert report["chat_avg_trust_score"] == 0.4


@pytest.mark.asyncio
async def test_quality_report_uses_langfuse_trace_items_when_enabled(monkeypatch):
    class FakeApiClient:
        enabled = True

        async def list_traces(self, **_kwargs):
            return {
                "data": [
                    {
                        "id": "trace-chat",
                        "timestamp": "2026-05-14T09:00:00Z",
                        "metadata": {"source_type": "chat", "model_key": "chat-model"},
                        "scores": [
                            {"name": "trust_score", "value": 0.6},
                            {"name": "hallucination_risk", "value": 0.7},
                            {"name": "overconfidence", "value": 0.4},
                            {"name": "has_citation", "value": 1},
                        ],
                        "observations": [],
                    }
                ],
                "meta": {"page": 1, "limit": 50, "totalItems": 1, "totalPages": 1},
            }

        def build_trace_url(self, trace_id):
            return f"http://127.0.0.1:3000/project/p/traces/{trace_id}"

    class EmptyResultRepo:
        async def list_by_range(self, *_args, **_kwargs):
            return []

    class EmptyRepo:
        async def list_by_range(self, *_args, **_kwargs):
            return []

        async def list_message_by_range(self, *_args, **_kwargs):
            return []

    class EmptyLedgerRepo:
        async def list_filtered(self, *_args, **_kwargs):
            return []

    class EmptyChatMessageRepo:
        async def list_assistant_for_org(self, *_args, **_kwargs):
            return []

    monkeypatch.setattr("app.services.quality_report_service.LangfuseApiClient", lambda: FakeApiClient())

    service = QualityReportService(session=object(), org_id="org-1")
    service._result_repo = EmptyResultRepo()
    service._feedback_repo = EmptyRepo()
    service._stability_repo = EmptyRepo()
    service._token_ledger_repo = EmptyLedgerRepo()
    service._chat_score_repo = EmptyRepo()
    service._chat_message_repo = EmptyChatMessageRepo()
    report = await service.build_report(source="chat")

    assert report["total_results"] == 1
    assert report["chat_message_count"] == 1
    assert report["chat_score_count"] == 1
    assert report["chat_unscored_count"] == 0
    assert report["chat_scored_rate"] == 1.0
    assert report["chat_avg_trust_score"] == 0.6
    assert report["chat_hallucination_rate"] == 1.0


@pytest.mark.asyncio
async def test_analytics_overview_overlays_quality_metrics_from_langfuse(monkeypatch):
    class FakeApiClient:
        enabled = True

    class FakeRepo:
        async def get_overview(self, *_args, **_kwargs):
            return {
                "total_tasks": 5,
                "total_alerts": 1,
                "total_results": 99,
                "total_cost": 123.0,
                "pass_rate": 0.99,
                "hallucination_rate": 0.99,
                "risk_yellow_rate": 0.0,
                "avg_risk_score": 0.0,
                "avg_latency_ms": 0.0,
                "task_trend": [],
                "pass_rate_trend": [],
                "hallucination_trend": [],
                "risk_distribution_trend": [],
                "risk_distribution": [],
                "alert_distribution": [],
                "model_metrics": [],
                "product_line_series": [],
                "scope_kind": "org",
            }

    async def fake_fetch(self, **_kwargs):
        return (
            [
                {
                    "source_type": "chat",
                    "trace_id": "trace-1",
                    "verdict": "pass",
                    "model_key": "chat-model",
                    "total_tokens": 200,
                    "total_cost": 0.03,
                    "trust_score": 0.8,
                    "hallucination_risk": 0.2,
                    "overconfidence": 0.1,
                    "has_citation": True,
                    "thumbs_down_count": 0,
                    "created_at": "2026-05-14T09:00:00Z",
                }
            ],
            None,
        )

    monkeypatch.setattr("app.services.analytics_service.LangfuseApiClient", lambda: FakeApiClient())
    monkeypatch.setattr(QualityReportService, "_fetch_traces_from_langfuse", fake_fetch)

    service = AnalyticsService(session=object(), org_id="org-1")
    service._repo = FakeRepo()
    overview = await service.overview()

    assert overview["total_tasks"] == 5
    assert overview["total_results"] == 1
    assert overview["total_cost"] == 0.03
    assert overview["pass_rate"] == 1.0
    assert overview["hallucination_rate"] == 0.0
    assert overview["model_metrics"][0]["avg_tokens"] == 200.0
