from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy.exc import ProgrammingError

from agent.llm.client import LLMClient
from app.services.rag_space_service import _is_rag_metadata_missing
from agent.subgraphs.quality_chat.graph import (
    _chat_usage_from_state,
    _enqueue_trust_scoring,
    _extract_named_user_from_history,
    _fallback_answer,
    _smalltalk_answer,
    finalizer,
    knowledge,
    planner,
    quality_gate,
    QualityChatState,
    task_extractor,
)
from app.core.config import settings
from app.core.security import create_stream_token
from app.services.chat_service import get_current_user_for_stream


def test_fallback_answer_uses_first_doc_excerpt():
    data = _fallback_answer(
        "What is a burr defect?",
        [
            {
                "title": "Surface Defect Standard",
                "text": "Burr defects usually appear around metal edges or molding split lines and should be judged with size and sharp-edge risk.",
                "source": "QS-009",
            }
        ],
        [{"id": "doc-1"}],
    )
    assert "Surface Defect Standard" in data["answer"]
    assert data["citations"] == [{"id": "doc-1"}]


def test_normalize_usage_keeps_only_stable_token_counts():
    raw_usage = {
        "prompt_tokens": 24,
        "completion_tokens": 12,
        "total_tokens": 36,
        "prompt_tokens_details": {"cached_tokens": 10},
    }
    assert LLMClient._normalize_usage(raw_usage) == {
        "prompt_tokens": 24,
        "completion_tokens": 12,
        "total_tokens": 36,
    }


def test_normalize_usage_accepts_object_shape():
    class Usage:
        prompt_tokens = 23
        completion_tokens = 0
        total_tokens = 23

    assert LLMClient._normalize_usage(Usage()) == {
        "prompt_tokens": 23,
        "completion_tokens": 0,
        "total_tokens": 23,
    }


def test_chat_usage_from_state_extracts_llm_usage_for_general_qa():
    usage = _chat_usage_from_state(
        {
            "org_id": "org-1",
            "user_id": "user-1",
            "workspace": "app",
            "trace": {"trace_id": "trace-root"},
            "reasoning": {
                "llm_meta": {
                    "model": "ep-chat",
                    "usage": {
                        "prompt_tokens": 30,
                        "completion_tokens": 12,
                        "total_tokens": 42,
                    },
                    "langfuse": {"trace_id": "trace-llm"},
                }
            },
        }
    )

    assert usage is not None
    assert usage["model_key"] == "ep-chat"
    assert usage["total_tokens"] == 42
    assert usage["trace_id"] == "trace-llm"


def test_chat_usage_from_state_uses_runtime_pricing_when_available():
    usage = _chat_usage_from_state(
        {
            "org_id": "org-1",
            "user_id": "user-1",
            "workspace": "app",
            "trace": {"trace_id": "trace-root"},
            "reasoning": {
                "llm_meta": {
                    "model": "custom-chat",
                    "usage": {
                        "prompt_tokens": 1000,
                        "completion_tokens": 1000,
                        "total_tokens": 2000,
                    },
                    "pricing": {
                        "input_price_per_million": 10.0,
                        "output_price_per_million": 20.0,
                    },
                }
            },
        }
    )

    assert usage is not None
    assert usage["cost_amount"] == 0.03


def test_quality_chat_state_keeps_trust_scoring_runtime_fields():
    annotations = QualityChatState.__annotations__

    assert "trust_scoring_payload" in annotations
    assert "trust_scoring_task" in annotations


def test_enqueue_trust_scoring_logs_queue_failures(monkeypatch, caplog):
    from worker.tasks.chat_trust_scoring_task import score_chat_message

    def fail_delay(_payload):
        raise RuntimeError("redis transport unavailable")

    monkeypatch.setattr(score_chat_message, "delay", fail_delay)

    with caplog.at_level("WARNING", logger="agent.subgraphs.quality_chat.graph"):
        _enqueue_trust_scoring({"assistant_message_id": "msg-1"})

    assert "trust scoring enqueue failed" in caplog.text
    assert "msg-1" in caplog.text


@pytest.mark.asyncio
async def test_finalizer_keeps_trust_scoring_in_response_payload(monkeypatch):
    updates: list[dict] = []
    scores: list[dict] = []
    events: list[dict] = []

    class FakeSession:
        async def commit(self):
            return None

    class FakeSessionContext:
        async def __aenter__(self):
            return FakeSession()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeChatMessageRepository:
        def __init__(self, _session):
            pass

        async def update_assistant_message(self, **kwargs):
            updates.append(kwargs)
            return None

    class FakeChatMessageScoreRepository:
        def __init__(self, _session):
            pass

        async def upsert_by_message_version(self, score):
            scores.append(score)
            return None

    async def fake_emit(event: dict):
        events.append(event)

    async def fake_persist_usage(_session, _state):
        return None

    async def fake_persist_rag(_session, _state):
        return None

    async def fake_score():
        return {
            "org_id": "11111111-1111-1111-1111-111111111111",
            "session_id": "22222222-2222-2222-2222-222222222222",
            "user_id": "33333333-3333-3333-3333-333333333333",
            "assistant_message_id": "44444444-4444-4444-4444-444444444444",
            "score_version": "trust_v1",
            "trace_id": "trace-1",
            "observation_id": "obs-1",
            "trace_url": "http://127.0.0.1:3000/project/p/traces/trace-1",
            "model_key": "model-1",
            "review_model": "deepseek-v4-flash",
            "rule_scores": {},
            "llm_scores": {},
            "combined_scores": {"risk_level": "low"},
            "trust_score": 0.9,
            "hallucination_risk": 0.1,
            "overconfidence": 0.2,
            "has_citation": True,
            "status": "scored",
            "langfuse_synced_at": None,
        }

    monkeypatch.setattr("agent.subgraphs.quality_chat.graph.get_session", lambda: FakeSessionContext())
    monkeypatch.setattr("agent.subgraphs.quality_chat.graph.ChatMessageRepository", FakeChatMessageRepository)
    monkeypatch.setattr("agent.subgraphs.quality_chat.graph.ChatMessageScoreRepository", FakeChatMessageScoreRepository)
    monkeypatch.setattr("agent.subgraphs.quality_chat.graph._persist_chat_token_usage", fake_persist_usage)
    monkeypatch.setattr("agent.subgraphs.quality_chat.graph._persist_rag_query_log", fake_persist_rag)

    trust_task = asyncio.create_task(fake_score())
    state = {
        "org_id": "11111111-1111-1111-1111-111111111111",
        "session_id": "22222222-2222-2222-2222-222222222222",
        "assistant_message_id": "44444444-4444-4444-4444-444444444444",
        "workflow_run_id": "run-1",
        "response_payload": {"answer": "ok", "message_type": "assistant_text"},
        "trust_scoring_payload": {"assistant_message_id": "44444444-4444-4444-4444-444444444444"},
        "trust_scoring_task": trust_task,
        "emit": fake_emit,
    }

    updated = await finalizer(state)

    assert updated["response_payload"]["trust_scoring"]["trust_score"] == 0.9
    assert updates[0]["payload"]["trust_scoring"]["trace_url"].endswith("/trace-1")
    assert scores[0]["trust_score"] == 0.9
    assert events[-1]["payload"]["trust_scoring"]["risk_level"] == "low"


def test_smalltalk_answer_remembers_user_name_from_history():
    answer = _smalltalk_answer(
        "我叫什么名字",
        [
            {"role": "user", "content": "你好"},
            {"role": "user", "content": "我叫tgg"},
        ],
    )
    assert answer == "你之前告诉过我，你叫tgg。"


def test_extract_named_user_from_history_reads_latest_name():
    history = [
        {"role": "user", "content": "我叫alice"},
        {"role": "assistant", "content": "好的"},
        {"role": "user", "content": "我叫tgg"},
    ]
    assert _extract_named_user_from_history(history) == "tgg"


def test_rag_metadata_missing_detection_matches_missing_table_error():
    exc = ProgrammingError(
        "SELECT * FROM rag_spaces",
        {},
        Exception("Table 'piap_main.rag_spaces' doesn't exist"),
    )
    assert _is_rag_metadata_missing(exc) is True


@pytest.mark.asyncio
async def test_quality_gate_downgrades_when_evidence_is_missing():
    original_answer = "This answer sounds certain."
    state = {
        "intent": "quality_qa",
        "reasoning": {"answer": original_answer},
        "citations": [],
        "retrieval_metrics": {"hit_count": 0},
    }
    updated = await quality_gate(state)
    assert updated["quality"]["passed"] is False
    assert updated["quality"]["risk_level"] == "critical"
    assert len(updated["reasoning"]["answer"]) > len(original_answer)


@pytest.mark.asyncio
async def test_planner_routes_smalltalk_without_task_state():
    state = {
        "query": "who are you?",
        "metadata": {},
        "history": [],
        "ext": {},
    }
    updated = await planner(state)
    assert updated["intent"] == "smalltalk"
    assert updated["intent_confidence"] >= 0.9


@pytest.mark.asyncio
async def test_planner_routes_general_qa_for_non_quality_text():
    state = {
        "query": "my name is tgg",
        "metadata": {},
        "history": [],
        "ext": {},
    }
    updated = await planner(state)
    assert updated["intent"] == "general_qa"


@pytest.mark.asyncio
async def test_planner_routes_quality_qa_for_quality_terms():
    state = {
        "query": "how should this defect be judged",
        "metadata": {},
        "history": [],
        "ext": {},
    }
    updated = await planner(state)
    assert updated["intent"] == "quality_qa"


@pytest.mark.asyncio
async def test_planner_routes_task_create_for_plain_quality_detection_trigger():
    state = {
        "query": "quality inspection",
        "metadata": {},
        "history": [],
        "ext": {},
    }
    updated = await planner(state)
    assert updated["intent"] == "task_create"


@pytest.mark.asyncio
async def test_knowledge_skips_retrieval_for_non_quality_qa():
    state = {
        "intent": "smalltalk",
        "query": "who are you?",
    }
    updated = await knowledge(state)
    assert updated["retrieval_metrics"]["skipped"] is True
    assert updated["citations"] == []


@pytest.mark.asyncio
async def test_knowledge_filters_retrieval_by_current_user(monkeypatch):
    captured: dict[str, object] = {}

    class FakeRetriever:
        def __init__(self, **kwargs):
            captured["init"] = kwargs

        async def retrieve(self, query, top_k=5, payload_filter=None):
            captured["query"] = query
            captured["top_k"] = top_k
            captured["payload_filter"] = payload_filter
            return []

    monkeypatch.setattr("agent.subgraphs.quality_chat.graph.Retriever", FakeRetriever)

    state = {
        "intent": "quality_qa",
        "query": "quality question",
        "session_id": "session-1",
        "org_id": "org-1",
        "user_id": "user-1",
        "trace": {},
        "ext": {
            "selected_rag_space_id": "space-1",
            "selected_rag_space_name": "My Space",
        },
    }

    updated = await knowledge(state)

    assert captured["payload_filter"] == {
        "org_id": "org-1",
        "user_id": "user-1",
        "rag_space_id": "space-1",
    }
    assert updated["retrieval_metrics"]["rag_space_id"] == "space-1"


@pytest.mark.asyncio
async def test_task_extractor_marks_missing_slots_for_incomplete_task_request():
    state = {
        "intent": "task_create",
        "query": "请帮我创建检测任务，产品编号 P-1001",
        "metadata": {},
        "ext": {},
        "task_draft": {},
        "awaiting_confirmation": False,
    }
    updated = await task_extractor(state)
    assert updated["action_state"] == "awaiting_task_details"
    assert updated["task_draft"]["product_id"] == "P-1001"
    assert updated["missing_slots"] == ["spec_code", "image_urls"]


@pytest.mark.asyncio
async def test_task_followup_confirm_requests_creation_when_slots_are_complete():
    state = {
        "intent": "task_followup",
        "query": "confirm",
        "metadata": {},
        "ext": {},
        "task_draft": {
            "product_id": "P-1001",
            "spec_code": "QS-009",
            "image_urls": ["https://example.com/1.jpg"],
            "priority": 5,
            "metadata": {},
        },
        "awaiting_confirmation": True,
    }
    updated = await task_extractor(state)
    assert updated["action_state"] == "task_create_requested"
    assert updated["missing_slots"] == []


def test_get_current_user_for_stream_reads_resource_claims():
    backend_dir = Path(__file__).resolve().parents[1]
    settings.jwt_private_key = (backend_dir / "jwt_private.pem").read_text(encoding="utf-8")
    settings.jwt_public_key = (backend_dir / "jwt_public.pem").read_text(encoding="utf-8")
    token = create_stream_token(
        "user-1",
        extra={
            "org_id": "org-1",
            "user_id": "user-1",
            "role": "user",
            "roles": ["user"],
            "resource": "chat",
            "resource_id": "session-1",
        },
    )
    current = get_current_user_for_stream(authorization="", token=token)
    assert current.user_id == "user-1"
    assert current.stream_resource == "chat"
    assert current.stream_resource_id == "session-1"
