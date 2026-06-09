from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.chat_session_summary_service import ChatSessionSummaryService
from app.services.short_term_memory_service import ShortTermMemoryService


class FakeSession:
    def __init__(self):
        self.flushed = False

    async def flush(self):
        self.flushed = True


class FakeMessage:
    def __init__(
        self,
        role: str,
        content: str,
        seq_no: int,
        *,
        payload: dict | None = None,
        message_type: str = "text",
    ):
        self.role = role
        self.content = content
        self.seq_no = seq_no
        self.payload = payload
        self.message_type = message_type


@pytest.mark.asyncio
async def test_short_term_memory_uses_latest_assistant_payload(monkeypatch):
    chat_session = SimpleNamespace(
        context_summary="用户正在创建质检任务。",
        context_facts_json={"preferred_language": "zh-CN"},
    )
    messages = [
        FakeMessage("user", "old question", 1),
        FakeMessage(
            "assistant",
            "old answer",
            2,
            payload={"pending_action": {"type": "old_action"}},
        ),
        FakeMessage("user", "补充信息", 3),
        FakeMessage(
            "assistant",
            "new answer",
            4,
            payload={
                "awaiting_confirmation": True,
                "task_draft": {"name": "new task"},
                "missing_slots": ["standard"],
                "selected_rag_space": {"id": "rag-1", "name": "标准库"},
            },
        ),
        FakeMessage("user", "current question", 5),
    ]

    class FakeSessionRepo:
        def __init__(self, _session):
            pass

        async def get(self, org_id, user_id, session_id):
            return chat_session

    class FakeMessageRepo:
        def __init__(self, _session):
            pass

        async def list_for_session(self, *, org_id, session_id, after_seq=0, limit=60):
            return messages

    import app.repositories.chat_repo as chat_repo

    monkeypatch.setattr(chat_repo, "ChatSessionRepository", FakeSessionRepo)
    monkeypatch.setattr(chat_repo, "ChatMessageRepository", FakeMessageRepo)
    monkeypatch.setattr(ShortTermMemoryService, "_resolve_model_context_window", lambda self: _async_value(8192))

    ctx = await ShortTermMemoryService(FakeSession(), "org-1").build_context(
        user_id="user-1",
        session_id="session-1",
        current_user_seq_no=5,
    )

    assert ctx["conversation_summary"] == "用户正在创建质检任务。"
    assert ctx["session_facts"] == {"preferred_language": "zh-CN"}
    assert ctx["recent_messages"] == [
        {"role": "user", "content": "old question"},
        {"role": "assistant", "content": "old answer"},
        {"role": "user", "content": "补充信息"},
        {"role": "assistant", "content": "new answer"},
    ]
    assert ctx["pending_action"]["type"] == "fill_slots"
    assert ctx["task_draft"] == {"name": "new task"}
    assert ctx["selected_rag_space"] == {"id": "rag-1", "name": "标准库"}


@pytest.mark.asyncio
async def test_short_term_memory_requires_existing_session(monkeypatch):
    class FakeSessionRepo:
        def __init__(self, _session):
            pass

        async def get(self, org_id, user_id, session_id):
            return None

    class FakeMessageRepo:
        def __init__(self, _session):
            pass

    import app.repositories.chat_repo as chat_repo

    monkeypatch.setattr(chat_repo, "ChatSessionRepository", FakeSessionRepo)
    monkeypatch.setattr(chat_repo, "ChatMessageRepository", FakeMessageRepo)

    with pytest.raises(ValueError, match="chat session not found"):
        await ShortTermMemoryService(FakeSession(), "org-1").build_context(
            user_id="user-1",
            session_id="missing-session",
            current_user_seq_no=10,
        )


@pytest.mark.asyncio
async def test_short_term_memory_marks_truncated_by_char_budget(monkeypatch):
    chat_session = SimpleNamespace(context_summary="", context_facts_json={})
    messages = [
        FakeMessage("user", "x" * 1000, 1),
        FakeMessage("assistant", "y" * 1000, 2),
        FakeMessage("user", "final useful message", 3),
    ]

    class FakeSessionRepo:
        def __init__(self, _session):
            pass

        async def get(self, org_id, user_id, session_id):
            return chat_session

    class FakeMessageRepo:
        def __init__(self, _session):
            pass

        async def list_for_session(self, *, org_id, session_id, after_seq=0, limit=60):
            return messages

    import app.repositories.chat_repo as chat_repo

    monkeypatch.setattr(chat_repo, "ChatSessionRepository", FakeSessionRepo)
    monkeypatch.setattr(chat_repo, "ChatMessageRepository", FakeMessageRepo)
    monkeypatch.setattr(ShortTermMemoryService, "_resolve_model_context_window", lambda self: _async_value(8192))

    ctx = await ShortTermMemoryService(FakeSession(), "org-1").build_context(
        user_id="user-1",
        session_id="session-1",
        current_user_seq_no=4,
        max_prompt_chars=200,
    )

    assert ctx["token_budget"]["truncated"] is True
    assert ctx["recent_messages"][-1] == {"role": "user", "content": "final useful message"}


@pytest.mark.asyncio
async def test_chat_session_summary_updates_context_fields(monkeypatch):
    session = FakeSession()
    chat_session = SimpleNamespace(
        context_summary="已有摘要",
        context_facts_json={"preferred_language": "zh-CN"},
        summary_seq_no=0,
        context_updated_at=None,
    )
    messages = [
        FakeMessage("user", "a" * 1200, i)
        for i in range(1, 13)
    ]

    class FakeSessionRepo:
        def __init__(self, _session):
            pass

        async def get(self, org_id, user_id, session_id):
            return chat_session

    class FakeMessageRepo:
        def __init__(self, _session):
            pass

        async def list_for_session(self, *, org_id, session_id, after_seq=0, limit=100):
            return messages

    async def fake_llm_summarize(self, transcript):
        return "新增摘要", {"current_work": "inspection"}

    import app.repositories.chat_repo as chat_repo

    monkeypatch.setattr(chat_repo, "ChatSessionRepository", FakeSessionRepo)
    monkeypatch.setattr(chat_repo, "ChatMessageRepository", FakeMessageRepo)
    monkeypatch.setattr(ChatSessionSummaryService, "_llm_summarize", fake_llm_summarize)

    summarized = await ChatSessionSummaryService(session, "org-1", "user-1").maybe_summarize("session-1")

    assert summarized is True
    assert chat_session.context_summary == "已有摘要\n新增摘要"
    assert chat_session.context_facts_json == {
        "preferred_language": "zh-CN",
        "current_work": "inspection",
    }
    assert chat_session.summary_seq_no == 6
    assert session.flushed is True


async def _async_value(value):
    return value
