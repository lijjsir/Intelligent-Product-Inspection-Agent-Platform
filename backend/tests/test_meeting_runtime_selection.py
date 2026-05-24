from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import meeting_agent_service as meeting_agent_mod
from app.services import meeting_ai_service as meeting_ai_mod


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


class FakeSessionCtx:
    def __init__(self) -> None:
        self.session = FakeSession()

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def make_runtime_models() -> list[dict[str, object]]:
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
        },
        {
            "id": "cfg-qwen",
            "org_id": "org-1",
            "provider": "volcengine",
            "model_key": "qwen-plus",
            "display_name": "Qwen",
            "endpoint": "https://qwen.example",
            "model_type": "chat",
            "is_active": True,
            "priority": 2,
            "rpm_limit": None,
            "health_status": "healthy",
            "health_message": None,
            "api_key": "qwen-secret",
        },
    ]


def make_model_config_service(runtime_models: list[dict[str, object]]):
    class FakeModelConfigService:
        def __init__(self, session, org_id: str):
            self.session = session
            self.org_id = org_id

        async def list_runtime_models(self, model_type: str | None = None):
            return runtime_models

    return FakeModelConfigService


def make_gateway():
    class FakeGateway:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        async def select_runtime(
            self,
            models: list[dict] | None = None,
            *,
            excluded_runtime_ids: set[str] | None = None,
            model_types: set[str] | None = None,
            reserve: bool = True,
        ):
            candidate_models = list(models or [])
            self.calls.append(
                {
                    "models": candidate_models,
                    "model_types": model_types,
                    "reserve": reserve,
                }
            )
            if not candidate_models:
                return None
            selected = candidate_models[0]
            return {
                "runtime_key": str(selected.get("id") or ""),
                "model_config_id": str(selected.get("id") or ""),
                "model_id": str(selected.get("model_key") or ""),
                "base_url": str(selected.get("endpoint") or ""),
                "api_key": selected.get("api_key"),
                "provider": str(selected.get("provider") or "custom"),
            }

    return FakeGateway()


@pytest.mark.asyncio
async def test_meeting_agent_uses_model_config_runtime_even_if_agent_model_is_stale(monkeypatch):
    runtime_models = make_runtime_models()
    gateway = make_gateway()
    events: list[dict] = []

    class FakeRepo:
        def __init__(self) -> None:
            self.created_messages: list[dict] = []

        async def get_visible_agent_definition(self, org_id: str, agent_def_id: str):
            return SimpleNamespace(
                id=agent_def_id,
                org_id=org_id,
                name="AI 助手",
                system_prompt="你是一个会议助手。",
                model="deepseek-chat",
                adapter_type="llm",
                participation_strategy={"auto_reply": False},
                is_active=True,
            )

        async def list_messages(self, org_id: str, room_id: str, after_seq: int = 0, limit: int = 20):
            return [
                SimpleNamespace(message_type="user", username="alice", content="hello world"),
            ]

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

    class FakeAdapter:
        def __init__(self) -> None:
            self.runtime_model = None

        async def invoke(self, **kwargs):
            self.runtime_model = kwargs.get("runtime_model")
            return "doubao response"

        async def should_participate(self, **kwargs):
            return False

        async def generate_autonomous_reply(self, **kwargs):
            return "unused"

    class FakeFactory:
        def __init__(self, adapter: FakeAdapter) -> None:
            self._adapter = adapter

        def get_for_agent(self, agent_def):
            return self._adapter

    async def fake_publish(room_id: str, event: dict):
        events.append(event)

    fake_repo = FakeRepo()
    fake_adapter = FakeAdapter()

    monkeypatch.setattr(meeting_agent_mod, "MeetingRepository", lambda session: fake_repo)
    monkeypatch.setattr(meeting_agent_mod, "ModelConfigService", make_model_config_service(runtime_models))
    monkeypatch.setattr(meeting_agent_mod, "LLMGateway", lambda: gateway)
    monkeypatch.setattr(meeting_agent_mod, "get_session", lambda: FakeSessionCtx())
    monkeypatch.setattr(meeting_agent_mod.meeting_stream_broker, "publish", fake_publish)

    service = meeting_agent_mod.MeetingAgentService()
    service._factory = FakeFactory(fake_adapter)

    await service.invoke_agent(
        room_id="room-1",
        agent_def_id="11111111-1111-1111-1111-111111111111",
        agent_name="AI 助手",
        query="@AI 助手 看一下现在的结果",
        org_id="org-1",
        user_id="user-1",
        username="alice",
    )

    assert gateway.calls[0]["models"] == runtime_models
    assert gateway.calls[0]["model_types"] == {"chat", "llm", "multimodal"}
    assert fake_adapter.runtime_model is not None
    assert fake_adapter.runtime_model["model_id"] == "doubao-pro"
    assert fake_repo.created_messages[0]["content"] == "doubao response"
    assert any(event["event"] == "message_final" for event in events)


@pytest.mark.asyncio
async def test_meeting_ai_uses_model_config_runtime(monkeypatch):
    runtime_models = make_runtime_models()
    gateway = make_gateway()
    requests: list[dict] = []
    events: list[dict] = []

    class FakeModelConfigService:
        def __init__(self, session, org_id: str):
            self.session = session
            self.org_id = org_id

        async def list_runtime_models(self, model_type: str | None = None):
            return runtime_models

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "doubao ai reply"}}]}

    class FakeClient:
        def __init__(self, timeout=None):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None):
            requests.append({"url": url, "headers": headers, "json": json})
            return FakeResponse()

    class FakeRepo:
        async def get_room(self, org_id: str, room_id: str):
            return SimpleNamespace(id=room_id, org_id=org_id, created_by="user-1")

        async def get_member(self, org_id: str, room_id: str, user_id: str):
            return SimpleNamespace(id="member-1")

        async def list_messages(self, org_id: str, room_id: str, after_seq: int = 0, limit: int = 20):
            return [
                SimpleNamespace(message_type="user", username="alice", content="请看下这个会议"),
            ]

        async def create_message(self, **kwargs):
            return SimpleNamespace(
                id=kwargs.get("message_id", "msg-1"),
                room_id=kwargs["room_id"],
                user_id=kwargs["user_id"],
                username=kwargs["username"],
                seq_no=1,
                content=kwargs["content"],
                message_type=kwargs.get("message_type", "agent"),
                agent_id=kwargs.get("agent_id"),
                mentions=kwargs.get("mentions"),
                created_at=None,
                updated_at=None,
            )

    async def fake_publish(room_id: str, event: dict):
        events.append(event)

    monkeypatch.setattr(meeting_ai_mod, "ModelConfigService", FakeModelConfigService)
    monkeypatch.setattr(meeting_ai_mod, "LLMGateway", lambda: gateway)
    monkeypatch.setattr(meeting_ai_mod.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr("app.services.stream_service.meeting_stream_broker.publish", fake_publish)

    service = meeting_ai_mod.MeetingAiService(FakeSession(), "org-1", "user-1")
    service._repo = FakeRepo()

    message = await service.ai_respond("room-1")
    summary_message = await service.summarize("room-1")

    assert gateway.calls[0]["models"] == runtime_models
    assert gateway.calls[0]["model_types"] == {"chat", "llm", "multimodal"}
    assert requests[0]["url"] == "https://doubao.example/chat/completions"
    assert requests[0]["json"]["model"] == "doubao-pro"
    assert requests[0]["headers"]["Authorization"] == "Bearer doubao-secret"
    assert message.content == "doubao ai reply"
    assert requests[1]["url"] == "https://doubao.example/chat/completions"
    assert requests[1]["json"]["model"] == "doubao-pro"
    assert requests[1]["json"]["temperature"] == 0.2
    assert summary_message.agent_id == "meeting_summary"
    assert any(event["event"] == "message_created" for event in events)
