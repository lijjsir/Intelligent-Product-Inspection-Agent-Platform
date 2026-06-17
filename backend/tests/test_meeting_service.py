from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError as PydanticValidationError

from agent.router.contracts import AgentRouteDecision, AgentRouterOutput
from app.core.exceptions import ForbiddenError, ValidationError
from app.api.v1 import meetings as meeting_api_mod
from app.services import meeting_agent_service as meeting_agent_mod
from app.services import meeting_service as meeting_service_mod
from app.repositories.meeting_repo import MeetingRepository
from app.schemas.meeting import (
    MeetingActionItemCreateRequest,
    MeetingAgentRunRequest,
    MeetingMemoryExtractRequest,
    MeetingMemoryUpdateRequest,
)


class FakeSession:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


class FakeUser:
    def __init__(self, username: str):
        self.username = username


class FakeUsersRepo:
    def __init__(self):
        self.users = {("org-1", "user-1"): FakeUser("alice")}

    async def get_by_id(self, org_id: str, user_id: str):
        return self.users.get((org_id, user_id))


class FakeMeetingRepo:
    def __init__(self):
        self.created_messages: list[dict] = []
        self.messages: list[SimpleNamespace] = []

    async def get_room(self, org_id: str, room_id: str):
        return SimpleNamespace(id=room_id, org_id=org_id, created_by="user-1")

    async def get_member(self, org_id: str, room_id: str, user_id: str):
        return SimpleNamespace(id="member-1", org_id=org_id, room_id=room_id, user_id=user_id)

    async def create_message(self, **kwargs):
        metadata = dict(kwargs.get("metadata_json") or {})
        private_recipient_user_id = kwargs.get("private_recipient_user_id")
        if private_recipient_user_id:
            metadata["private_recipient_user_id"] = private_recipient_user_id
        message = SimpleNamespace(
            id=kwargs.get("message_id", "msg-1"),
            room_id=kwargs["room_id"],
            user_id=kwargs["user_id"],
            username=kwargs["username"],
            seq_no=len(self.created_messages) + 1,
            content=kwargs["content"],
            message_type=kwargs.get("message_type", "user"),
            agent_id=kwargs.get("agent_id"),
            mentions=kwargs.get("mentions"),
            quote_message_id=kwargs.get("quote_message_id"),
            metadata_json=metadata or None,
            private_recipient_user_id=metadata.get("private_recipient_user_id"),
            created_at=None,
            updated_at=None,
        )
        self.created_messages.append(kwargs)
        self.messages.append(message)
        return message

    async def list_messages(
        self,
        *,
        org_id: str,
        room_id: str,
        after_seq: int = 0,
        limit: int = 200,
        visible_user_id: str | None = None,
    ):
        results = []
        for message in self.messages:
            if message.room_id != room_id or message.seq_no <= after_seq:
                continue
            recipient_id = getattr(message, "private_recipient_user_id", None)
            if recipient_id and visible_user_id not in {message.user_id, recipient_id}:
                continue
            results.append(message)
        return results[:limit]


def test_meeting_stream_private_event_visible_to_sender_and_recipient_only():
    event = {"event": "message_created", "private_user_ids": ["user-1", "user-2"]}

    assert meeting_api_mod._can_see_meeting_stream_event(event, "user-1") is True
    assert meeting_api_mod._can_see_meeting_stream_event(event, "user-2") is True
    assert meeting_api_mod._can_see_meeting_stream_event(event, "user-3") is False


def test_meeting_stream_private_message_metadata_is_filtered_without_private_user_list():
    event = {
        "event": "message_created",
        "message": {
            "user_id": "user-1",
            "metadata_json": {"private_recipient_user_id": "user-2"},
        },
    }

    assert meeting_api_mod._can_see_meeting_stream_event(event, "user-1") is True
    assert meeting_api_mod._can_see_meeting_stream_event(event, "user-2") is True
    assert meeting_api_mod._can_see_meeting_stream_event(event, "user-3") is False


def test_meeting_stream_public_event_is_visible_to_room_members():
    event = {"event": "message_created", "message": {"user_id": "user-1", "metadata_json": {}}}

    assert meeting_api_mod._can_see_meeting_stream_event(event, "user-3") is True


@pytest.mark.asyncio
async def test_send_message_triggers_mentions_only_not_autonomous(monkeypatch):
    fake_repo = FakeMeetingRepo()
    fake_users = FakeUsersRepo()
    fake_session = FakeSession()
    invoked: list[dict] = []
    autonomous_called = False

    class FakeAgentService:
        async def invoke_agent(self, **kwargs):
            invoked.append(kwargs)

        async def check_autonomous_participation(self, **kwargs):
            nonlocal autonomous_called
            autonomous_called = True

    monkeypatch.setattr(meeting_service_mod, "MeetingRepository", lambda session: fake_repo)
    monkeypatch.setattr(meeting_service_mod, "MeetingAgentService", FakeAgentService)
    monkeypatch.setattr(meeting_service_mod.asyncio, "create_task", lambda coro: coro.close())

    service = meeting_service_mod.MeetingService(fake_session, "org-1", "user-1")
    service._repo = fake_repo
    service._users = fake_users

    async def fake_parse_mentions(content: str, room_id: str):
        return [{"agent_id": "agent-1", "agent_name": "质检Agent"}]

    service._parse_mentions = fake_parse_mentions

    result = await service.send_message("room-1", "@质检Agent 看一下")

    assert result.content == "@质检Agent 看一下"
    assert autonomous_called is False
    assert fake_session.commits == 1
    assert fake_repo.created_messages[0]["mentions"] == [{"agent_id": "agent-1", "agent_name": "质检Agent"}]


@pytest.mark.asyncio
async def test_send_message_routes_legacy_ai_alias_to_general_agent(monkeypatch):
    fake_repo = FakeMeetingRepo()
    fake_users = FakeUsersRepo()
    fake_session = FakeSession()
    scheduled_tasks: list[asyncio.Task] = []
    invoked_queries: list[tuple[str, str]] = []
    real_create_task = asyncio.create_task

    class FakeAgentService:
        async def invoke_agent(self, **kwargs):
            raise AssertionError("room agent invocation should not run for built-in total agent alias")

    async def fake_invoke_general_agent_reply(*, room_id: str, query: str):
        invoked_queries.append((room_id, query))

    def tracking_create_task(coro):
        task = real_create_task(coro)
        scheduled_tasks.append(task)
        return task

    monkeypatch.setattr(meeting_service_mod, "MeetingRepository", lambda session: fake_repo)
    monkeypatch.setattr(meeting_service_mod, "MeetingAgentService", FakeAgentService)
    monkeypatch.setattr(meeting_service_mod.asyncio, "create_task", tracking_create_task)

    service = meeting_service_mod.MeetingService(fake_session, "org-1", "user-1")
    service._repo = fake_repo
    service._users = fake_users
    service._invoke_general_agent_reply = fake_invoke_general_agent_reply

    async def fake_parse_mentions(content: str, room_id: str):
        return []

    service._parse_mentions = fake_parse_mentions

    result = await service.send_message("room-1", "@AI 助手 你能做什么")

    assert result.content == "@AI 助手 你能做什么"
    assert fake_session.commits == 1
    assert fake_repo.created_messages[0]["mentions"] == [{"agent_id": "general_agent", "agent_name": "会议Agent"}]
    assert len(scheduled_tasks) == 1
    await asyncio.wait_for(scheduled_tasks[0], timeout=1)
    assert invoked_queries == [("room-1", "@AI 助手 你能做什么")]


@pytest.mark.asyncio
async def test_send_message_blocks_closed_room():
    class ClosedRoomRepo(FakeMeetingRepo):
        async def get_room(self, org_id: str, room_id: str):
            return SimpleNamespace(id=room_id, org_id=org_id, created_by="user-1", status="closed")

    service = meeting_service_mod.MeetingService(FakeSession(), "org-1", "user-1")
    service._repo = ClosedRoomRepo()
    service._users = FakeUsersRepo()

    with pytest.raises(ForbiddenError):
        await service.send_message("room-1", "关闭后不能继续发言")

    assert service._repo.created_messages == []


@pytest.mark.asyncio
async def test_send_message_triggers_general_agent_special_mention(monkeypatch):
    fake_repo = FakeMeetingRepo()
    fake_users = FakeUsersRepo()
    fake_session = FakeSession()
    scheduled_tasks: list[asyncio.Task] = []
    invoked_queries: list[tuple[str, str]] = []
    real_create_task = asyncio.create_task

    async def fake_invoke_general_agent_reply(*, room_id: str, query: str):
        invoked_queries.append((room_id, query))

    def tracking_create_task(coro):
        task = real_create_task(coro)
        scheduled_tasks.append(task)
        return task

    monkeypatch.setattr(meeting_service_mod, "MeetingRepository", lambda session: fake_repo)
    monkeypatch.setattr(meeting_service_mod.asyncio, "create_task", tracking_create_task)

    service = meeting_service_mod.MeetingService(fake_session, "org-1", "user-1")
    service._repo = fake_repo
    service._users = fake_users
    service._invoke_general_agent_reply = fake_invoke_general_agent_reply

    async def fake_parse_mentions(content: str, room_id: str):
        return []

    service._parse_mentions = fake_parse_mentions

    result = await service.send_message("room-1", "@会议Agent 帮我总结这次会议")

    assert result.content == "@会议Agent 帮我总结这次会议"
    assert fake_session.commits == 1
    assert fake_repo.created_messages[0]["mentions"] == [{"agent_id": "general_agent", "agent_name": "会议Agent"}]
    assert len(scheduled_tasks) == 1
    await asyncio.wait_for(scheduled_tasks[0], timeout=1)
    assert invoked_queries == [("room-1", "@会议Agent 帮我总结这次会议")]


@pytest.mark.asyncio
async def test_send_message_can_skip_general_agent_auto_trigger(monkeypatch):
    fake_repo = FakeMeetingRepo()
    fake_users = FakeUsersRepo()
    fake_session = FakeSession()
    scheduled_tasks: list[asyncio.Task] = []
    real_create_task = asyncio.create_task

    def tracking_create_task(coro):
        task = real_create_task(coro)
        scheduled_tasks.append(task)
        return task

    monkeypatch.setattr(meeting_service_mod, "MeetingRepository", lambda session: fake_repo)
    monkeypatch.setattr(meeting_service_mod.asyncio, "create_task", tracking_create_task)

    service = meeting_service_mod.MeetingService(fake_session, "org-1", "user-1")
    service._repo = fake_repo
    service._users = fake_users

    async def fake_parse_mentions(content: str, room_id: str):
        return []

    service._parse_mentions = fake_parse_mentions

    result = await service.send_message(
        "room-1",
        "@会议Agent 帮我总结这次会议",
        skip_agent_trigger=True,
    )

    assert result.content == "@会议Agent 帮我总结这次会议"
    assert fake_session.commits == 1
    assert fake_repo.created_messages[0]["mentions"] == [{"agent_id": "general_agent", "agent_name": "会议Agent"}]
    assert scheduled_tasks == []


@pytest.mark.asyncio
async def test_private_message_is_visible_to_sender_and_recipient_only(monkeypatch):
    fake_repo = FakeMeetingRepo()
    fake_session = FakeSession()
    published: list[dict] = []

    async def fake_publish(room_id: str, event: dict):
        published.append(event)

    monkeypatch.setattr(meeting_service_mod.meeting_stream_broker, "publish", fake_publish)

    sender_service = meeting_service_mod.MeetingService(fake_session, "org-1", "user-1")
    sender_service._repo = fake_repo
    sender_service._users = FakeUsersRepo()

    result = await sender_service.send_message(
        "room-1",
        "这条只给 Bob",
        private_recipient_user_id="user-2",
        skip_agent_trigger=True,
    )

    assert result.private_recipient_user_id == "user-2"
    assert fake_repo.created_messages[0]["private_recipient_user_id"] == "user-2"
    assert set(published[-1]["private_user_ids"]) == {"user-1", "user-2"}

    recipient_service = meeting_service_mod.MeetingService(fake_session, "org-1", "user-2")
    recipient_service._repo = fake_repo
    recipient_service._users = FakeUsersRepo()
    recipient_messages = await recipient_service.list_messages("room-1")
    assert [message.id for message in recipient_messages] == [result.id]

    third_party_service = meeting_service_mod.MeetingService(fake_session, "org-1", "user-3")
    third_party_service._repo = fake_repo
    third_party_service._users = FakeUsersRepo()
    third_party_messages = await third_party_service.list_messages("room-1")
    assert third_party_messages == []


@pytest.mark.asyncio
async def test_private_message_with_agent_mention_stays_private(monkeypatch):
    fake_repo = FakeMeetingRepo()
    fake_session = FakeSession()
    scheduled_tasks: list[asyncio.Task] = []

    def tracking_create_task(coro):
        scheduled_tasks.append(coro)
        coro.close()

    monkeypatch.setattr(meeting_service_mod.asyncio, "create_task", tracking_create_task)

    sender_service = meeting_service_mod.MeetingService(fake_session, "org-1", "user-1")
    sender_service._repo = fake_repo
    sender_service._users = FakeUsersRepo()

    result = await sender_service.send_message(
        "room-1",
        "@会议Agent 这句话也只给 Bob",
        private_recipient_user_id="user-2",
    )

    assert result.private_recipient_user_id == "user-2"
    assert result.mentions is None
    assert scheduled_tasks == []


@pytest.mark.asyncio
async def test_send_message_can_publish_quote_snapshot_only():
    fake_repo = FakeMeetingRepo()
    fake_session = FakeSession()
    service = meeting_service_mod.MeetingService(fake_session, "org-1", "user-1")
    service._repo = fake_repo
    service._users = FakeUsersRepo()

    result = await service.send_message(
        "room-1",
        "",
        quote_snapshot={
            "source": "agent",
            "author": "会议Agent",
            "content": "AI 侧栏里整理出的结论",
            "created_at": "2026-06-17T10:00:00",
        },
    )

    assert result.content == ""
    assert result.metadata_json["quote_snapshot"] == {
        "source": "agent",
        "author": "会议Agent",
        "content": "AI 侧栏里整理出的结论",
        "created_at": "2026-06-17T10:00:00",
    }
    assert fake_session.commits == 1


@pytest.mark.asyncio
async def test_update_message_blocks_recalled_message():
    class FakeRepo(FakeMeetingRepo):
        def __init__(self):
            super().__init__()
            self.update_called = False
            self.message = SimpleNamespace(
                id="msg-1",
                room_id="room-1",
                user_id="user-1",
                username="alice",
                seq_no=1,
                content="",
                message_type="user",
                agent_id=None,
                mentions=None,
                quote_message_id=None,
                metadata_json={
                    "recalled_at": "2026-06-17T10:00:00",
                    "original_content": "撤回前的内容",
                },
                private_recipient_user_id=None,
                created_at=datetime.utcnow(),
                updated_at=None,
            )

        async def get_message(self, org_id: str, room_id: str, message_id: str):
            return self.message if message_id == self.message.id else None

        async def update_message_content(self, **kwargs):
            self.update_called = True
            return self.message

    fake_repo = FakeRepo()
    fake_session = FakeSession()
    service = meeting_service_mod.MeetingService(fake_session, "org-1", "user-1")
    service._repo = fake_repo
    service._users = FakeUsersRepo()

    with pytest.raises(ForbiddenError, match="recalled messages cannot be edited"):
        await service.update_message("room-1", "msg-1", "改回原消息")

    assert fake_repo.update_called is False
    assert fake_session.commits == 0


@pytest.mark.asyncio
async def test_update_message_allows_old_owned_user_message(monkeypatch):
    class FakeRepo(FakeMeetingRepo):
        def __init__(self):
            super().__init__()
            self.message = SimpleNamespace(
                id="msg-1",
                room_id="room-1",
                user_id="user-1",
                username="alice",
                seq_no=1,
                content="old content",
                message_type="user",
                agent_id=None,
                mentions=None,
                quote_message_id=None,
                metadata_json={},
                private_recipient_user_id=None,
                created_at=datetime(2024, 1, 1, 9, 30, 0),
                updated_at=None,
            )

        async def get_message(self, org_id: str, room_id: str, message_id: str):
            return self.message if message_id == self.message.id else None

        async def update_message_content(self, **kwargs):
            self.message.content = kwargs["content"]
            self.message.metadata_json = kwargs["metadata_json"]
            return self.message

    published_events: list[dict] = []

    async def fake_publish(room_id: str, event: dict):
        published_events.append({"room_id": room_id, "event": event})

    monkeypatch.setattr(meeting_service_mod.meeting_stream_broker, "publish", fake_publish)

    fake_repo = FakeRepo()
    fake_session = FakeSession()
    service = meeting_service_mod.MeetingService(fake_session, "org-1", "user-1")
    service._repo = fake_repo
    service._users = FakeUsersRepo()

    result = await service.update_message("room-1", "msg-1", "new content")

    assert result.content == "new content"
    assert result.metadata_json is not None
    assert "edited_at" in result.metadata_json
    assert "recalled_at" not in result.metadata_json
    assert fake_session.commits == 1
    assert published_events[0]["room_id"] == "room-1"
    assert published_events[0]["event"]["message"].get("content") == "new content"


@pytest.mark.asyncio
async def test_update_private_message_is_blocked():
    class FakeRepo(FakeMeetingRepo):
        def __init__(self):
            super().__init__()
            self.update_called = False
            self.message = SimpleNamespace(
                id="msg-1",
                room_id="room-1",
                user_id="user-1",
                username="alice",
                seq_no=1,
                content="private content",
                message_type="user",
                agent_id=None,
                mentions=None,
                quote_message_id=None,
                metadata_json={"private_recipient_user_id": "user-2"},
                private_recipient_user_id="user-2",
                created_at=datetime.utcnow(),
                updated_at=None,
            )

        async def get_message(self, org_id: str, room_id: str, message_id: str):
            return self.message if message_id == self.message.id else None

        async def update_message_content(self, **kwargs):
            self.update_called = True
            return self.message

    fake_repo = FakeRepo()
    fake_session = FakeSession()
    service = meeting_service_mod.MeetingService(fake_session, "org-1", "user-1")
    service._repo = fake_repo
    service._users = FakeUsersRepo()

    with pytest.raises(ForbiddenError, match="private messages cannot be edited"):
        await service.update_message("room-1", "msg-1", "new private content")

    assert fake_repo.update_called is False
    assert fake_session.commits == 0


@pytest.mark.asyncio
async def test_recall_private_message_blocks_after_two_minutes():
    class FakeRepo(FakeMeetingRepo):
        def __init__(self):
            super().__init__()
            self.update_called = False
            self.message = SimpleNamespace(
                id="msg-1",
                room_id="room-1",
                user_id="user-1",
                username="alice",
                seq_no=1,
                content="private content",
                message_type="user",
                agent_id=None,
                mentions=None,
                quote_message_id=None,
                metadata_json={"private_recipient_user_id": "user-2"},
                private_recipient_user_id="user-2",
                created_at=datetime.utcnow() - timedelta(minutes=3),
                updated_at=None,
            )

        async def get_message(self, org_id: str, room_id: str, message_id: str):
            return self.message if message_id == self.message.id else None

        async def update_message_content(self, **kwargs):
            self.update_called = True
            return self.message

    fake_repo = FakeRepo()
    fake_session = FakeSession()
    service = meeting_service_mod.MeetingService(fake_session, "org-1", "user-1")
    service._repo = fake_repo
    service._users = FakeUsersRepo()

    with pytest.raises(ForbiddenError, match="消息只能在发送后 2 分钟内撤回"):
        await service.recall_message("room-1", "msg-1")

    assert fake_repo.update_called is False
    assert fake_session.commits == 0


@pytest.mark.asyncio
async def test_recall_private_message_within_two_minutes_publishes_to_both_users(monkeypatch):
    class FakeRepo(FakeMeetingRepo):
        def __init__(self):
            super().__init__()
            self.message = SimpleNamespace(
                id="msg-1",
                room_id="room-1",
                user_id="user-1",
                username="alice",
                seq_no=1,
                content="private content",
                message_type="user",
                agent_id=None,
                mentions=None,
                quote_message_id=None,
                metadata_json={"private_recipient_user_id": "user-2"},
                private_recipient_user_id="user-2",
                created_at=datetime.utcnow(),
                updated_at=None,
            )

        async def get_message(self, org_id: str, room_id: str, message_id: str):
            return self.message if message_id == self.message.id else None

        async def update_message_content(self, **kwargs):
            self.message.content = kwargs["content"]
            self.message.metadata_json = kwargs["metadata_json"]
            self.message.private_recipient_user_id = self.message.metadata_json.get("private_recipient_user_id")
            return self.message

    published_events: list[dict] = []

    async def fake_publish(room_id: str, event: dict):
        published_events.append(event)

    monkeypatch.setattr(meeting_service_mod.meeting_stream_broker, "publish", fake_publish)

    fake_repo = FakeRepo()
    fake_session = FakeSession()
    service = meeting_service_mod.MeetingService(fake_session, "org-1", "user-1")
    service._repo = fake_repo
    service._users = FakeUsersRepo()

    result = await service.recall_message("room-1", "msg-1")

    assert result.content == ""
    assert result.metadata_json["recalled_at"]
    assert set(published_events[-1]["private_user_ids"]) == {"user-1", "user-2"}
    assert fake_session.commits == 1


@pytest.mark.asyncio
async def test_recall_public_message_blocks_after_two_minutes():
    class FakeRepo(FakeMeetingRepo):
        def __init__(self):
            super().__init__()
            self.update_called = False
            self.message = SimpleNamespace(
                id="msg-1",
                room_id="room-1",
                user_id="user-1",
                username="alice",
                seq_no=1,
                content="public content",
                message_type="user",
                agent_id=None,
                mentions=None,
                quote_message_id=None,
                metadata_json={},
                private_recipient_user_id=None,
                created_at=datetime.utcnow() - timedelta(minutes=3),
                updated_at=None,
            )

        async def get_message(self, org_id: str, room_id: str, message_id: str):
            return self.message if message_id == self.message.id else None

        async def update_message_content(self, **kwargs):
            self.update_called = True
            return self.message

    fake_repo = FakeRepo()
    fake_session = FakeSession()
    service = meeting_service_mod.MeetingService(fake_session, "org-1", "user-1")
    service._repo = fake_repo
    service._users = FakeUsersRepo()

    with pytest.raises(ForbiddenError, match="消息只能在发送后 2 分钟内撤回"):
        await service.recall_message("room-1", "msg-1")

    assert fake_repo.update_called is False
    assert fake_session.commits == 0


@pytest.mark.asyncio
async def test_leave_room_removes_non_creator_membership(monkeypatch):
    class FakeRepo(FakeMeetingRepo):
        def __init__(self):
            super().__init__()
            self.removed: list[tuple[str, str, str]] = []

        async def get_room(self, org_id: str, room_id: str):
            return SimpleNamespace(id=room_id, org_id=org_id, created_by="user-1")

        async def get_member(self, org_id: str, room_id: str, user_id: str):
            return SimpleNamespace(id="member-2", org_id=org_id, room_id=room_id, user_id=user_id, role="member")

        async def remove_member(self, org_id: str, room_id: str, user_id: str):
            self.removed.append((org_id, room_id, user_id))
            return True

    published_events: list[dict] = []

    async def fake_publish(room_id: str, event: dict):
        published_events.append(event)

    fake_repo = FakeRepo()
    fake_session = FakeSession()
    service = meeting_service_mod.MeetingService(fake_session, "org-1", "user-2")
    service._repo = fake_repo
    service._users = FakeUsersRepo()
    monkeypatch.setattr(meeting_service_mod.meeting_stream_broker, "publish", fake_publish)

    await service.leave_room("room-1")

    assert fake_repo.removed == [("org-1", "room-1", "user-2")]
    assert fake_session.commits == 1
    assert published_events[-1]["message"]["message_type"] == "system"


@pytest.mark.asyncio
async def test_leave_room_blocks_creator():
    fake_repo = FakeMeetingRepo()
    fake_session = FakeSession()
    service = meeting_service_mod.MeetingService(fake_session, "org-1", "user-1")
    service._repo = fake_repo
    service._users = FakeUsersRepo()

    with pytest.raises(ForbiddenError, match="meeting creator cannot leave"):
        await service.leave_room("room-1")

    assert fake_session.commits == 0


@pytest.mark.asyncio
async def test_parse_mentions_requires_room_participant_and_supports_spaced_name():
    class FakeRoomAgent:
        def __init__(self, agent_id: str, role: str):
            self.agent_id = agent_id
            self.role = role

    class FakeRepo:
        async def get_agents(self, org_id: str, room_id: str):
            return [
                FakeRoomAgent("11111111-1111-1111-1111-111111111111", "participant"),
                FakeRoomAgent("22222222-2222-2222-2222-222222222222", "observer"),
            ]

        async def get_visible_agent_definition(self, org_id: str, agent_def_id: str):
            if agent_def_id == "11111111-1111-1111-1111-111111111111":
                return SimpleNamespace(name="AI 助手")
            if agent_def_id == "22222222-2222-2222-2222-222222222222":
                return SimpleNamespace(name="观察员")
            return None

    service = meeting_service_mod.MeetingService(FakeSession(), "org-1", "user-1")
    service._repo = FakeRepo()

    assert await service._parse_mentions("@AI 助手 帮我看一下", "room-1") == [
        {"agent_id": "11111111-1111-1111-1111-111111111111", "agent_name": "AI 助手"}
    ]
    assert await service._parse_mentions("@AI助手 帮我看一下", "room-1") == [
        {"agent_id": "11111111-1111-1111-1111-111111111111", "agent_name": "AI 助手"}
    ]
    assert await service._parse_mentions("@观察员 说一下", "room-1") == []


@pytest.mark.asyncio
async def test_list_room_members_resolves_host_and_usernames():
    class FakeRepo:
        async def get_room(self, org_id: str, room_id: str):
            return SimpleNamespace(id=room_id, org_id=org_id, created_by="user-1")

        async def get_member(self, org_id: str, room_id: str, user_id: str):
            return SimpleNamespace(id="member-current", org_id=org_id, room_id=room_id, user_id=user_id)

        async def list_members(self, org_id: str, room_id: str):
            return [
                SimpleNamespace(id="member-1", room_id=room_id, user_id="user-1", role="host", created_at=None),
                SimpleNamespace(id="member-2", room_id=room_id, user_id="user-2", role="member", created_at=None),
            ]

    fake_users = FakeUsersRepo()
    fake_users.users[("org-1", "user-2")] = FakeUser("bob")

    service = meeting_service_mod.MeetingService(FakeSession(), "org-1", "user-1")
    service._repo = FakeRepo()
    service._users = fake_users

    members = await service.list_room_members("room-1")

    assert [(member.username, member.role) for member in members] == [("alice", "host"), ("bob", "member")]


@pytest.mark.asyncio
async def test_meeting_creator_can_assign_member_host_role():
    member = SimpleNamespace(
        id="member-2",
        room_id="room-1",
        user_id="user-2",
        role="member",
        created_at=None,
    )

    class FakeRepo(FakeMeetingRepo):
        async def update_member_role(self, org_id: str, room_id: str, user_id: str, role: str):
            if user_id != member.user_id:
                return None
            member.role = role
            return member

    fake_users = FakeUsersRepo()
    fake_users.users[("org-1", "user-2")] = FakeUser("bob")

    service = meeting_service_mod.MeetingService(FakeSession(), "org-1", "user-1")
    service._repo = FakeRepo()
    service._users = fake_users

    updated = await service.update_member_role("room-1", "user-2", "host")

    assert updated.username == "bob"
    assert updated.role == "host"
    assert service._repo.created_messages[-1]["content"] == "成员「bob」已设为主持人。"


@pytest.mark.asyncio
async def test_non_creator_cannot_assign_member_role():
    class FakeRepo(FakeMeetingRepo):
        async def get_room(self, org_id: str, room_id: str):
            return SimpleNamespace(id=room_id, org_id=org_id, created_by="user-1")

        async def get_member(self, org_id: str, room_id: str, user_id: str):
            return SimpleNamespace(id="member-2", org_id=org_id, room_id=room_id, user_id=user_id, role="host")

    service = meeting_service_mod.MeetingService(FakeSession(), "org-1", "user-2")
    service._repo = FakeRepo()
    service._users = FakeUsersRepo()

    with pytest.raises(ForbiddenError):
        await service.update_member_role("room-1", "user-3", "host")


@pytest.mark.asyncio
async def test_parse_mentions_supports_single_agent_short_aliases():
    class FakeRoomAgent:
        agent_id = "11111111-1111-1111-1111-111111111111"
        role = "participant"

    class FakeRepo:
        async def get_agents(self, org_id: str, room_id: str):
            return [FakeRoomAgent()]

        async def get_visible_agent_definition(self, org_id: str, agent_def_id: str):
            return SimpleNamespace(name="Quality Bot")

    service = meeting_service_mod.MeetingService(FakeSession(), "org-1", "user-1")
    service._repo = FakeRepo()

    expected = [{"agent_id": "11111111-1111-1111-1111-111111111111", "agent_name": "Quality Bot"}]
    assert await service._parse_mentions("@agent please check this", "room-1") == expected
    assert await service._parse_mentions("@aent please check this", "room-1") == expected
    assert await service._parse_mentions("@ai please check this", "room-1") == expected


def test_contains_meeting_ai_mention_supports_spaced_and_compact_aliases():
    service = meeting_service_mod.MeetingService(FakeSession(), "org-1", "user-1")

    assert service._contains_meeting_ai_mention("@智能助手 你能做什么") is True
    assert service._contains_meeting_ai_mention("@AI 助手 你能做什么") is True
    assert service._contains_meeting_ai_mention("@AI助手 你能做什么") is True
    assert service._contains_meeting_ai_mention("请 @AI助手 帮忙") is True
    assert service._contains_meeting_ai_mention("@ai please help") is False


def test_contains_general_agent_mention_supports_spaced_and_compact_aliases():
    service = meeting_service_mod.MeetingService(FakeSession(), "org-1", "user-1")

    assert service._contains_general_agent_mention("@会议 Agent 帮我总结会议") is True
    assert service._contains_general_agent_mention("@会议Agent 帮我总结会议") is True
    assert service._contains_general_agent_mention("@agent 最近的质检任务情况是怎样的") is True
    assert service._contains_general_agent_mention("@总智能体 帮我总结会议") is True
    assert service._contains_general_agent_mention("@总Agent 帮我总结会议") is True
    assert service._contains_general_agent_mention("@总 Agent 帮我总结会议") is True
    assert service._contains_general_agent_mention("请 @general agent summarize") is True


def test_requested_domains_ignore_meeting_agent_mention_noise():
    service = meeting_service_mod.MeetingService(FakeSession(), "org-1", "user-1")

    domains = service._requested_domains_for_intent(
        "quality_task_status",
        "@会议Agent 为什么这次质检任务不合格",
    )

    assert "quality" in domains
    assert "standard" in domains
    assert "platform_ops" not in domains


@pytest.mark.asyncio
async def test_run_general_agent_routes_summary_and_creates_candidate_memory(monkeypatch):
    class FakeRepo(FakeMeetingRepo):
        def __init__(self):
            super().__init__()
            self.created_memory_items = []
            self.scope_bindings = []
            self.transfer_logs = []

        async def list_recent_messages(self, *, org_id: str, room_id: str, limit: int = 50):
            return [
                SimpleNamespace(id="msg-1", content="本次会议确认 P001 下月需要提高抽检比例", message_type="user"),
                SimpleNamespace(id="msg-2", content="行动项：Bob 负责复核检测标准", message_type="user"),
            ]

        async def list_memory_items_for_room(
            self,
            *,
            org_id: str,
            room_id: str,
            include_confirmed: bool = True,
            statuses=None,
            limit: int = 50,
        ):
            if statuses == ["active"]:
                return [
                    SimpleNamespace(
                        memory_id="mem_active_1",
                        content_summary="P001 最近批次风险上升",
                        content_json={"title": "P001 风险上升", "recommended_scope": "meeting"},
                        confidence=0.8,
                        status="active",
                        memory_type="decision",
                        created_by="user-1",
                        created_at=None,
                        updated_at=None,
                        scope_json={"meeting_room_id": room_id},
                    )
                ]
            return []

        async def create_memory_item(self, item):
            self.created_memory_items.append(item)
            return item

        async def create_memory_scope_binding(self, **kwargs):
            self.scope_bindings.append(kwargs)
            return SimpleNamespace(**kwargs)

        async def create_memory_transfer_log(self, **kwargs):
            self.transfer_logs.append(kwargs)
            return SimpleNamespace(**kwargs)

    published: list[dict] = []

    async def fake_publish(room_id: str, event: dict):
        published.append(event)

    fake_repo = FakeRepo()
    monkeypatch.setattr(meeting_service_mod.meeting_stream_broker, "publish", fake_publish)

    service = meeting_service_mod.MeetingService(FakeSession(), "org-1", "user-1")
    service._repo = fake_repo
    service._users = FakeUsersRepo()

    result = await service.run_general_agent(
        "room-1",
        MeetingAgentRunRequest(query="请总结本次会议并提取候选记忆", mode="meeting_summary"),
    )

    assert result.selected_subgraph == "meeting_summary"
    assert "当前会议上下文" in result.answer
    assert result.memory_sources[0].memory_id == "mem_active_1"
    assert len(result.candidate_memories) == 2
    assert fake_repo.created_messages[-1]["agent_id"] == "general_agent"
    assert fake_repo.created_messages[-1]["metadata_json"]["selected_subgraph"] == "meeting_summary"
    assert fake_repo.scope_bindings[0]["scope_type"] == "meeting_room"
    assert fake_repo.transfer_logs[0]["status"] == "candidate"
    assert published[-1]["event"] == "message_created"


@pytest.mark.asyncio
async def test_cancel_general_agent_run_prevents_final_message(monkeypatch):
    class FakeRepo(FakeMeetingRepo):
        async def list_recent_messages(self, *, org_id: str, room_id: str, limit: int = 50):
            if limit == 80:
                await service.cancel_general_agent_run(room_id, "wf-cancel-1")
            return [
                SimpleNamespace(id="msg-1", content="请总结本次会议", message_type="user"),
            ]

        async def list_memory_items_for_room(self, **kwargs):
            return []

    published: list[dict] = []

    async def fake_publish(room_id: str, event: dict):
        published.append(event)

    fake_repo = FakeRepo()
    fake_session = FakeSession()
    monkeypatch.setattr(meeting_service_mod.meeting_stream_broker, "publish", fake_publish)

    service = meeting_service_mod.MeetingService(fake_session, "org-1", "user-1")
    service._repo = fake_repo
    service._users = FakeUsersRepo()

    result = await service.run_general_agent(
        "room-1",
        MeetingAgentRunRequest(query="请总结本次会议", mode="meeting_summary", workflow_run_id="wf-cancel-1"),
    )

    assert result.message.metadata_json["cancelled"] is True
    assert result.answer == "会议Agent回复已停止"
    assert not fake_repo.created_messages
    assert fake_session.commits == 0
    assert [event["event"] for event in published].count("agent_run_failed") >= 1
    assert all(event["event"] != "message_created" for event in published)


@pytest.mark.asyncio
async def test_run_general_agent_intro_question_returns_capability_intro(monkeypatch):
    class FakeRepo(FakeMeetingRepo):
        async def list_recent_messages(self, *, org_id: str, room_id: str, limit: int = 50):
            return [
                SimpleNamespace(id="msg-1", content="@会议Agent 你会干什么？", message_type="user"),
            ]

        async def list_memory_items_for_room(
            self,
            *,
            org_id: str,
            room_id: str,
            include_confirmed: bool = True,
            statuses=None,
            limit: int = 50,
        ):
            return []

    published: list[dict] = []

    async def fake_publish(room_id: str, event: dict):
        published.append(event)

    fake_session = FakeSession()
    fake_repo = FakeRepo()
    monkeypatch.setattr(meeting_service_mod.meeting_stream_broker, "publish", fake_publish)

    service = meeting_service_mod.MeetingService(fake_session, "org-1", "user-1")
    service._repo = fake_repo
    service._users = FakeUsersRepo()

    result = await service.run_general_agent(
        "room-1",
        MeetingAgentRunRequest(query="@会议Agent 你会干什么？", mode="auto"),
    )

    assert result.selected_subgraph == "capability_intro"
    assert "我是会议Agent" in result.answer
    assert result.candidate_memories == []
    assert fake_session.commits == 1
    assert fake_repo.created_messages[-1]["metadata_json"]["selected_subgraph"] == "capability_intro"
    assert published[-1]["event"] == "message_created"


@pytest.mark.asyncio
async def test_extract_memories_preserves_full_candidate_detail_and_source_message():
    class FakeRepo(FakeMeetingRepo):
        def __init__(self):
            super().__init__()
            self.created_memory_items = []
            self.scope_bindings = []
            self.transfer_logs = []

        async def list_recent_messages(self, *, org_id: str, room_id: str, limit: int = 50):
            return [
                SimpleNamespace(
                    id="msg-summary-1",
                    content="会议结论：当前会议室负责候选记忆审核。\n1. 参与角色包括用户、专家、会议Agent。\n2. 需要主持人确认后再发布。",
                    message_type="summary",
                )
            ]

        async def list_memory_items_for_room(
            self,
            *,
            org_id: str,
            room_id: str,
            include_confirmed: bool = True,
            statuses=None,
            limit: int = 50,
        ):
            return []

        async def create_memory_item(self, item):
            self.created_memory_items.append(item)
            return item

        async def create_memory_scope_binding(self, **kwargs):
            self.scope_bindings.append(kwargs)
            return SimpleNamespace(**kwargs)

        async def create_memory_transfer_log(self, **kwargs):
            self.transfer_logs.append(kwargs)
            return SimpleNamespace(**kwargs)

    fake_repo = FakeRepo()
    service = meeting_service_mod.MeetingService(FakeSession(), "org-1", "user-1")
    service._repo = fake_repo
    service._users = FakeUsersRepo()

    result = await service.extract_memories("room-1", MeetingMemoryExtractRequest(max_items=1))

    assert len(result) == 1
    assert result[0].source_message_id == "msg-summary-1"
    assert "\n1." in result[0].content
    assert "\n" not in result[0].summary
    assert fake_repo.created_memory_items[0].content_json["content"] == result[0].content
    assert fake_repo.created_memory_items[0].content_json["source_message_id"] == "msg-summary-1"


def test_candidate_detail_text_filters_rejection_noise():
    text = """一条候选记忆已被拒绝，理由：测试

会议结论：建议继续发布

拒绝理由：重复内容"""

    cleaned = meeting_service_mod.MeetingService._candidate_detail_text(text)

    assert "已被拒绝" not in cleaned
    assert "拒绝理由" not in cleaned
    assert "建议继续发布" in cleaned


@pytest.mark.asyncio
async def test_run_general_agent_auto_routes_to_agent_manager(monkeypatch):
    captured_payloads: list[dict] = []

    class FakeRepo(FakeMeetingRepo):
        async def list_recent_messages(self, *, org_id: str, room_id: str, limit: int = 50):
            return [
                SimpleNamespace(id="msg-1", seq_no=1, username="alice", content="我们刚才提到了最近的质检任务。", message_type="user"),
                SimpleNamespace(id="msg-2", seq_no=2, username="bob", content="关注未完成任务。", message_type="user"),
            ]

    class FakeAgentManagerService:
        async def run_chat(self, payload: dict, db_session=None):
            captured_payloads.append(payload)
            return AgentRouterOutput(
                route_decision=AgentRouteDecision(
                    selected_agent="inspection_task",
                    sub_route="quality_task_status",
                    intent="quality_task_status",
                    confidence=0.9,
                    reason="quality_task_status",
                    route_source="manager",
                ),
                agent_output={
                    "answer": "最近质检任务只读查询完成。",
                    "summary": "质检任务状态查询完成",
                    "message_type": "task_status",
                    "capabilities_used": ["quality.task.status", "chat.response.compose"],
                    "trace_id": "trace-1",
                },
                status="completed",
            )

    published: list[dict] = []

    async def fake_publish(room_id: str, event: dict):
        published.append(event)

    fake_session = FakeSession()
    fake_repo = FakeRepo()
    monkeypatch.setattr(meeting_service_mod, "AgentManagerService", FakeAgentManagerService)
    monkeypatch.setattr(meeting_service_mod.meeting_stream_broker, "publish", fake_publish)

    service = meeting_service_mod.MeetingService(fake_session, "org-1", "user-1")
    service._repo = fake_repo
    service._users = FakeUsersRepo()

    async def fake_build_inspection_context():
        return {"stats": {"total": 2}}

    service._build_meeting_inspection_context = fake_build_inspection_context

    result = await service.run_general_agent(
        "room-1",
        MeetingAgentRunRequest(query="@会议Agent 最近的质检任务情况是怎样的", mode="auto"),
    )

    assert result.selected_subgraph == "quality_task_status"
    assert "只读查询完成" in result.answer
    assert result.memory_sources == []
    assert result.candidate_memories == []
    assert captured_payloads[0]["query"] == "最近的质检任务情况是怎样的"
    assert captured_payloads[0]["ext"]["surface"] == "chat"
    assert captured_payloads[0]["ext"]["forbidden_modes"] == ["action"]
    assert captured_payloads[0]["ext"]["inspection_context"]["stats"]["total"] == 2
    assert fake_session.commits == 1
    metadata = fake_repo.created_messages[-1]["metadata_json"]
    assert metadata["selected_subgraph"] == "quality_task_status"
    assert metadata["route_source"] == "agent_manager"
    assert metadata["selected_agent"] == "inspection_task"
    assert metadata["capabilities_used"] == ["quality.task.status", "chat.response.compose"]
    assert published[-1]["event"] == "message_created"


@pytest.mark.asyncio
async def test_run_general_agent_passes_attachments_to_agent_manager(monkeypatch):
    captured_payloads: list[dict] = []

    class FakeRepo(FakeMeetingRepo):
        async def list_recent_messages(self, *, org_id: str, room_id: str, limit: int = 50):
            return [
                SimpleNamespace(id="msg-1", seq_no=1, username="alice", content="please inspect this image", message_type="user"),
            ]

    class FakeAgentManagerService:
        async def run_chat(self, payload: dict, db_session=None):
            captured_payloads.append(payload)
            return AgentRouterOutput(
                route_decision=AgentRouteDecision(
                    selected_agent="inspection_task",
                    sub_route="image_understanding",
                    intent="image_understanding",
                    confidence=0.9,
                    reason="image attachment",
                    route_source="manager",
                ),
                agent_output={
                    "answer": "image checked",
                    "message_type": "image_understanding",
                    "capabilities_used": ["quality.image.inspect"],
                },
                status="completed",
            )

    published: list[dict] = []

    async def fake_publish(room_id: str, event: dict):
        published.append(event)

    attachment = {
        "id": "att-1",
        "name": "screenshot.png",
        "url": "/api/v1/files/chat-attachments/screenshot.png",
        "content_type": "image/png",
        "size_bytes": 1234,
        "kind": "image",
        "bucket": "chat-attachments",
        "object_key": "screenshot.png",
    }
    fake_session = FakeSession()
    fake_repo = FakeRepo()
    monkeypatch.setattr(meeting_service_mod, "AgentManagerService", FakeAgentManagerService)
    monkeypatch.setattr(meeting_service_mod.meeting_stream_broker, "publish", fake_publish)

    service = meeting_service_mod.MeetingService(fake_session, "org-1", "user-1")
    service._repo = fake_repo
    service._users = FakeUsersRepo()

    async def fake_build_inspection_context():
        return {"stats": {"total": 1}}

    service._build_meeting_inspection_context = fake_build_inspection_context

    result = await service.run_general_agent(
        "room-1",
        MeetingAgentRunRequest(query="inspect attached screenshot", mode="auto", attachments=[attachment]),
    )

    assert result.selected_subgraph == "image_understanding"
    assert captured_payloads[0]["attachments"][0]["bucket"] == "chat-attachments"
    assert captured_payloads[0]["attachments"][0]["object_key"] == "screenshot.png"
    assert captured_payloads[0]["image_urls"] == ["/api/v1/files/chat-attachments/screenshot.png"]
    metadata = fake_repo.created_messages[-1]["metadata_json"]
    assert metadata["attachment_echo"][0]["bucket"] == "chat-attachments"
    assert metadata["attachment_echo"][0]["object_key"] == "screenshot.png"
    assert published[0]["attachments"][0]["object_key"] == "screenshot.png"
    assert published[-1]["event"] == "message_created"


@pytest.mark.asyncio
async def test_confirm_memory_publishes_meeting_scope_binding():
    memory = SimpleNamespace(
        memory_id="mem_meeting_1",
        content_summary="P001 下月提高抽检比例",
        content_json={
            "title": "P001 抽检策略",
            "content": "P001 下月提高抽检比例",
            "memory_type": "decision",
            "source_id": "room-1",
        },
        scope_json={"meeting_room_id": "room-1"},
        confidence=0.65,
        status="candidate",
        memory_type="task_episode",
        created_by="user-1",
        created_at=None,
        updated_at=None,
    )

    class FakeRepo(FakeMeetingRepo):
        def __init__(self):
            super().__init__()
            self.scope_bindings = []
            self.transfer_logs = []

        async def get_memory_item(self, org_id: str, memory_id: str):
            return memory if memory_id == memory.memory_id else None

        async def update_memory_item(
            self,
            *,
            org_id: str,
            memory_id: str,
            status=None,
            content_summary=None,
            content_json=None,
            scope_json=None,
        ):
            if status is not None:
                memory.status = status
            if content_summary is not None:
                memory.content_summary = content_summary
            if content_json is not None:
                memory.content_json = content_json
            if scope_json is not None:
                memory.scope_json = scope_json
            return memory

        async def create_memory_scope_binding(self, **kwargs):
            self.scope_bindings.append(kwargs)
            return SimpleNamespace(**kwargs)

        async def create_memory_transfer_log(self, **kwargs):
            self.transfer_logs.append(kwargs)
            return SimpleNamespace(**kwargs)

    fake_repo = FakeRepo()
    service = meeting_service_mod.MeetingService(FakeSession(), "org-1", "user-1")
    service._repo = fake_repo
    service._users = FakeUsersRepo()

    result = await service.confirm_memory(
        "mem_meeting_1",
        MeetingMemoryUpdateRequest(title="P001 抽检策略", content="P001 下月提高抽检比例", scope="meeting"),
    )

    assert result.status == "active"
    assert result.scope == "meeting"
    assert result.confirmed_by == "user-1"
    assert memory.scope_json["scope_type"] == "meeting_room"
    assert memory.scope_json["scope_id"] == "room-1"
    assert memory.scope_json["room_id"] == "room-1"
    assert fake_repo.scope_bindings[-1]["scope_type"] == "meeting_room"
    assert fake_repo.scope_bindings[-1]["scope_id"] == "room-1"
    assert fake_repo.transfer_logs[-1]["status"] == "confirmed"
    assert fake_repo.transfer_logs[-1]["to_scope_type"] == "meeting_room"
    assert fake_repo.created_messages[-1]["message_type"] == "system"


@pytest.mark.asyncio
async def test_extract_memories_marks_business_memory_with_scope_metadata():
    class FakeRepo(FakeMeetingRepo):
        def __init__(self):
            super().__init__()
            self.created_memory_items = []
            self.scope_bindings = []
            self.transfer_logs = []

        async def get_room(self, org_id: str, room_id: str):
            return SimpleNamespace(
                id=room_id,
                org_id=org_id,
                created_by="user-1",
                memory_policy={
                    "business_context": {
                        "task_ids": ["task-1"],
                        "product_ids": ["P001"],
                        "batch_nos": ["B001"],
                        "standard_ids": ["STD-1"],
                        "tasks": [],
                    }
                },
            )

        async def list_recent_messages(self, *, org_id: str, room_id: str, limit: int = 50):
            return [
                SimpleNamespace(
                    id="msg-business-1",
                    content="质检任务 task-1 需要复核，P001 产品抽检风险上升",
                    message_type="user",
                )
            ]

        async def list_memory_items_for_room(
            self,
            *,
            org_id: str,
            room_id: str,
            include_confirmed: bool = True,
            statuses=None,
            limit: int = 50,
        ):
            return []

        async def create_memory_item(self, item):
            self.created_memory_items.append(item)
            return item

        async def create_memory_scope_binding(self, **kwargs):
            self.scope_bindings.append(kwargs)
            return SimpleNamespace(**kwargs)

        async def create_memory_transfer_log(self, **kwargs):
            self.transfer_logs.append(kwargs)
            return SimpleNamespace(**kwargs)

    fake_repo = FakeRepo()
    service = meeting_service_mod.MeetingService(FakeSession(), "org-1", "user-1")
    service._repo = fake_repo
    service._users = FakeUsersRepo()

    result = await service.extract_memories("room-1", MeetingMemoryExtractRequest(max_items=1))

    assert result[0].memory_category == "business_memory"
    assert result[0].recommended_scope == "inspection_task"
    assert result[0].recommended_scope_id == "task-1"
    assert result[0].shareability["cross_room_allowed"] is True
    assert "product" in result[0].shareability["allowed_scopes"]
    assert result[0].source_refs == [
        {"type": "meeting_room", "id": "room-1"},
        {"type": "meeting_message", "id": "msg-business-1"},
    ]
    assert fake_repo.created_memory_items[0].content_json["memory_category"] == "business_memory"


@pytest.mark.asyncio
async def test_quality_fact_without_business_binding_is_business_but_meeting_only():
    class FakeRepo(FakeMeetingRepo):
        def __init__(self):
            super().__init__()
            self.created_memory_items = []
            self.scope_bindings = []
            self.transfer_logs = []

        async def get_room(self, org_id: str, room_id: str):
            return SimpleNamespace(
                id=room_id,
                org_id=org_id,
                created_by="user-1",
                memory_policy={"business_context": {"task_ids": [], "product_ids": [], "batch_nos": [], "standard_ids": [], "tasks": []}},
            )

        async def list_recent_messages(self, *, org_id: str, room_id: str, limit: int = 50):
            return [
                SimpleNamespace(
                    id="msg-quality-fact",
                    content="最近一次质检是在 2026 年 6 月 3 日进行的，检测结果为不合格 fail，整体评分为 1.0 分，检测耗时约 19.2 秒，使用模型 doubao-seed-2-0-lite-260215。",
                    message_type="user",
                )
            ]

        async def list_memory_items_for_room(self, **kwargs):
            return []

        async def create_memory_item(self, item):
            self.created_memory_items.append(item)
            return item

        async def create_memory_scope_binding(self, **kwargs):
            self.scope_bindings.append(kwargs)
            return SimpleNamespace(**kwargs)

        async def create_memory_transfer_log(self, **kwargs):
            self.transfer_logs.append(kwargs)
            return SimpleNamespace(**kwargs)

    fake_repo = FakeRepo()
    service = meeting_service_mod.MeetingService(FakeSession(), "org-1", "user-1")
    service._repo = fake_repo
    service._users = FakeUsersRepo()

    result = await service.extract_memories("room-1", MeetingMemoryExtractRequest(max_items=1))

    candidate = result[0]
    assert candidate.memory_type == "quality_fact"
    assert candidate.memory_category == "business_memory"
    assert candidate.recommended_scope == "meeting"
    assert candidate.shareability["allowed_scopes"] == ["meeting"]
    assert "inspection_task" in candidate.shareability["missing_bindings"]
    assert any("单次质检事实默认发布到质检任务" in warning for warning in candidate.warnings)


def test_meeting_memory_scope_validation_accepts_only_stable_publish_targets():
    with pytest.raises(PydanticValidationError):
        MeetingMemoryUpdateRequest(scope="department")

    with pytest.raises(PydanticValidationError):
        MeetingMemoryUpdateRequest(scope="rag_space", scope_id="rag-001")

    request = MeetingMemoryUpdateRequest(scope="workspace", scope_id="quality_risk_library")
    assert request.scope == "workspace"
    assert request.scope_id == "quality_risk_library"


def _meeting_memory(
    *,
    memory_id: str = "mem_meeting_1",
    status: str = "candidate",
    category: str = "meeting_memory",
    room_id: str = "room-1",
    content: str = "P001 下月提高抽检比例",
):
    return SimpleNamespace(
        memory_id=memory_id,
        content_summary=content,
        content_json={
            "title": "P001 抽检策略",
            "content": content,
            "memory_type": "decision",
            "memory_category": category,
            "source_id": room_id,
            "source_refs": [{"type": "meeting_room", "id": room_id}],
        },
        scope_json={"meeting_room_id": room_id},
        confidence=0.65,
        status=status,
        memory_type="task_episode",
        created_by="user-1",
        created_at=None,
        updated_at=None,
        version_parent_id=None,
    )


class FakeTaskRepository:
    def __init__(self, session):
        self.session = session

    async def get_for_user(self, org_id: str, task_id: str, owner_user_id: str | None = None):
        if task_id == "task-1":
            return SimpleNamespace(id="task-1", product_id="P001", spec_code="STD-1", status="done")
        return None


class FakeAlertRepository:
    created_alerts: list[dict] = []

    def __init__(self, session):
        self.session = session

    async def create_once(self, payload: dict):
        self.created_alerts.append(payload)
        return SimpleNamespace(**payload)


@pytest.mark.asyncio
async def test_non_business_memory_cannot_publish_to_product_scope():
    memory = _meeting_memory(category="meeting_memory", content="会议决定下周三继续同步协作安排")
    memory.content_json["title"] = "会议同步安排"

    class FakeRepo(FakeMeetingRepo):
        async def get_room(self, org_id: str, room_id: str):
            return SimpleNamespace(
                id=room_id,
                org_id=org_id,
                created_by="user-1",
                memory_policy={
                    "business_context": {
                        "task_ids": [],
                        "product_ids": ["P001"],
                        "batch_nos": [],
                        "standard_ids": [],
                        "tasks": [],
                    }
                },
            )

        async def get_memory_item(self, org_id: str, memory_id: str):
            return memory

    service = meeting_service_mod.MeetingService(FakeSession(), "org-1", "user-1")
    service._repo = FakeRepo()
    service._users = FakeUsersRepo()

    with pytest.raises(ValidationError, match="only business_memory"):
        await service.confirm_memory(
            memory.memory_id,
            MeetingMemoryUpdateRequest(scope="product", scope_id="P001"),
        )


@pytest.mark.asyncio
async def test_rejected_noise_memory_cannot_be_overridden_and_confirmed():
    memory = _meeting_memory(category="rejected_noise", content="哈哈 收到")

    class FakeRepo(FakeMeetingRepo):
        async def get_memory_item(self, org_id: str, memory_id: str):
            return memory

    service = meeting_service_mod.MeetingService(FakeSession(), "org-1", "user-1")
    service._repo = FakeRepo()
    service._users = FakeUsersRepo()

    with pytest.raises(ValidationError, match="rejected_noise"):
        await service.confirm_memory(
            memory.memory_id,
            MeetingMemoryUpdateRequest(scope="meeting", is_business_memory=False),
        )


@pytest.mark.asyncio
async def test_confirm_memory_reclassifies_quality_fact_from_edited_content():
    memory = _meeting_memory(
        category="meeting_memory",
        content="会议形成待确认结论：最近一次质检情况怎么样",
    )

    class FakeRepo(FakeMeetingRepo):
        def __init__(self):
            super().__init__()
            self.scope_bindings = []
            self.transfer_logs = []

        async def get_room(self, org_id: str, room_id: str):
            return SimpleNamespace(
                id=room_id,
                org_id=org_id,
                created_by="user-1",
                memory_policy={"business_context": {"task_ids": [], "product_ids": [], "batch_nos": [], "standard_ids": [], "tasks": []}},
            )

        async def get_memory_item(self, org_id: str, memory_id: str):
            return memory

        async def update_memory_item(
            self,
            *,
            org_id: str,
            memory_id: str,
            status=None,
            content_summary=None,
            content_json=None,
            scope_json=None,
        ):
            if status is not None:
                memory.status = status
            if content_summary is not None:
                memory.content_summary = content_summary
            if content_json is not None:
                memory.content_json = content_json
            if scope_json is not None:
                memory.scope_json = scope_json
            return memory

        async def create_memory_scope_binding(self, **kwargs):
            self.scope_bindings.append(kwargs)
            return SimpleNamespace(**kwargs)

        async def create_memory_transfer_log(self, **kwargs):
            self.transfer_logs.append(kwargs)
            return SimpleNamespace(**kwargs)

    fake_repo = FakeRepo()
    service = meeting_service_mod.MeetingService(FakeSession(), "org-1", "user-1")
    service._repo = fake_repo
    service._users = FakeUsersRepo()

    result = await service.confirm_memory(
        memory.memory_id,
        MeetingMemoryUpdateRequest(
            title="最近一次质检事实",
            content="最近一次质检是在 2026 年 6 月 3 日进行的，检测结果为不合格 fail，整体评分为 1.0 分，检测耗时约 19.2 秒。",
            scope="meeting",
        ),
    )

    assert result.memory_type == "quality_fact"
    assert result.memory_category == "business_memory"
    assert result.shareability["allowed_scopes"] == ["meeting"]
    assert "inspection_task" in result.shareability["missing_bindings"]


@pytest.mark.asyncio
async def test_business_memory_product_publish_requires_bound_context():
    memory = _meeting_memory(category="business_memory")

    class FakeRepo(FakeMeetingRepo):
        def __init__(self):
            super().__init__()
            self.scope_bindings = []
            self.transfer_logs = []

        async def get_room(self, org_id: str, room_id: str):
            return SimpleNamespace(
                id=room_id,
                org_id=org_id,
                created_by="user-1",
                memory_policy={
                    "business_context": {
                        "task_ids": [],
                        "product_ids": ["P001"],
                        "batch_nos": [],
                        "standard_ids": [],
                        "tasks": [],
                    }
                },
            )

        async def get_memory_item(self, org_id: str, memory_id: str):
            return memory

        async def update_memory_item(
            self,
            *,
            org_id: str,
            memory_id: str,
            status=None,
            content_summary=None,
            content_json=None,
            scope_json=None,
        ):
            if status is not None:
                memory.status = status
            if content_summary is not None:
                memory.content_summary = content_summary
            if content_json is not None:
                memory.content_json = content_json
            if scope_json is not None:
                memory.scope_json = scope_json
            return memory

        async def create_memory_scope_binding(self, **kwargs):
            self.scope_bindings.append(kwargs)
            return SimpleNamespace(**kwargs)

        async def create_memory_transfer_log(self, **kwargs):
            self.transfer_logs.append(kwargs)
            return SimpleNamespace(**kwargs)

    fake_repo = FakeRepo()
    service = meeting_service_mod.MeetingService(FakeSession(), "org-1", "user-1")
    service._repo = fake_repo
    service._users = FakeUsersRepo()

    with pytest.raises(ValidationError, match="product scope must be bound"):
        await service.confirm_memory(
            memory.memory_id,
            MeetingMemoryUpdateRequest(scope="product", scope_id="P999", is_business_memory=True),
        )

    result = await service.confirm_memory(
        memory.memory_id,
        MeetingMemoryUpdateRequest(scope="product", scope_id="P001", is_business_memory=True),
    )

    assert result.status == "active"
    assert result.scope == "product"
    assert result.scope_type == "product"
    assert result.scope_id == "P001"
    assert fake_repo.scope_bindings[-1]["scope_type"] == "product"
    assert fake_repo.transfer_logs[-1]["to_scope_type"] == "product"


@pytest.mark.asyncio
async def test_risk_forecast_generates_risk_insight_candidate():
    class FakeRepo(FakeMeetingRepo):
        def __init__(self):
            super().__init__()
            self.created_memory_items = []
            self.scope_bindings = []
            self.transfer_logs = []

        async def get_room(self, org_id: str, room_id: str):
            return SimpleNamespace(
                id=room_id,
                org_id=org_id,
                created_by="user-1",
                memory_policy={
                    "business_context": {
                        "task_ids": ["task-1"],
                        "product_ids": ["P001"],
                        "batch_nos": ["B001"],
                        "standard_ids": ["STD-1"],
                        "tasks": [],
                    }
                },
            )

        async def list_recent_messages(self, *, org_id: str, room_id: str, limit: int = 50):
            return [
                SimpleNamespace(id="msg-1", content="P001 的 B001 批次最近多次质检不合格，需要预测后续风险", message_type="user"),
                SimpleNamespace(id="msg-2", content="建议未来两周重点看复测稳定性和失败率", message_type="user"),
            ]

        async def list_memory_items_for_room(self, **kwargs):
            return []

        async def create_memory_item(self, item):
            self.created_memory_items.append(item)
            return item

        async def create_memory_scope_binding(self, **kwargs):
            self.scope_bindings.append(kwargs)
            return SimpleNamespace(**kwargs)

        async def create_memory_transfer_log(self, **kwargs):
            self.transfer_logs.append(kwargs)
            return SimpleNamespace(**kwargs)

    fake_repo = FakeRepo()
    service = meeting_service_mod.MeetingService(FakeSession(), "org-1", "user-1")
    service._repo = fake_repo
    service._users = FakeUsersRepo()

    result = await service.run_general_agent(
        "room-1",
        MeetingAgentRunRequest(query="请预测后续质检风险", mode="risk_forecast"),
    )

    candidate = result.candidate_memories[0]
    assert candidate.memory_type == "risk_insight"
    assert candidate.memory_category == "business_memory"
    assert candidate.recommended_scope == "batch"
    assert candidate.recommended_scope_id == "B001"
    assert candidate.risk_level == "medium"
    assert candidate.forecast_window["days_min"] == 7
    assert "workspace" in candidate.shareability["allowed_scopes"]
    assert fake_repo.created_memory_items[0].content_json["affected_objects"]["batch_nos"] == ["B001"]


@pytest.mark.asyncio
async def test_risk_insight_without_business_binding_stays_in_meeting():
    class FakeRepo(FakeMeetingRepo):
        def __init__(self):
            super().__init__()
            self.created_memory_items = []
            self.scope_bindings = []
            self.transfer_logs = []

        async def list_recent_messages(self, *, org_id: str, room_id: str, limit: int = 50):
            return [
                SimpleNamespace(id="msg-1", content="大家觉得最近可能有风险，但还没有绑定产品或批次", message_type="user"),
            ]

        async def list_memory_items_for_room(self, **kwargs):
            return []

        async def create_memory_item(self, item):
            self.created_memory_items.append(item)
            return item

        async def create_memory_scope_binding(self, **kwargs):
            self.scope_bindings.append(kwargs)
            return SimpleNamespace(**kwargs)

        async def create_memory_transfer_log(self, **kwargs):
            self.transfer_logs.append(kwargs)
            return SimpleNamespace(**kwargs)

    fake_repo = FakeRepo()
    service = meeting_service_mod.MeetingService(FakeSession(), "org-1", "user-1")
    service._repo = fake_repo
    service._users = FakeUsersRepo()

    result = await service.run_general_agent(
        "room-1",
        MeetingAgentRunRequest(query="预测风险", mode="risk_forecast"),
    )

    candidate = result.candidate_memories[0]
    assert candidate.memory_type == "risk_insight"
    assert candidate.memory_category == "meeting_memory"
    assert candidate.recommended_scope == "meeting"
    assert candidate.shareability["allowed_scopes"] == ["meeting"]


@pytest.mark.asyncio
async def test_confirm_risk_insight_to_risk_library_creates_risk_forecast_alert(monkeypatch):
    FakeAlertRepository.created_alerts = []
    monkeypatch.setattr(meeting_service_mod, "AlertRepository", FakeAlertRepository)

    memory = _meeting_memory(category="business_memory", content="B001 批次连续出现复测不稳定，未来 7-14 天需要重点关注")
    memory.content_json.update(
        {
            "memory_type": "risk_insight",
            "affected_objects": {
                "inspection_task_ids": ["task-1"],
                "product_ids": ["P001"],
                "batch_nos": ["B001"],
                "standard_ids": ["STD-1"],
            },
            "forecast_window": {"label": "未来 7-14 天", "days_min": 7, "days_max": 14},
            "risk_level": "high",
            "recommended_actions": ["复核相关质检任务", "跟踪复测结论"],
            "evidence_refs": [{"type": "meeting_message", "id": "msg-1"}],
        }
    )

    class FakeRepo(FakeMeetingRepo):
        def __init__(self):
            super().__init__()
            self.scope_bindings = []
            self.transfer_logs = []

        async def get_room(self, org_id: str, room_id: str):
            return SimpleNamespace(
                id=room_id,
                org_id=org_id,
                created_by="user-1",
                memory_policy={
                    "business_context": {
                        "task_ids": ["task-1"],
                        "product_ids": ["P001"],
                        "batch_nos": ["B001"],
                        "standard_ids": ["STD-1"],
                        "tasks": [],
                    }
                },
            )

        async def get_memory_item(self, org_id: str, memory_id: str):
            return memory

        async def update_memory_item(
            self,
            *,
            org_id: str,
            memory_id: str,
            status=None,
            content_summary=None,
            content_json=None,
            scope_json=None,
        ):
            if status is not None:
                memory.status = status
            if content_summary is not None:
                memory.content_summary = content_summary
            if content_json is not None:
                memory.content_json = content_json
            if scope_json is not None:
                memory.scope_json = scope_json
            return memory

        async def create_memory_scope_binding(self, **kwargs):
            self.scope_bindings.append(kwargs)
            return SimpleNamespace(**kwargs)

        async def create_memory_transfer_log(self, **kwargs):
            self.transfer_logs.append(kwargs)
            return SimpleNamespace(**kwargs)

    fake_repo = FakeRepo()
    service = meeting_service_mod.MeetingService(FakeSession(), "org-1", "user-1")
    service._repo = fake_repo
    service._users = FakeUsersRepo()

    result = await service.confirm_memory(
        memory.memory_id,
        MeetingMemoryUpdateRequest(scope="workspace", scope_id="quality_risk_library", is_business_memory=True),
    )

    assert result.scope == "workspace"
    assert result.scope_type == "workspace"
    assert result.scope_id == "quality_risk_library"
    assert fake_repo.scope_bindings[-1]["scope_type"] == "workspace"
    assert FakeAlertRepository.created_alerts[-1]["alert_type"] == "risk_forecast"
    assert FakeAlertRepository.created_alerts[-1]["severity"] == "error"
    assert FakeAlertRepository.created_alerts[-1]["detail"]["target_scope_id"] == "quality_risk_library"


@pytest.mark.asyncio
async def test_quality_risk_library_requires_bound_business_object():
    memory = _meeting_memory(category="business_memory", content="当前会议存在风险线索")
    memory.content_json.update({"memory_type": "risk_insight"})

    class FakeRepo(FakeMeetingRepo):
        async def get_memory_item(self, org_id: str, memory_id: str):
            return memory

    service = meeting_service_mod.MeetingService(FakeSession(), "org-1", "user-1")
    service._repo = FakeRepo()
    service._users = FakeUsersRepo()

    with pytest.raises(ValidationError, match="quality risk library publishing requires"):
        await service.confirm_memory(
            memory.memory_id,
            MeetingMemoryUpdateRequest(scope="workspace", scope_id="quality_risk_library", is_business_memory=True),
        )


def test_organization_memory_publish_scope_is_rejected_by_schema():
    with pytest.raises(PydanticValidationError):
        MeetingMemoryUpdateRequest(scope="organization", scope_id="org-1", is_business_memory=True)


@pytest.mark.asyncio
async def test_confirmed_memory_edit_creates_new_version(monkeypatch):
    memory = _meeting_memory(status="active", category="meeting_memory")
    memory.content_json.update(
        {
            "confirmed_at": "2026-01-01T00:00:00",
            "confirmed_by": "user-1",
            "published_scope": "meeting",
            "target_scope_type": "meeting_room",
            "target_scope_id": "room-1",
        }
    )

    class FakeRepo(FakeMeetingRepo):
        def __init__(self):
            super().__init__()
            self.created_memory_items = []
            self.scope_bindings = []
            self.transfer_logs = []

        async def get_memory_item(self, org_id: str, memory_id: str):
            return memory

        async def create_memory_item(self, item):
            self.created_memory_items.append(item)
            return item

        async def update_memory_item(self, *, org_id: str, memory_id: str, status=None, content_json=None, **kwargs):
            if status is not None:
                memory.status = status
            if content_json is not None:
                memory.content_json = content_json
            return memory

        async def create_memory_scope_binding(self, **kwargs):
            self.scope_bindings.append(kwargs)
            return SimpleNamespace(**kwargs)

        async def create_memory_transfer_log(self, **kwargs):
            self.transfer_logs.append(kwargs)
            return SimpleNamespace(**kwargs)

    fake_repo = FakeRepo()
    service = meeting_service_mod.MeetingService(FakeSession(), "org-1", "user-1")
    service._repo = fake_repo
    service._users = FakeUsersRepo()

    result = await service.confirm_memory(
        memory.memory_id,
        MeetingMemoryUpdateRequest(scope="meeting", content="P001 下月提高抽检比例，新增复核说明"),
    )

    assert memory.status == "superseded"
    assert memory.content_json["superseded_by"] == result.memory_id
    assert result.version_parent_id == "mem_meeting_1"
    assert fake_repo.created_memory_items[-1].version_parent_id == "mem_meeting_1"
    assert fake_repo.transfer_logs[-1]["memory_id"] == result.memory_id


def test_agent_audit_memory_reads_are_serialized():
    row = SimpleNamespace(
        id="audit-1",
        room_id="room-1",
        user_id="user-1",
        agent_id="general_agent",
        question="总结一下",
        intent="meeting_summary",
        requested_domains=["meeting", "memory"],
        allowed_domains=["meeting", "memory"],
        denied_domains=[],
        tool_calls=[],
        source_refs=[
            {"type": "meeting_message", "id": "msg-1"},
            {"type": "memory", "id": "mem-1", "scope": "product"},
        ],
        redacted_fields=[],
        decision="allowed",
        created_at=None,
    )
    service = meeting_service_mod.MeetingService(FakeSession(), "org-1", "user-1")

    result = service._serialize_agent_query_audit(row)

    assert result.memory_reads == [{"type": "memory", "id": "mem-1", "scope": "product"}]


@pytest.mark.asyncio
async def test_transfer_memory_requires_host_permission():
    memory = _meeting_memory(status="active", category="business_memory")

    class FakeRepo(FakeMeetingRepo):
        async def get_room(self, org_id: str, room_id: str):
            return SimpleNamespace(id=room_id, org_id=org_id, created_by="user-1")

        async def get_member(self, org_id: str, room_id: str, user_id: str):
            return SimpleNamespace(id="member-2", org_id=org_id, room_id=room_id, user_id=user_id, role="member")

        async def get_memory_item(self, org_id: str, memory_id: str):
            return memory

    service = meeting_service_mod.MeetingService(FakeSession(), "org-1", "user-2")
    service._repo = FakeRepo()
    service._users = FakeUsersRepo()

    with pytest.raises(ForbiddenError):
        await service.transfer_memory(
            memory.memory_id,
            meeting_service_mod.MeetingMemoryTransferRequest(to_scope_type="meeting_room", to_scope_id="room-1"),
        )


@pytest.mark.asyncio
async def test_meeting_memory_review_requires_host():
    memory = SimpleNamespace(
        memory_id="mem_meeting_1",
        content_summary="P001 下月提高抽检比例",
        content_json={
            "title": "P001 抽检策略",
            "content": "P001 下月提高抽检比例",
            "memory_type": "decision",
            "source_id": "room-1",
        },
        scope_json={"meeting_room_id": "room-1"},
        confidence=0.65,
        status="candidate",
        memory_type="task_episode",
        created_by="user-1",
        created_at=None,
        updated_at=None,
    )

    class FakeRepo(FakeMeetingRepo):
        async def get_room(self, org_id: str, room_id: str):
            return SimpleNamespace(id=room_id, org_id=org_id, created_by="user-1")

        async def get_member(self, org_id: str, room_id: str, user_id: str):
            return SimpleNamespace(id="member-2", org_id=org_id, room_id=room_id, user_id=user_id, role="member")

        async def get_memory_item(self, org_id: str, memory_id: str):
            return memory if memory_id == memory.memory_id else None

    service = meeting_service_mod.MeetingService(FakeSession(), "org-1", "user-2")
    service._repo = FakeRepo()
    service._users = FakeUsersRepo()

    with pytest.raises(ForbiddenError):
        await service.extract_memories("room-1", MeetingMemoryExtractRequest())
    with pytest.raises(ForbiddenError):
        await service.confirm_memory("mem_meeting_1", MeetingMemoryUpdateRequest(scope="meeting"))
    with pytest.raises(ForbiddenError):
        await service.reject_memory("mem_meeting_1")


@pytest.mark.asyncio
async def test_action_item_create_and_complete_flow():
    class FakeRepo(FakeMeetingRepo):
        def __init__(self):
            super().__init__()
            self.action_items = {}

        async def create_action_item(self, **kwargs):
            row = SimpleNamespace(
                id="action-1",
                room_id=kwargs["room_id"],
                title=kwargs["title"],
                description=kwargs["description"],
                owner_id=kwargs["owner_id"],
                due_at=kwargs["due_at"],
                status="open",
                source_message_id=kwargs["source_message_id"],
                created_by=kwargs["created_by"],
                created_at=None,
                updated_at=None,
            )
            self.action_items[row.id] = row
            return row

        async def get_action_item(self, org_id: str, action_item_id: str):
            return self.action_items.get(action_item_id)

        async def update_action_item(self, org_id: str, action_item_id: str, **fields):
            row = self.action_items[action_item_id]
            for key, value in fields.items():
                if value is not None:
                    setattr(row, key, value)
            return row

    fake_repo = FakeRepo()
    fake_users = FakeUsersRepo()
    fake_users.users[("org-1", "user-2")] = FakeUser("bob")

    service = meeting_service_mod.MeetingService(FakeSession(), "org-1", "user-1")
    service._repo = fake_repo
    service._users = fake_users

    created = await service.create_action_item(
        "room-1",
        MeetingActionItemCreateRequest(title="复核检测标准", description="确认 P001 判定依据", owner_id="user-2"),
    )
    completed = await service.complete_action_item(created.id)

    assert created.title == "复核检测标准"
    assert created.owner_name == "bob"
    assert completed.status == "done"
    assert fake_repo.created_messages[0]["message_type"] == "system"
    assert fake_repo.created_messages[-1]["content"] == "会议待办已完成：复核检测标准"


@pytest.mark.asyncio
async def test_next_message_seq_locks_room_before_allocating(monkeypatch):
    executed = []

    class FakeResult:
        def scalar_one_or_none(self):
            return None

    class FakeScalarSession:
        async def execute(self, stmt):
            executed.append(stmt)
            return FakeResult()

        async def scalar(self, stmt):
            executed.append(stmt)
            return 8

    repo = MeetingRepository(FakeScalarSession())

    seq_no = await repo.next_message_seq(org_id="org-1", room_id="room-1")

    assert seq_no == 9
    assert len(executed) == 2
    assert getattr(executed[0], "_for_update_arg", None) is not None


@pytest.mark.asyncio
async def test_start_agent_discussion_persists_topic_and_calls_round(monkeypatch):
    fake_repo = FakeMeetingRepo()
    fake_users = FakeUsersRepo()
    fake_session = FakeSession()
    captured_round = {}

    class FakeAgentService:
        async def start_discussion_round(self, **kwargs):
            captured_round.update(kwargs)
            return 2

    monkeypatch.setattr(meeting_service_mod, "MeetingRepository", lambda session: fake_repo)
    monkeypatch.setattr(meeting_service_mod, "MeetingAgentService", FakeAgentService)

    service = meeting_service_mod.MeetingService(fake_session, "org-1", "user-1")
    service._repo = fake_repo
    service._users = fake_users

    result = await service.start_agent_discussion("room-1", "讨论一下这个问题", 3)

    assert result.started is True
    assert result.participant_count == 2
    assert result.topic_message is not None
    assert result.topic_message.content == "讨论一下这个问题"
    assert fake_session.commits == 1
    assert fake_repo.created_messages[0]["content"] == "讨论一下这个问题"
    assert captured_round["room_id"] == "room-1"
    assert captured_round["query"] == "讨论一下这个问题"
    assert captured_round["max_agents"] == 3


@pytest.mark.asyncio
async def test_start_discussion_round_ignores_observers(monkeypatch):
    class FakeAgentDef:
        def __init__(self, name: str, is_active: bool = True):
            self.name = name
            self.is_active = is_active

    class FakeRoomAgent:
        def __init__(self, agent_id: str, role: str):
            self.agent_id = agent_id
            self.role = role

    class FakeRepo:
        def __init__(self):
            self.room_agents = [
                FakeRoomAgent("11111111-1111-1111-1111-111111111111", "participant"),
                FakeRoomAgent("22222222-2222-2222-2222-222222222222", "observer"),
                FakeRoomAgent("33333333-3333-3333-3333-333333333333", "participant"),
                FakeRoomAgent("not-a-uuid", "participant"),
            ]

        async def get_agents(self, org_id: str, room_id: str):
            return self.room_agents

        async def get_visible_agent_definition(self, org_id: str, agent_def_id: str):
            if agent_def_id == "11111111-1111-1111-1111-111111111111":
                return FakeAgentDef("Quality")
            if agent_def_id == "22222222-2222-2222-2222-222222222222":
                return FakeAgentDef("Observer")
            if agent_def_id == "33333333-3333-3333-3333-333333333333":
                return FakeAgentDef("Inactive", is_active=False)
            return None

    class FakeSessionCtx:
        def __init__(self):
            self.session = FakeSession()

        async def __aenter__(self):
            return self.session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    scheduled_tasks = []
    fake_repo = FakeRepo()
    captured = {}
    real_create_task = meeting_agent_mod.asyncio.create_task

    async def fake_run(self, **kwargs):
        captured.update(kwargs)

    def tracking_create_task(coro):
        task = real_create_task(coro)
        scheduled_tasks.append(task)
        return task

    monkeypatch.setattr(meeting_agent_mod, "get_session", lambda: FakeSessionCtx())
    monkeypatch.setattr(meeting_agent_mod, "MeetingRepository", lambda session: fake_repo)
    monkeypatch.setattr(meeting_agent_mod.MeetingAgentService, "_run_discussion_round", fake_run)
    monkeypatch.setattr(meeting_agent_mod.asyncio, "create_task", tracking_create_task)

    service = meeting_agent_mod.MeetingAgentService()
    count = await service.start_discussion_round(
        room_id="room-1",
        org_id="org-1",
        user_id="user-1",
        username="alice",
        query="请讨论一下检测流程",
        max_agents=3,
    )

    assert count == 1
    await asyncio.wait_for(scheduled_tasks[0], timeout=1)
    assert captured["participants"] == [{"agent_id": "11111111-1111-1111-1111-111111111111", "agent_name": "Quality"}]
    assert "请讨论一下检测流程" in captured["query"]


@pytest.mark.asyncio
async def test_autonomous_participation_emits_failure_on_llm_error(monkeypatch):
    class FakeAgentDef:
        def __init__(self, name: str = "AI 助手", is_active: bool = True):
            self.name = name
            self.is_active = is_active
            self.participation_strategy = {
                "auto_reply": True,
                "cooldown_seconds": 0,
                "strategies": {"message_count": {"enabled": True, "every_n_messages": 1}},
            }

    class FakeRoomAgent:
        def __init__(self, agent_id: str, role: str):
            self.agent_id = agent_id
            self.role = role

    class FakeRepo:
        def __init__(self):
            self.created_messages: list[dict] = []
            self.room_agents = [FakeRoomAgent("11111111-1111-1111-1111-111111111111", "participant")]

        async def get_agents(self, org_id: str, room_id: str):
            return self.room_agents

        async def list_messages(self, org_id: str, room_id: str, after_seq: int = 0, limit: int = 30):
            return []

        async def get_visible_agent_definition(self, org_id: str, agent_def_id: str):
            return FakeAgentDef()

        async def create_message(self, **kwargs):
            self.created_messages.append(kwargs)
            return SimpleNamespace(
                id=kwargs.get("message_id", "msg-1"),
                room_id=kwargs["room_id"],
                user_id=kwargs["user_id"],
                username=kwargs["username"],
                seq_no=len(self.created_messages),
                content=kwargs["content"],
                message_type=kwargs.get("message_type", "agent"),
                agent_id=kwargs.get("agent_id"),
                mentions=kwargs.get("mentions"),
                created_at=None,
                updated_at=None,
            )

    class FakeSessionCtx:
        def __init__(self):
            self.session = FakeSession()

        async def __aenter__(self):
            return self.session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeAdapter:
        async def should_participate(self, **kwargs):
            return True

        async def generate_autonomous_reply(self, **kwargs):
            raise RuntimeError("boom")

    class FakeFactory:
        def get_for_agent(self, agent_def):
            return FakeAdapter()

    fake_repo = FakeRepo()
    events: list[dict] = []

    class FakeModelConfigService:
        def __init__(self, session, org_id: str):
            self.session = session
            self.org_id = org_id

        async def list_runtime_models(self, model_type: str | None = None):
            return [
                {
                    "id": "cfg-doubao",
                    "org_id": "org-1",
                    "provider": "volcengine",
                    "model_key": "doubao-pro",
                    "display_name": "Doubao",
                    "endpoint": "https://doubao.example",
                    "model_type": "chat",
                    "is_active": True,
                    "priority": 1,
                    "rpm_limit": None,
                    "health_status": "healthy",
                    "health_message": None,
                    "api_key": "doubao-secret",
                }
            ]

    class FakeGateway:
        def __init__(self):
            self.calls: list[dict] = []

        async def select_runtime(
            self,
            models: list[dict] | None = None,
            *,
            excluded_runtime_ids: set[str] | None = None,
            model_types: set[str] | None = None,
            reserve: bool = True,
        ):
            self.calls.append(
                {
                    "models": list(models or []),
                    "model_types": model_types,
                    "reserve": reserve,
                }
            )
            return {
                "runtime_key": "cfg-doubao",
                "model_config_id": "cfg-doubao",
                "model_id": "doubao-pro",
                "base_url": "https://doubao.example",
                "api_key": "doubao-secret",
                "provider": "volcengine",
            }

    fake_gateway = FakeGateway()

    async def fake_publish(room_id: str, event: dict):
        events.append(event)

    monkeypatch.setattr(meeting_agent_mod, "get_session", lambda: FakeSessionCtx())
    monkeypatch.setattr(meeting_agent_mod, "MeetingRepository", lambda session: fake_repo)
    monkeypatch.setattr(meeting_agent_mod, "ModelConfigService", FakeModelConfigService)
    monkeypatch.setattr(meeting_agent_mod, "LLMGateway", lambda: fake_gateway)
    monkeypatch.setattr(meeting_agent_mod.meeting_stream_broker, "publish", fake_publish)

    service = meeting_agent_mod.MeetingAgentService()
    service._factory = FakeFactory()

    await service.check_autonomous_participation(
        room_id="room-1",
        org_id="org-1",
        user_id="user-1",
    )

    assert any(evt["event"] == "agent_run_started" for evt in events)
    assert any(evt["event"] == "agent_run_failed" for evt in events)
    assert fake_repo.created_messages[-1]["content"].startswith("[Agent AI 助手] 响应失败:")
