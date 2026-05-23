from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from app.schemas.chat import ChatTaskSubmitRequest
from app.services import chat_service as chat_mod
from app.services.chat_service import ChatService
from app.schemas.user import CurrentUser
from agent.subgraphs.quality_chat.graph import task_executor


@pytest.mark.asyncio
async def test_chat_task_submit_is_blocked_and_does_not_create_task(monkeypatch):
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
            return object()

        async def touch(self, org_id: str, user_id: str, session_id: str):
            return None

    created_messages: list[dict] = []

    class FakeChatMessageRepository:
        def __init__(self, _session):
            pass

        async def create(self, **kwargs):
            created_messages.append(kwargs)
            return type(
                "Message",
                (),
                {
                    "id": "assistant-blocked",
                    "session_id": kwargs["session_id"],
                    "seq_no": 1,
                    "role": kwargs["role"],
                    "message_type": kwargs["message_type"],
                    "content": kwargs["content"],
                    "payload": kwargs["payload"],
                    "created_at": None,
                },
            )()

    monkeypatch.setattr(chat_mod, "get_session", fake_get_session)
    monkeypatch.setattr(chat_mod, "ChatSessionRepository", FakeChatSessionRepository)
    monkeypatch.setattr(chat_mod, "ChatMessageRepository", FakeChatMessageRepository)

    current = CurrentUser(user_id="user-1", org_id="org-1", role="user")
    result = await ChatService(org_id="org-1", user_id="user-1", current=current).submit_task(
        session_id="session-1",
        payload=ChatTaskSubmitRequest(
            product_id="P001",
            spec_code="STD-1",
            image_urls=["https://example.test/a.png"],
            priority=5,
        ),
    )

    assert result.message_type == "action_blocked"
    assert "质量检测任务页面" in result.content
    assert created_messages[0]["payload"]["action_state"] == "blocked"


@pytest.mark.asyncio
async def test_quality_chat_graph_task_executor_blocks_formal_task_creation():
    state = {
        "action_state": "task_create_requested",
        "task_draft": {
            "product_id": "P001",
            "spec_code": "STD-1",
            "image_urls": ["https://example.test/a.png"],
            "priority": 5,
        },
        "session_id": "session-1",
        "request_id": "request-1",
        "org_id": "org-1",
        "user_id": "user-1",
        "missing_slots": [],
    }

    result = await task_executor(state)  # type: ignore[arg-type]

    assert result["created_task"] is None
    assert result["action_state"] == "blocked"
    assert result["pending_action"] == "create_task"
    assert "质量检测任务页面" in result["reasoning"]["answer"]
