from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import ProgrammingError

from agent.llm.client import LLMClient
from agent.prompts.chat_prompts import PROMPTS as CHAT_CODE_PROMPTS
from agent.prompts.prompt_builder import PromptBuilder
from app.services.rag_space_service import _is_rag_metadata_missing
from agent.subgraphs.quality_chat.graph import (
    _chat_usage_from_state,
    _enqueue_trust_scoring,
    _extract_named_user_from_history,
    _fallback_answer,
    _persist_rag_query_log,
    _smalltalk_answer,
    finalizer,
    knowledge,
    planner,
    quality_gate,
    reasoning,
    ChatState,
    task_extractor,
)
from app.core.config import settings
from app.core.security import create_stream_token
from app.schemas.user import CurrentUser
from app.services import chat_service as chat_service_mod
from app.services.chat_service import ChatService, get_current_user_for_stream


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


def test_chat_general_prompt_supports_normal_model_chat():
    prompts = {str(item["key"]): str(item["content"]) for item in CHAT_CODE_PROMPTS}
    content = prompts["chat.general.system"]

    assert "通用对话助手" in content
    assert "常识性问题" in content
    assert "城市评价" in content
    assert "对普通问题直接回答" in content
    assert "不要因为问题不属于质检领域而拒答" in content
    assert "JSON" in content
    assert '{"answer": string, "summary": string}' in content
    assert "你是一个产品质量检测助手" not in content
    assert "只回答产品质量" not in content


def test_chat_specialized_prompts_keep_json_contract():
    prompts = {str(item["key"]): str(item["content"]) for item in CHAT_CODE_PROMPTS}
    for prompt_key in {"chat.rag_answer.system", "chat.file_summary.system", "chat.paper_format_check.system"}:
        content = prompts[prompt_key]
        assert "JSON" in content
        assert '{"answer": string, "summary": string}' in content


def test_chat_rag_prompt_does_not_refuse_on_empty_recall():
    prompts = {str(item["key"]): str(item["content"]) for item in CHAT_CODE_PROMPTS}
    content = prompts["chat.rag_answer.system"]

    assert "不是回答开关" in content
    assert "仍然继续回答用户问题" in content
    assert "不来自当前知识库" in content


def test_prompt_builder_appends_rag_empty_recall_policy_to_runtime_override():
    system_prompt, user_message, _temperature, _metadata = PromptBuilder.build(
        agent="chat",
        sub_route="rag_qa",
        query="张雪峰老师现状",
        retrieved_docs=[],
        prompt_override="旧版提示：如果证据不足，请说明知识库没有提供该信息。",
        prompt_version_override="db_prompt_v1",
    )

    assert "旧版提示" in system_prompt
    assert "仍然要继续回答用户问题" in system_prompt
    assert "不来自当前知识库" in system_prompt
    assert "未检索到可用知识库片段" in user_message
    assert "请继续回答用户问题" in user_message


@pytest.mark.asyncio
async def test_planner_uses_rag_qa_when_space_is_selected():
    state = {
        "query": "我叫什么名字",
        "metadata": {},
        "ext": {
            "selected_rag_space": {"id": "space-1", "name": "食物"},
        },
        "history": [],
    }

    updated = await planner(state)

    assert updated["intent"] == "rag_qa"
    assert updated["metadata"]["rag_forced_by_selection"] is True


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


@pytest.mark.asyncio
async def test_reasoning_preserves_fallback_when_llm_call_fails(monkeypatch):
    class FakeSessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeModelConfigService:
        def __init__(self, session, org_id):
            return None

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
                }
            ]

    class FakeGateway:
        async def select_runtime(self, models, **kwargs):
            item = list(models)[0]
            return {
                "model_id": item["model_key"],
                "base_url": item["endpoint"],
                "api_key": item["api_key"],
                "provider": item["provider"],
                "input_price_per_million": None,
                "output_price_per_million": None,
            }

    class FakeLLMClient:
        def __init__(self, **kwargs):
            return None

        async def chat(self, *args, **kwargs):
            raise RuntimeError("upstream unavailable")

    monkeypatch.setattr("agent.subgraphs.quality_chat.graph.get_session", lambda: FakeSessionContext())
    monkeypatch.setattr("agent.subgraphs.quality_chat.graph.ModelConfigService", FakeModelConfigService)
    monkeypatch.setattr("agent.subgraphs.quality_chat.graph.LLMGateway", lambda: FakeGateway())
    monkeypatch.setattr("agent.subgraphs.quality_chat.graph.LLMClient", FakeLLMClient)

    state = {
        "org_id": "org-1",
        "session_id": "session-1",
        "intent": "general_qa",
        "query": "hello",
        "history": [],
        "retrieved_chunks": [],
        "citations": [],
        "action_state": "answered",
        "task_draft": {},
        "missing_slots": [],
        "trace": {"trace_id": "trace-1"},
    }

    updated = await reasoning(state)

    assert updated["action_state"] == "answered"
    assert updated["reasoning"]["answer"]
    assert updated["reasoning"]["llm_error"] == "upstream unavailable"


@pytest.mark.asyncio
async def test_reasoning_uses_prompt_admin_override_when_available(monkeypatch):
    captured_messages: list[list[dict[str, str]]] = []

    class FakeSessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeModelConfigService:
        def __init__(self, session, org_id):
            return None

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
                }
            ]

    class FakeGateway:
        async def select_runtime(self, models, **kwargs):
            item = list(models)[0]
            return {
                "model_id": item["model_key"],
                "base_url": item["endpoint"],
                "api_key": item["api_key"],
                "provider": item["provider"],
                "input_price_per_million": None,
                "output_price_per_million": None,
            }

    class FakeLLMClient:
        def __init__(self, **kwargs):
            return None

        async def chat(self, messages, *args, **kwargs):
            captured_messages.append(messages)
            return {"answer": "ok", "summary": "override used", "__meta__": {}}

    async def fake_prompt_get(self, prompt_key: str, *, org_id: str):
        assert prompt_key == "chat.general.system"
        assert org_id == "org-1"
        return "PROMPT_OVERRIDE_FROM_DB"

    monkeypatch.setattr("agent.subgraphs.quality_chat.graph.get_session", lambda: FakeSessionContext())
    monkeypatch.setattr("agent.subgraphs.quality_chat.graph.ModelConfigService", FakeModelConfigService)
    monkeypatch.setattr("agent.subgraphs.quality_chat.graph.LLMGateway", lambda: FakeGateway())
    monkeypatch.setattr("agent.subgraphs.quality_chat.graph.LLMClient", FakeLLMClient)
    monkeypatch.setattr("app.services.prompt_admin_service.PromptResolver.get", fake_prompt_get)

    state = {
        "org_id": "org-1",
        "session_id": "session-1",
        "intent": "general_qa",
        "query": "hello",
        "history": [],
        "retrieved_chunks": [],
        "citations": [],
        "action_state": "answered",
        "task_draft": {},
        "missing_slots": [],
        "trace": {"trace_id": "trace-1"},
    }

    updated = await reasoning(state)

    assert updated["reasoning"]["answer"] == "ok"
    assert captured_messages[0][0]["content"] == "PROMPT_OVERRIDE_FROM_DB"


def test_chat_state_keeps_trust_scoring_runtime_fields():
    annotations = ChatState.__annotations__

    assert "trust_scoring_payload" in annotations
    assert "trust_scoring_task" not in annotations


def test_enqueue_trust_scoring_logs_queue_failures(monkeypatch, caplog):
    import sys
    from types import SimpleNamespace

    def fail_delay(_payload):
        raise RuntimeError("redis transport unavailable")

    monkeypatch.setitem(
        sys.modules,
        "worker.tasks.chat_trust_scoring_task",
        SimpleNamespace(score_chat_message=SimpleNamespace(delay=fail_delay)),
    )

    with caplog.at_level("WARNING", logger="agent.subgraphs.quality_chat.graph"):
        _enqueue_trust_scoring({"assistant_message_id": "msg-1"})

    assert "trust scoring enqueue failed" in caplog.text
    assert "msg-1" in caplog.text


@pytest.mark.asyncio
async def test_finalizer_marks_trust_scoring_reviewing_and_enqueues_once(monkeypatch):
    updates: list[dict] = []
    scores: list[dict] = []
    events: list[dict] = []
    queued_payloads: list[dict] = []

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

    def fake_enqueue(payload: dict | None):
        if payload:
            queued_payloads.append(payload)

    pending_score = {
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
        "llm_scores": None,
        "combined_scores": None,
        "trust_score": None,
        "hallucination_risk": 0.1,
        "overconfidence": 0.2,
        "has_citation": True,
        "status": "reviewing",
        "langfuse_synced_at": None,
    }

    def fake_build_pending_trust_score(**_kwargs):
        return dict(pending_score)

    monkeypatch.setattr("agent.subgraphs.quality_chat.graph._enqueue_trust_scoring", fake_enqueue)
    monkeypatch.setattr("agent.subgraphs.quality_chat.graph.build_pending_trust_score", fake_build_pending_trust_score)

    monkeypatch.setattr("agent.subgraphs.quality_chat.graph.get_session", lambda: FakeSessionContext())
    monkeypatch.setattr("agent.subgraphs.quality_chat.graph.ChatMessageRepository", FakeChatMessageRepository)
    monkeypatch.setattr("agent.subgraphs.quality_chat.graph.ChatMessageScoreRepository", FakeChatMessageScoreRepository)
    monkeypatch.setattr("agent.subgraphs.quality_chat.graph._persist_chat_token_usage", fake_persist_usage)
    monkeypatch.setattr("agent.subgraphs.quality_chat.graph._persist_rag_query_log", fake_persist_rag)

    state = {
        "org_id": "11111111-1111-1111-1111-111111111111",
        "session_id": "22222222-2222-2222-2222-222222222222",
        "user_id": "33333333-3333-3333-3333-333333333333",
        "assistant_message_id": "44444444-4444-4444-4444-444444444444",
        "workflow_run_id": "run-1",
        "response_payload": {"answer": "ok", "message_type": "assistant_text"},
        "trust_scoring_payload": {
            "org_id": "11111111-1111-1111-1111-111111111111",
            "session_id": "22222222-2222-2222-2222-222222222222",
            "user_id": "33333333-3333-3333-3333-333333333333",
            "assistant_message_id": "44444444-4444-4444-4444-444444444444",
            "input_text": "hello",
            "output_text": "ok",
            "citations": [],
            "trace_id": "trace-1",
            "observation_id": "obs-1",
            "model_key": "model-1",
        },
        "emit": fake_emit,
    }

    updated = await finalizer(state)

    assert updated["response_payload"]["trust_scoring"]["status"] == "reviewing"
    assert updated["response_payload"]["trust_scoring"]["trust_score"] is None
    assert updates == []
    assert scores == []
    assert events == []
    assert queued_payloads == [state["trust_scoring_payload"]]


@pytest.mark.asyncio
async def test_run_workflow_loads_history_before_current_user_seq(monkeypatch):
    captured_payloads: list[dict] = []

    class FakeMessage:
        def __init__(self, role: str, content: str, seq_no: int):
            self.role = role
            self.content = content
            self.seq_no = seq_no

    class FakeRepo:
        def __init__(self, _session):
            pass

        async def list_for_session(self, *, org_id, session_id, after_seq=0, limit=20):
            return [
                FakeMessage("user", "old question", 1),
                FakeMessage("assistant", "old answer", 2),
                FakeMessage("user", "current question", 3),
                FakeMessage("assistant", "", 4),
            ]

    class FakeSession:
        pass

    class FakeSessionContext:
        async def __aenter__(self):
            return FakeSession()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeBroker:
        async def publish(self, _session_id: str, _event: dict):
            return None

    class FakeOrchestrator:
        async def run_chat(self, payload: dict):
            captured_payloads.append(payload)
            return {}

    monkeypatch.setattr(chat_service_mod, "get_session", lambda: FakeSessionContext())
    monkeypatch.setattr(chat_service_mod, "ChatMessageRepository", FakeRepo)
    monkeypatch.setattr(chat_service_mod, "chat_stream_broker", FakeBroker())

    service = ChatService(
        org_id="org-1",
        user_id="user-1",
        current=CurrentUser(user_id="user-1", org_id="org-1", role="user", roles=["user"]),
    )
    service._orchestrator = FakeOrchestrator()

    await service._run_workflow(
        session_id="session-1",
        assistant_message_id="assistant-1",
        request=chat_service_mod.ChatMessageSendRequest(message="current question"),
        workflow_run_id="workflow-1",
        current_user_seq_no=3,
        assistant_message_seq_no=4,
    )

    ext = captured_payloads[0]["ext"]
    assert ext["current_user_seq_no"] == 3
    assert ext["assistant_message_seq_no"] == 4
    assert ext["history_messages"] == [
        {"role": "user", "content": "old question"},
        {"role": "assistant", "content": "old answer"},
    ]


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
async def test_persist_rag_query_log_writes_trace_detail_payload(monkeypatch):
    payloads: list[dict] = []

    class FakeRagAnalysisRepository:
        def __init__(self, _session, _org_id):
            pass

        async def create_log(self, data: dict):
            payloads.append(data)
            return None

    monkeypatch.setattr(
        "agent.subgraphs.quality_chat.graph.RagAnalysisRepository",
        FakeRagAnalysisRepository,
    )

    state = {
        "org_id": "org-1",
        "session_id": "session-1",
        "user_id": "user-1",
        "query": "苹果划痕怎么判定",
        "intent": "rag_qa",
        "sub_route": "rag_qa",
        "trace": {"trace_id": "trace-rag-1"},
        "retrieval_metrics": {
            "query": "苹果划痕怎么判定",
            "rag_space_id": "rag-food",
            "hit_count": 2,
            "latency_ms": 320,
            "top_score": 0.87,
            "top_k": 5,
        },
        "retrieved_chunks": [
            {
                "chunk_id": "chunk-1",
                "title": "苹果外观标准",
                "source": "apple-spec.pdf",
                "quote": "划痕长度超过 3mm 判定为不合格",
                "score": 0.87,
            },
            {
                "chunk_id": "chunk-2",
                "title": "苹果包装规范",
                "source": "packaging.docx",
                "quote": "轻微擦痕可接受",
                "score": 0.73,
            },
        ],
        "citations": [
            {
                "id": "rag-1",
                "title": "苹果外观标准",
                "source": "apple-spec.pdf",
                "quote": "划痕长度超过 3mm 判定为不合格",
                "score": 0.87,
                "kind": "rag",
            }
        ],
        "response_payload": {
            "answer": "超过 3mm 的划痕通常判定为不合格。",
            "summary": "基于知识库回答",
        },
        "ext": {
            "selected_rag_space": {
                "id": "rag-food",
                "name": "食品知识库",
            }
        },
    }

    await _persist_rag_query_log(object(), state)

    assert len(payloads) == 1
    log = payloads[0]
    assert log["query"] == "苹果划痕怎么判定"
    assert log["rag_space_id"] == "rag-food"
    assert log["top_k"] == 5
    assert log["hit_count"] == 2
    assert log["hit_rate"] == 0.4
    assert log["trace_id"] == "trace-rag-1"
    assert log["metadata_json"]["top_sources"] == ["apple-spec.pdf", "packaging.docx"]
    assert log["metadata_json"]["rule_hits"] == []
    assert log["metadata_json"]["verdict"] is None
    assert log["metadata_json"]["product_family"] is None
    assert log["metadata_json"]["expectation_matched"] is None
    assert log["metadata_json"]["retrieval_config"]["top_k"] == 5
    assert log["metadata_json"]["retrieved_chunks"][0]["chunk_id"] == "chunk-1"
    assert log["metadata_json"]["used_citations"][0]["id"] == "rag-1"
    assert log["metadata_json"]["answer"] == "超过 3mm 的划痕通常判定为不合格。"


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
async def test_quality_gate_does_not_rewrite_plain_rag_answers():
    original_answer = "tgg"
    state = {
        "intent": "rag_qa",
        "reasoning": {"answer": original_answer},
        "citations": [{"id": "doc-1"}],
        "retrieval_metrics": {"hit_count": 1},
    }

    updated = await quality_gate(state)

    assert updated["quality"] == {}
    assert updated["reasoning"]["answer"] == original_answer


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
async def test_knowledge_retrieves_for_plain_rag_qa(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_resolve_and_search_system_rag(**kwargs):
        captured.update(kwargs)
        return {
            "rag_space_id": kwargs["user_rag_space_id"],
            "rag_space_ids": [kwargs["user_rag_space_id"]],
            "rag_space_names": ["My Space"],
            "latency_ms": 3,
            "hits": [{"id": "doc-1", "title": "1.txt", "text": "我的名字叫tgg", "score": 0.9}],
        }

    monkeypatch.setattr("agent.subgraphs.quality_chat.graph.resolve_and_search_system_rag", fake_resolve_and_search_system_rag)

    state = {
        "intent": "rag_qa",
        "query": "我叫什么名字",
        "session_id": "session-1",
        "org_id": "org-1",
        "user_id": "user-1",
        "trace": {},
        "ext": {"selected_rag_space_id": "space-1"},
    }

    updated = await knowledge(state)

    assert captured["query"] == "我叫什么名字"
    assert captured["org_id"] == "org-1"
    assert captured["user_id"] == "user-1"
    assert captured["user_rag_space_id"] == "space-1"
    assert updated["retrieval_metrics"]["skipped"] is False
    assert updated["citations"][0]["quote"] == "我的名字叫tgg"


@pytest.mark.asyncio
async def test_knowledge_filters_retrieval_by_current_user(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_resolve_and_search_system_rag(**kwargs):
        captured.update(kwargs)
        return {
            "rag_space_id": kwargs["user_rag_space_id"],
            "rag_space_ids": [kwargs["user_rag_space_id"]],
            "rag_space_names": ["My Space"],
            "latency_ms": 3,
            "hits": [],
        }

    monkeypatch.setattr("agent.subgraphs.quality_chat.graph.resolve_and_search_system_rag", fake_resolve_and_search_system_rag)

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

    assert captured["org_id"] == "org-1"
    assert captured["user_id"] == "user-1"
    assert captured["user_rag_space_id"] == "space-1"
    assert updated["retrieval_metrics"]["rag_space_id"] == "space-1"


@pytest.mark.asyncio
async def test_knowledge_includes_scope_node_filters_when_present(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_resolve_and_search_system_rag(**kwargs):
        captured.update(kwargs)
        return {
            "rag_space_id": kwargs["user_rag_space_id"],
            "rag_space_ids": [kwargs["user_rag_space_id"]],
            "rag_space_names": ["My Space"],
            "latency_ms": 3,
            "hits": [],
        }

    monkeypatch.setattr("agent.subgraphs.quality_chat.graph.resolve_and_search_system_rag", fake_resolve_and_search_system_rag)

    state = {
        "intent": "quality_qa",
        "query": "quality question",
        "session_id": "session-1",
        "org_id": "org-1",
        "user_id": "user-1",
        "trace": {},
        "ext": {
            "selected_rag_space_id": "space-1",
            "selected_rag_scope_node_ids": ["folder-1", "folder-2"],
        },
    }

    await knowledge(state)

    assert captured["org_id"] == "org-1"
    assert captured["user_id"] == "user-1"
    assert captured["user_rag_space_id"] == "space-1"
    assert captured["scope_node_ids"] == ["folder-1", "folder-2"]


@pytest.mark.asyncio
async def test_knowledge_accepts_rag_scope_payload(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_resolve_and_search_system_rag(**kwargs):
        captured.update(kwargs)
        return {
            "rag_space_id": kwargs["user_rag_space_id"],
            "rag_space_ids": [kwargs["user_rag_space_id"]],
            "rag_space_names": ["My Space"],
            "latency_ms": 3,
            "hits": [],
        }

    monkeypatch.setattr("agent.subgraphs.quality_chat.graph.resolve_and_search_system_rag", fake_resolve_and_search_system_rag)

    state = {
        "intent": "quality_qa",
        "query": "我叫什么名字",
        "session_id": "session-1",
        "org_id": "org-1",
        "user_id": "user-1",
        "trace": {},
        "ext": {
            "rag_scope": {
                "enabled": True,
                "rag_space_id": "space-1",
                "scope_node_ids": ["folder-1"],
                "scope_mode": "folder",
            },
        },
    }

    await knowledge(state)

    assert captured["org_id"] == "org-1"
    assert captured["user_id"] == "user-1"
    assert captured["user_rag_space_id"] == "space-1"
    assert captured["scope_node_ids"] == ["folder-1"]


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


@pytest.mark.asyncio
async def test_cancel_chat_message_marks_assistant_interrupted(monkeypatch):
    updates: list[dict] = []
    touches: list[dict] = []
    published: list[tuple[str, dict]] = []

    class FakeSession:
        async def commit(self):
            return None

    @asynccontextmanager
    async def fake_get_session():
        yield FakeSession()

    class FakeChatSessionRepository:
        def __init__(self, _session):
            pass

        async def get(self, org_id: str, user_id: str, session_id: str):
            assert org_id == "org-1"
            assert user_id == "user-1"
            assert session_id == "session-1"
            return object()

        async def touch(self, org_id: str, user_id: str, session_id: str):
            touches.append({"org_id": org_id, "user_id": user_id, "session_id": session_id})

    class FakeMessage:
        session_id = "session-1"
        role = "assistant"
        payload = {"workflow_run_id": "wf-1", "status": "running"}

    class FakeChatMessageRepository:
        def __init__(self, _session):
            pass

        async def get(self, org_id: str, message_id: str):
            assert org_id == "org-1"
            assert message_id == "assistant-1"
            return FakeMessage()

        async def update_assistant_message(self, **kwargs):
            updates.append(kwargs)
            return SimpleNamespace(
                id="assistant-1",
                session_id="session-1",
                seq_no=2,
                role="assistant",
                message_type=kwargs["message_type"],
                content=kwargs["content"],
                payload=kwargs["payload"],
                created_at=None,
            )

    class FakeBroker:
        async def publish(self, session_id: str, event: dict):
            published.append((session_id, event))

    async def sleeper():
        await asyncio.sleep(60)

    task = asyncio.create_task(sleeper())
    chat_service_mod._ACTIVE_CHAT_WORKFLOWS["wf-1"] = task
    chat_service_mod._ACTIVE_CHAT_MESSAGE_TO_WORKFLOW["assistant-1"] = "wf-1"

    monkeypatch.setattr(chat_service_mod, "get_session", fake_get_session)
    monkeypatch.setattr(chat_service_mod, "ChatSessionRepository", FakeChatSessionRepository)
    monkeypatch.setattr(chat_service_mod, "ChatMessageRepository", FakeChatMessageRepository)
    monkeypatch.setattr(chat_service_mod, "chat_stream_broker", FakeBroker())

    service = ChatService(
        org_id="org-1",
        user_id="user-1",
        current=CurrentUser(user_id="user-1", org_id="org-1", role="user", roles=["user"]),
    )
    response = await service.cancel_message("session-1", "assistant-1")

    assert response.message_type == "interrupted"
    assert updates[0]["payload"]["status"] == "interrupted"
    assert touches == [{"org_id": "org-1", "user_id": "user-1", "session_id": "session-1"}]
    assert published[0][0] == "session-1"
    assert published[0][1]["event"] == "message_final"
    assert task.cancelled() or task.cancelling()

    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
    chat_service_mod._ACTIVE_CHAT_WORKFLOWS.pop("wf-1", None)
    chat_service_mod._ACTIVE_CHAT_MESSAGE_TO_WORKFLOW.pop("assistant-1", None)
