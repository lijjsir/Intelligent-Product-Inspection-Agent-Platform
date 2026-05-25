from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.services import meeting_agent_service as meeting_agent_mod
from app.services import meeting_service as meeting_service_mod


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

    async def get_room(self, org_id: str, room_id: str):
        return SimpleNamespace(id=room_id, org_id=org_id, created_by="user-1")

    async def get_member(self, org_id: str, room_id: str, user_id: str):
        return SimpleNamespace(id="member-1", org_id=org_id, room_id=room_id, user_id=user_id)

    async def create_message(self, **kwargs):
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
            created_at=None,
            updated_at=None,
        )
        self.created_messages.append(kwargs)
        return message


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
        return [{"agent_id": "agent-1", "agent_name": "AI 助手"}]

    service._parse_mentions = fake_parse_mentions

    result = await service.send_message("room-1", "@AI 助手 看一下")

    assert result.content == "@AI 助手 看一下"
    assert autonomous_called is False
    assert fake_repo.created_messages[0]["mentions"] == [{"agent_id": "agent-1", "agent_name": "AI 助手"}]


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
