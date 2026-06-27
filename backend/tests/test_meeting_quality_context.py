from types import SimpleNamespace

import pytest

from agent.router.contracts import AgentRouteDecision, AgentRouterOutput
from app.schemas.meeting import MeetingAgentRunRequest
from app.services import meeting_service as meeting_service_mod


class FakeSession:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


class FakeUsersRepo:
    async def get_by_id(self, org_id: str, user_id: str):
        return SimpleNamespace(username="alice", role="user")


class DefaultDomainMeetingRepo:
    def __init__(self):
        self.created_messages: list[dict] = []

    async def get_member(self, org_id: str, room_id: str, user_id: str):
        return SimpleNamespace(id="member-1", org_id=org_id, room_id=room_id, user_id=user_id, role="member")

    async def get_room(self, org_id: str, room_id: str):
        return SimpleNamespace(
            id=room_id,
            org_id=org_id,
            created_by="user-1",
            status="active",
            allowed_data_domains=None,
            memory_policy={},
        )

    async def list_recent_messages(self, *, org_id: str, room_id: str, limit: int = 50, **kwargs):
        return [
            SimpleNamespace(
                id="msg-1",
                seq_no=1,
                username="alice",
                content="@会议Agent 有几条质检任务被创建？",
                message_type="user",
            )
        ]

    async def list_memory_items_for_room(self, **kwargs):
        return []

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
            quote_message_id=kwargs.get("quote_message_id"),
            metadata_json=kwargs.get("metadata_json"),
            private_recipient_user_id=(kwargs.get("metadata_json") or {}).get("private_recipient_user_id"),
            created_at=None,
            updated_at=None,
        )


@pytest.mark.asyncio
async def test_general_meeting_agent_reads_quality_tasks_with_default_room_domains(monkeypatch):
    captured_payloads: list[dict] = []
    published: list[dict] = []

    class FakeAgentManagerService:
        async def run_chat(self, payload: dict, db_session=None):
            captured_payloads.append(payload)
            return AgentRouterOutput(
                route_decision=AgentRouteDecision(
                    selected_agent="quality_analysis",
                    sub_route="quality_task_status",
                    intent="quality_task_status",
                    confidence=0.9,
                    reason="quality_task_status",
                    route_source="manager",
                ),
                agent_output={
                    "answer": "当前可见范围内共 3 条质检任务，其中 1 条需要复核。",
                    "message_type": "task_status",
                    "capabilities_used": ["quality.task.status", "chat.response.compose"],
                },
                status="completed",
            )

    async def fake_publish(room_id: str, event: dict):
        published.append(event)

    monkeypatch.setattr(meeting_service_mod, "AgentManagerService", FakeAgentManagerService)
    monkeypatch.setattr(meeting_service_mod.meeting_stream_broker, "publish", fake_publish)

    service = meeting_service_mod.MeetingService(FakeSession(), "org-1", "user-1")
    service._repo = DefaultDomainMeetingRepo()
    service._users = FakeUsersRepo()
    service._select_general_agent_subgraph = lambda query, mode: "agent_manager"

    async def fake_build_inspection_context(room=None):
        return {
            "stats": {"total": 3, "status_done": 2, "status_failed": 1},
            "quality_insights": {"failed_or_risky_count": 1},
            "recent_tasks": [],
            "recent_failures": [],
            "selected_tasks": [],
        }

    service._build_meeting_inspection_context = fake_build_inspection_context

    result = await service.run_general_agent(
        "room-1",
        MeetingAgentRunRequest(query="@会议Agent 有几条质检任务被创建？", mode="auto"),
    )

    assert result.selected_subgraph == "quality_task_status"
    assert "3 条质检任务" in result.answer
    assert captured_payloads[0]["ext"]["inspection_context"]["stats"]["total"] == 3
    assert "quality.task" in captured_payloads[0]["metadata"]["allowed_data_domains"]
    assert service._repo.created_messages[-1]["metadata_json"]["selected_subgraph"] == "quality_task_status"
    assert published[-1]["event"] == "message_created"
