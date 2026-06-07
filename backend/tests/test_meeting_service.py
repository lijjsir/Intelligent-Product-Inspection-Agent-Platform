from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from agent.router.contracts import AgentRouteDecision, AgentRouterOutput
from app.core.exceptions import ForbiddenError
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
            quote_message_id=kwargs.get("quote_message_id"),
            metadata_json=kwargs.get("metadata_json"),
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
            project_id: str = "default",
            include_project_shared: bool = True,
            statuses=None,
            limit: int = 50,
        ):
            if statuses == ["active"]:
                return [
                    SimpleNamespace(
                        memory_id="mem_active_1",
                        content_summary="P001 最近批次风险上升",
                        content_json={"title": "P001 风险上升", "recommended_scope": "project_shared"},
                        confidence=0.8,
                        status="active",
                        memory_type="decision",
                        created_by="user-1",
                        created_at=None,
                        updated_at=None,
                        scope_json={"project_id": "default"},
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
            project_id: str = "default",
            include_project_shared: bool = True,
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
async def test_confirm_memory_publishes_project_scope_binding():
    memory = SimpleNamespace(
        memory_id="mem_meeting_1",
        content_summary="P001 下月提高抽检比例",
        content_json={
            "title": "P001 抽检策略",
            "content": "P001 下月提高抽检比例",
            "memory_type": "decision",
            "source_id": "room-1",
            "project_id": "default",
        },
        scope_json={"meeting_room_id": "room-1", "project_id": "default"},
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

        async def update_memory_item(self, *, org_id: str, memory_id: str, status=None, content_summary=None, content_json=None):
            if status is not None:
                memory.status = status
            if content_summary is not None:
                memory.content_summary = content_summary
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
        "mem_meeting_1",
        MeetingMemoryUpdateRequest(title="P001 抽检策略", content="P001 下月提高抽检比例", scope="project_shared"),
    )

    assert result.status == "active"
    assert result.scope == "project_shared"
    assert result.confirmed_by == "user-1"
    assert fake_repo.scope_bindings[-1]["scope_type"] == "project"
    assert fake_repo.transfer_logs[-1]["status"] == "confirmed"
    assert fake_repo.created_messages[-1]["message_type"] == "system"


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
            "project_id": "default",
        },
        scope_json={"meeting_room_id": "room-1", "project_id": "default"},
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
        await service.confirm_memory("mem_meeting_1", MeetingMemoryUpdateRequest(scope="project_shared"))
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
