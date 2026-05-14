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
    assert result["trust_score"] < 1.0
    assert result["trace_url"] == "http://127.0.0.1:3000/project/x/traces/trace-1"
    assert {item["name"] for item in synced_scores} >= {
        "hallucination_risk",
        "overconfidence",
        "has_citation",
        "trust_score",
    }


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
async def test_quality_trace_list_keeps_chat_token_ledger_when_filtered_to_chat():
    class ResultRepo:
        async def list_by_range(self, *_args, **_kwargs):
            return [SimpleNamespace(id="result-1", created_at=datetime(2026, 5, 14, 8, 0, 0))]

    class FeedbackRepo:
        async def list_by_range(self, *_args, **_kwargs):
            return []

    class TokenLedgerRepo:
        async def list_filtered(self, *_args, **_kwargs):
            return [
                SimpleNamespace(result_id=None, trace_id="trace-chat", total_tokens=327),
                SimpleNamespace(result_id="result-1", trace_id="trace-inspection", total_tokens=999),
            ]

    class ChatScoreRepo:
        async def list_by_range(self, *_args, **_kwargs):
            return [
                SimpleNamespace(
                    assistant_message_id="msg-1",
                    session_id="session-1",
                    observation_id="obs-1",
                    trace_id="trace-chat",
                    trace_url="http://127.0.0.1:3000/project/p/traces/trace-chat",
                    model_key="doubao-seed-2-0-pro-260215",
                    trust_score=0.355,
                    hallucination_risk=0.725,
                    overconfidence=0.21,
                    has_citation=False,
                    status="scored",
                    review_model="deepseek-v4-flash",
                    langfuse_synced_at=datetime(2026, 5, 14, 8, 1, 0),
                    created_at=datetime(2026, 5, 14, 8, 0, 0),
                )
            ]

    class ChatMessageRepo:
        async def list_assistant_for_org(self, *_args, **_kwargs):
            return []

    service = QualityReportService(session=object(), org_id="org-1")
    service._result_repo = ResultRepo()
    service._feedback_repo = FeedbackRepo()
    service._token_ledger_repo = TokenLedgerRepo()
    service._chat_score_repo = ChatScoreRepo()
    service._chat_message_repo = ChatMessageRepo()

    traces = await service.list_traces(source="chat")

    assert len(traces) == 1
    assert traces[0]["source_type"] == "chat"
    assert traces[0]["total_tokens"] == 327


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

    service = QualityReportService(session=object(), org_id="org-1")
    service._result_repo = ResultRepo()
    service._feedback_repo = FeedbackRepo()
    service._stability_repo = StabilityRepo()
    service._chat_score_repo = ChatScoreRepo()
    service._chat_message_repo = ChatMessageRepo()

    report = await service.build_report(source="chat")

    assert report["total_results"] == 1
    assert report["hallucination_rate"] == 0.0
    assert report["thumbs_down_rate"] == 0.0
    assert report["model_metrics"] == [
        {
            "model_key": "chat-model",
            "result_count": 1,
            "pass_rate": 0.0,
            "hallucination_rate": 0.0,
            "thumbs_down_rate": 0.0,
        }
    ]
    assert report["chat_score_count"] == 1
    assert report["chat_avg_trust_score"] == 0.4
