# Meeting Agent LLM Adapter — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce LLM-backed agents into meeting rooms with @mention and autonomous participation, using an adapter pattern that allows future swap to real agent pipelines.

**Architecture:** A `BaseAgentAdapter` abstraction with `LLMAgentAdapter` (current, calls DeepSeek API) and `PipelineAgentAdapter` (stub for future). `MeetingAgentService` uses `AgentAdapterFactory` to resolve the right adapter per agent definition. Autonomous participation is checked via background asyncio tasks after each user message.

**Tech Stack:** Python/FastAPI backend, SQLAlchemy async, DeepSeek API via httpx, Vue 3 + Pinia frontend, SSE streaming

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/migrations/versions/0053_add_meeting_agent_definitions.py` | Create | Migration: new table + seed row |
| `backend/app/models/meeting.py` | Modify | Add `MeetingAgentDefinition` model |
| `backend/app/schemas/meeting.py` | Modify | Add agent definition schemas |
| `backend/app/repositories/meeting_repo.py` | Modify | Add agent definition CRUD |
| `backend/agent/adapters/__init__.py` | Create | Package init with re-exports |
| `backend/agent/adapters/base.py` | Create | `BaseAgentAdapter` ABC |
| `backend/agent/adapters/llm_adapter.py` | Create | LLM-backed adapter |
| `backend/agent/adapters/pipeline_adapter.py` | Create | Future pipeline adapter stub |
| `backend/agent/adapters/factory.py` | Create | Adapter factory |
| `backend/app/services/meeting_ai_service.py` | Modify | Add streaming LLM call method |
| `backend/app/services/meeting_agent_service.py` | Modify | Refactor to use adapters |
| `backend/app/services/meeting_service.py` | Modify | Trigger autonomous check after send |
| `backend/app/api/v1/meetings.py` | Modify | Add agent-def endpoints, update agent list |
| `frontend/src/api/meeting.api.ts` | Modify | Add agent-def API calls |
| `frontend/src/stores/meeting.store.ts` | Modify | Add agent management state |
| `frontend/src/views/MeetingRoomView.vue` | Modify | Add agent management UI |

---

### Task 1: Database Migration

**Files:**
- Create: `backend/migrations/versions/0053_add_meeting_agent_definitions.py`

- [ ] **Step 1: Write the migration file**

```python
"""add meeting_agent_definitions

Revision ID: 0053
Revises: 0052
Create Date: 2026-05-23
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence

from alembic import op
from sqlalchemy import Boolean, Column, DateTime, String, Text, JSON, text
from sqlalchemy.dialects.mysql import BINARY


revision: str = "0053"
down_revision: str | None = "0052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "meeting_agent_definitions",
        Column("id", BINARY(16), primary_key=True),
        Column("org_id", BINARY(16), nullable=False, index=True),
        Column("name", String(64), nullable=False),
        Column("system_prompt", Text, nullable=False),
        Column("model", String(64), nullable=False, server_default="deepseek-chat"),
        Column("adapter_type", String(32), nullable=False, server_default="llm"),
        Column("participation_strategy", JSON, nullable=True),
        Column("is_active", Boolean, nullable=False, server_default=text("1")),
        Column("created_by", BINARY(16), nullable=True, index=True),
        Column("created_at", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(3)")),
        Column("updated_at", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")),
        Column("deleted_at", DateTime, nullable=True),
    )

    # Seed a default "AI 助手" agent definition
    default_id = uuid.uuid4().bytes
    op.execute(
        f"INSERT INTO meeting_agent_definitions "
        f"(id, org_id, name, system_prompt, model, adapter_type, participation_strategy, is_active) "
        f"VALUES ("
        f"0x{default_id.hex()}, "
        f"0x{chr(0)*16}, "  # org_id = zero UUID (system default)
        f"'AI 助手', "
        f"'你是一个会议协作助手，正在参与一个多人会议室讨论。请用中文回复，语气友好、简洁、专业。根据对话内容给出有价值的回应。', "
        f"'deepseek-chat', "
        f"'llm', "
        f"'{{\"auto_reply\": true, \"cooldown_seconds\": 30, \"strategies\": {{\"message_count\": {{\"enabled\": true, \"every_n_messages\": 5}}, \"topic_match\": {{\"enabled\": false, \"keywords\": []}}, \"silence_timer\": {{\"enabled\": true, \"after_seconds\": 300}}}}}}', "
        f"1"
        f")"
    )


def downgrade() -> None:
    op.drop_table("meeting_agent_definitions")
```

- [ ] **Step 2: Commit**

```bash
git add backend/migrations/versions/0053_add_meeting_agent_definitions.py
git commit -m "feat: add meeting_agent_definitions migration with default agent seed"
```

---

### Task 2: SQLAlchemy Model

**Files:**
- Modify: `backend/app/models/meeting.py`

- [ ] **Step 1: Add MeetingAgentDefinition model**

Add after the `MeetingRoomAgent` class (after line 56):

```python
class MeetingAgentDefinition(Base, TimestampMixin):
    __tablename__ = "meeting_agent_definitions"
    __table_args__ = (
        Index("idx_mad_org_active", "org_id", "is_active"),
    )

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False, default="deepseek-chat")
    adapter_type: Mapped[str] = mapped_column(String(32), nullable=False, default="llm")
    participation_strategy: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str | None] = mapped_column(UUIDBinary, index=True, nullable=True)
```

Import `Boolean` from sqlalchemy at the top of the file (it should already be there, verify it's in the import line).

- [ ] **Step 2: Commit**

```bash
git add backend/app/models/meeting.py
git commit -m "feat: add MeetingAgentDefinition model"
```

---

### Task 3: Pydantic Schemas

**Files:**
- Modify: `backend/app/schemas/meeting.py`

- [ ] **Step 1: Add agent definition schemas**

Add after the `AdminMeetingRoomQuery` class (end of file):

```python
# ── Agent Definition schemas ──────────────────────────────────────

class AgentDefinitionResponse(BaseModel):
    id: str
    org_id: str
    name: str
    system_prompt: str
    model: str = "deepseek-chat"
    adapter_type: str = "llm"
    participation_strategy: dict | None = None
    is_active: bool = True
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class AgentDefinitionCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    system_prompt: str = Field(..., min_length=1, max_length=5000)
    model: str = Field(default="deepseek-chat", max_length=64)
    adapter_type: str = Field(default="llm", pattern="^(llm|pipeline)$")
    participation_strategy: dict | None = None


class AgentDefinitionUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    system_prompt: str | None = Field(default=None, min_length=1, max_length=5000)
    model: str | None = Field(default=None, max_length=64)
    participation_strategy: dict | None = None
    is_active: bool | None = None
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/meeting.py
git commit -m "feat: add agent definition schemas"
```

---

### Task 4: Repository — Agent Definition CRUD

**Files:**
- Modify: `backend/app/repositories/meeting_repo.py`

- [ ] **Step 1: Add agent definition repository methods**

Add after the `count_agents` method (after line 235), before the `# ── Admin ──` section:

```python
    # ── Agent Definitions ──────────────────────────────────────────

    async def create_agent_definition(
        self,
        *,
        org_id: str,
        name: str,
        system_prompt: str,
        model: str = "deepseek-chat",
        adapter_type: str = "llm",
        participation_strategy: dict | None = None,
        created_by: str,
    ) -> MeetingAgentDefinition:
        from app.models.meeting import MeetingAgentDefinition
        row = MeetingAgentDefinition(
            org_id=org_id,
            name=name,
            system_prompt=system_prompt,
            model=model,
            adapter_type=adapter_type,
            participation_strategy=participation_strategy or {
                "auto_reply": True,
                "cooldown_seconds": 30,
                "strategies": {
                    "message_count": {"enabled": True, "every_n_messages": 5},
                    "topic_match": {"enabled": False, "keywords": []},
                    "silence_timer": {"enabled": True, "after_seconds": 300},
                },
            },
            created_by=created_by,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row, attribute_names=["created_at", "updated_at"])
        return row

    async def get_agent_definition(self, org_id: str, agent_def_id: str) -> MeetingAgentDefinition | None:
        from app.models.meeting import MeetingAgentDefinition
        result = await self._session.execute(
            select(MeetingAgentDefinition).where(
                MeetingAgentDefinition.id == agent_def_id,
                MeetingAgentDefinition.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_active_agent_definitions(self, org_id: str) -> list[MeetingAgentDefinition]:
        from app.models.meeting import MeetingAgentDefinition
        result = await self._session.execute(
            select(MeetingAgentDefinition).where(
                MeetingAgentDefinition.is_active.is_(True),
                MeetingAgentDefinition.deleted_at.is_(None),
            ).order_by(MeetingAgentDefinition.name.asc())
        )
        return list(result.scalars().all())

    async def update_agent_definition(
        self, org_id: str, agent_def_id: str, **fields
    ) -> MeetingAgentDefinition | None:
        from app.models.meeting import MeetingAgentDefinition
        row = await self.get_agent_definition(org_id, agent_def_id)
        if row is None:
            return None
        for key, value in fields.items():
            if value is not None and hasattr(row, key):
                setattr(row, key, value)
        await self._session.flush()
        return row

    async def delete_agent_definition(self, org_id: str, agent_def_id: str) -> bool:
        from app.models.meeting import MeetingAgentDefinition
        row = await self.get_agent_definition(org_id, agent_def_id)
        if row is None:
            return False
        row.deleted_at = datetime.utcnow()
        await self._session.flush()
        return True
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/repositories/meeting_repo.py
git commit -m "feat: add agent definition CRUD to meeting repo"
```

---

### Task 5: Adapter Base Class

**Files:**
- Create: `backend/agent/adapters/__init__.py`
- Create: `backend/agent/adapters/base.py`

- [ ] **Step 1: Create package init**

```python
from agent.adapters.base import BaseAgentAdapter
from agent.adapters.llm_adapter import LLMAgentAdapter
from agent.adapters.pipeline_adapter import PipelineAgentAdapter
from agent.adapters.factory import AgentAdapterFactory

__all__ = [
    "BaseAgentAdapter",
    "LLMAgentAdapter",
    "PipelineAgentAdapter",
    "AgentAdapterFactory",
]
```

- [ ] **Step 2: Write the abstract base**

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable


class BaseAgentAdapter(ABC):
    """Abstract adapter for agent invocation — LLM or pipeline backed."""

    @abstractmethod
    async def invoke(
        self,
        *,
        room_id: str,
        agent_def: Any,
        query: str,
        context_messages: list[dict[str, str]],
        emit: Callable,
    ) -> str:
        """Called when this agent is @mentioned. Returns the agent's reply text."""
        ...

    @abstractmethod
    async def should_participate(
        self,
        *,
        agent_def: Any,
        messages_since_last: int,
        seconds_since_last: float,
        recent_content: str,
    ) -> bool:
        """Return True if the agent should autonomously speak now."""
        ...

    @abstractmethod
    async def generate_autonomous_reply(
        self,
        *,
        room_id: str,
        agent_def: Any,
        recent_messages: list[dict[str, str]],
        emit: Callable,
    ) -> str:
        """Generate a reply when autonomous participation is triggered."""
        ...
```

- [ ] **Step 3: Commit**

```bash
git add backend/agent/adapters/__init__.py backend/agent/adapters/base.py
git commit -m "feat: add BaseAgentAdapter abstract class"
```

---

### Task 6: Pipeline Adapter Stub

**Files:**
- Create: `backend/agent/adapters/pipeline_adapter.py`

- [ ] **Step 1: Write stub implementation**

```python
from __future__ import annotations

from typing import Any, Callable

from agent.adapters.base import BaseAgentAdapter


class PipelineAgentAdapter(BaseAgentAdapter):
    """Adapter that routes to the full agent orchestrator pipeline.

    Stub — will be implemented when real agent pipelines are ready.
    """

    async def invoke(
        self,
        *,
        room_id: str,
        agent_def: Any,
        query: str,
        context_messages: list[dict[str, str]],
        emit: Callable,
    ) -> str:
        raise NotImplementedError("PipelineAgentAdapter is not yet implemented")

    async def should_participate(
        self,
        *,
        agent_def: Any,
        messages_since_last: int,
        seconds_since_last: float,
        recent_content: str,
    ) -> bool:
        raise NotImplementedError("PipelineAgentAdapter is not yet implemented")

    async def generate_autonomous_reply(
        self,
        *,
        room_id: str,
        agent_def: Any,
        recent_messages: list[dict[str, str]],
        emit: Callable,
    ) -> str:
        raise NotImplementedError("PipelineAgentAdapter is not yet implemented")
```

- [ ] **Step 2: Commit**

```bash
git add backend/agent/adapters/pipeline_adapter.py
git commit -m "feat: add PipelineAgentAdapter stub"
```

---

### Task 7: LLM Adapter

**Files:**
- Create: `backend/agent/adapters/llm_adapter.py`

- [ ] **Step 1: Write LLM adapter with streaming**

```python
from __future__ import annotations

import json
import logging
from typing import Any, Callable

import httpx

from app.core.config import settings
from agent.adapters.base import BaseAgentAdapter

logger = logging.getLogger(__name__)


class LLMAgentAdapter(BaseAgentAdapter):
    """Calls LLM API directly with agent system_prompt + room context."""

    async def invoke(
        self,
        *,
        room_id: str,
        agent_def: Any,
        query: str,
        context_messages: list[dict[str, str]],
        emit: Callable,
    ) -> str:
        llm_messages = self._build_messages(agent_def, context_messages, query)
        return await self._stream_llm(llm_messages, emit)

    async def should_participate(
        self,
        *,
        agent_def: Any,
        messages_since_last: int,
        seconds_since_last: float,
        recent_content: str,
    ) -> bool:
        strategy = getattr(agent_def, "participation_strategy", None) or {}
        if not strategy.get("auto_reply", True):
            return False

        cooldown = int(strategy.get("cooldown_seconds", 30))
        if seconds_since_last < cooldown:
            return False

        strategies = strategy.get("strategies", {})
        if strategies.get("message_count", {}).get("enabled"):
            if messages_since_last >= int(strategies["message_count"].get("every_n_messages", 5)):
                return True

        if strategies.get("silence_timer", {}).get("enabled"):
            if seconds_since_last >= int(strategies["silence_timer"].get("after_seconds", 300)):
                return True

        if strategies.get("topic_match", {}).get("enabled"):
            keywords = strategies["topic_match"].get("keywords", [])
            if keywords and any(kw.lower() in recent_content.lower() for kw in keywords):
                return True

        return False

    async def generate_autonomous_reply(
        self,
        *,
        room_id: str,
        agent_def: Any,
        recent_messages: list[dict[str, str]],
        emit: Callable,
    ) -> str:
        system_prompt = getattr(agent_def, "system_prompt", "")
        name = getattr(agent_def, "name", "AI 助手")
        llm_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": f"你叫{name}，你正在自主参与一个会议讨论。请根据最近的对话，给出有价值的发言。"},
        ]
        for msg in recent_messages:
            role = "assistant" if msg.get("role") in ("agent", "agent_streaming") else "user"
            llm_messages.append({"role": role, "content": f"{msg.get('username', '')}: {msg.get('content', '')}"})

        return await self._stream_llm(llm_messages, emit)

    # ── private ────────────────────────────────────────────────────

    def _build_messages(
        self,
        agent_def: Any,
        context_messages: list[dict[str, str]],
        query: str,
    ) -> list[dict[str, str]]:
        system_prompt = getattr(agent_def, "system_prompt", "")
        name = getattr(agent_def, "name", "AI 助手")
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": f"你叫{name}，你正在参与一个多人会议室。有人在消息中 @了你，请直接回答这个人的问题。"},
        ]
        for msg in context_messages:
            role = "assistant" if msg.get("role") in ("agent", "agent_streaming") else "user"
            messages.append({"role": role, "content": f"{msg.get('username', '')}: {msg.get('content', '')}"})
        messages.append({"role": "user", "content": query})
        return messages

    async def _stream_llm(
        self,
        messages: list[dict[str, str]],
        emit: Callable,
    ) -> str:
        api_key = settings.deepseek_api_key
        base_url = settings.deepseek_base_url.rstrip("/")
        model = settings.deepseek_model_id

        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY not configured")

        full_content = ""
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 2000,
                    "stream": True,
                },
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[len("data:"):].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        delta = data["choices"][0].get("delta", {}).get("content", "")
                        if delta:
                            full_content += delta
                            await emit({
                                "event": "message_delta",
                                "delta": delta,
                            })
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

        if not full_content:
            full_content = "抱歉，我暂时无法回答这个问题。"

        return full_content
```

- [ ] **Step 2: Commit**

```bash
git add backend/agent/adapters/llm_adapter.py
git commit -m "feat: add LLMAgentAdapter with streaming support"
```

---

### Task 8: Adapter Factory

**Files:**
- Create: `backend/agent/adapters/factory.py`

- [ ] **Step 1: Write factory**

```python
from __future__ import annotations

from typing import Any

from agent.adapters.base import BaseAgentAdapter
from agent.adapters.llm_adapter import LLMAgentAdapter
from agent.adapters.pipeline_adapter import PipelineAgentAdapter


class AgentAdapterFactory:
    _adapters: dict[str, BaseAgentAdapter] = {}

    @classmethod
    def get(cls, adapter_type: str) -> BaseAgentAdapter:
        if adapter_type not in cls._adapters:
            if adapter_type == "llm":
                cls._adapters[adapter_type] = LLMAgentAdapter()
            elif adapter_type == "pipeline":
                cls._adapters[adapter_type] = PipelineAgentAdapter()
            else:
                raise ValueError(f"Unknown adapter_type: {adapter_type}")
        return cls._adapters[adapter_type]

    @classmethod
    def get_for_agent(cls, agent_def: Any) -> BaseAgentAdapter:
        adapter_type = getattr(agent_def, "adapter_type", "llm") or "llm"
        return cls.get(adapter_type)
```

- [ ] **Step 2: Commit**

```bash
git add backend/agent/adapters/factory.py
git commit -m "feat: add AgentAdapterFactory"
```

---

### Task 9: Enhance MeetingAiService for Streaming

**Files:**
- Modify: `backend/app/services/meeting_ai_service.py`

- [ ] **Step 1: Add streaming LLM method**

Add a new method `stream_respond` after `ai_respond`. Also add a `build_context` helper so the adapter can use it:

```python
    def build_context_messages(self, room_id: str, limit: int = 20) -> list[dict[str, str]]:
        """Return recent messages as a list of {role, username, content} dicts.
        Synchronous helper — callers must manage the session.
        """
        # This is a lightweight version; the heavy lifting stays in ai_respond / adapter
        return []

    async def stream_respond(
        self,
        *,
        room_id: str,
        agent_name: str = "AI 助手",
        system_prompt: str | None = None,
        model: str | None = None,
    ) -> MeetingMessageResponse:
        """Streaming AI response — same as ai_respond but yields via emit callback.
        Used by LLMAgentAdapter for meeting room agent streaming."""
        await self._ensure_member(room_id)

        messages = await self._repo.list_messages(
            org_id=self._org_id, room_id=room_id, after_seq=0, limit=20
        )

        default_system = system_prompt or (
            "你是一个会议协作助手，正在参与一个多人会议室。"
            "请用中文回复，语气友好、简洁、专业。"
            "根据最近的对话内容给出有价值的回应。"
        )

        llm_messages: list[dict[str, str]] = [
            {"role": "system", "content": default_system},
        ]
        for msg in messages:
            role = "assistant" if msg.message_type in ("agent", "agent_streaming") else "user"
            llm_messages.append({"role": role, "content": f"{msg.username}: {msg.content}"})

        api_key = settings.deepseek_api_key
        base_url = settings.deepseek_base_url.rstrip("/")
        llm_model = model or settings.deepseek_model_id

        if not api_key:
            raise ServiceUnavailableError("AI 助手未配置（缺少 DEEPSEEK_API_KEY）")

        full_content = ""
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST",
                    f"{base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": llm_model,
                        "messages": llm_messages,
                        "temperature": 0.7,
                        "max_tokens": 2000,
                        "stream": True,
                    },
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[len("data:"):].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            delta = data["choices"][0].get("delta", {}).get("content", "")
                            if delta:
                                full_content += delta
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
        except httpx.HTTPStatusError as exc:
            logger.error("LLM API error: %s", exc)
            raise ServiceUnavailableError(f"AI 助手请求失败: {exc.response.status_code}")
        except Exception as exc:
            logger.error("LLM call failed: %s", exc)
            raise ServiceUnavailableError(f"AI 助手调用失败: {exc}")

        if not full_content:
            full_content = "抱歉，我暂时无法回应。"

        message = await self._repo.create_message(
            org_id=self._org_id,
            room_id=room_id,
            user_id=self._user_id,
            username=agent_name,
            content=full_content,
            message_type="agent",
            agent_id="ai_assistant",
        )

        from app.services.stream_service import meeting_stream_broker
        await meeting_stream_broker.publish(room_id, {
            "event": "message_created",
            "room_id": room_id,
            "message": MeetingMessageResponse.model_validate(message).model_dump(),
        })

        return MeetingMessageResponse.model_validate(message)
```

Add `import json` at the top of the file.

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/meeting_ai_service.py
git commit -m "feat: add streaming LLM method to MeetingAiService"
```

---

### Task 10: Refactor MeetingAgentService to Use Adapters

**Files:**
- Modify: `backend/app/services/meeting_agent_service.py`

- [ ] **Step 1: Rewrite MeetingAgentService to use adapter factory**

Replace the entire file content:

```python
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from app.core.ids import uuid7
from app.repositories.meeting_repo import MeetingRepository
from agent.adapters.factory import AgentAdapterFactory
from app.services.stream_service import meeting_stream_broker
from infra.database.session import get_session

logger = logging.getLogger(__name__)

# Track last agent message time per (room_id, agent_def_id) for cooldown
_last_agent_message: dict[tuple[str, str], datetime] = {}


class MeetingAgentService:
    def __init__(self) -> None:
        self._factory = AgentAdapterFactory()

    async def invoke_agent(
        self,
        *,
        room_id: str,
        agent_def_id: str,
        agent_name: str,
        message_id: str,
        query: str,
        org_id: str,
        user_id: str,
        username: str,
    ) -> None:
        """Called when a user @mentions an agent in a message."""
        workflow_run_id = str(uuid7())
        agent_message_id = str(uuid7())

        async def emit(event: dict[str, Any]) -> None:
            event.setdefault("ts", datetime.utcnow().isoformat())
            await meeting_stream_broker.publish(room_id, event)

        try:
            async with get_session() as session:
                repo = MeetingRepository(session)
                agent_def = await repo.get_agent_definition(org_id, agent_def_id)
                if not agent_def:
                    logger.warning("agent definition not found: %s", agent_def_id)
                    return

                context_msgs = await repo.list_messages(
                    org_id=org_id, room_id=room_id, after_seq=0, limit=20
                )
                context_dicts = [
                    {"role": msg.message_type, "username": msg.username, "content": msg.content}
                    for msg in context_msgs
                ]

                adapter = self._factory.get_for_agent(agent_def)

                await emit({
                    "event": "agent_run_started",
                    "room_id": room_id,
                    "message_id": agent_message_id,
                    "agent_id": agent_def_id,
                    "agent_name": agent_name,
                    "workflow_run_id": workflow_run_id,
                })

                full_content = await adapter.invoke(
                    room_id=room_id,
                    agent_def=agent_def,
                    query=query,
                    context_messages=context_dicts,
                    emit=emit,
                )

                await repo.create_message(
                    org_id=org_id,
                    room_id=room_id,
                    user_id=user_id,
                    username=agent_name,
                    content=full_content,
                    message_type="agent",
                    agent_id=agent_def_id,
                )
                await session.commit()

            _last_agent_message[(room_id, agent_def_id)] = datetime.utcnow()

            await emit({
                "event": "message_final",
                "room_id": room_id,
                "message_id": agent_message_id,
                "agent_id": agent_def_id,
                "agent_name": agent_name,
                "workflow_run_id": workflow_run_id,
                "content": full_content,
            })

        except Exception as exc:
            logger.exception(
                "meeting agent invocation failed room_id=%s agent_id=%s workflow_run_id=%s",
                room_id, agent_def_id, workflow_run_id,
            )
            error_content = f"[Agent {agent_name}] 响应失败: {exc}"
            async with get_session() as session:
                repo = MeetingRepository(session)
                await repo.create_message(
                    org_id=org_id,
                    room_id=room_id,
                    user_id=user_id,
                    username=agent_name,
                    content=error_content,
                    message_type="agent",
                    agent_id=agent_def_id,
                )
                await session.commit()

            await emit({
                "event": "agent_run_failed",
                "room_id": room_id,
                "message_id": agent_message_id,
                "agent_id": agent_def_id,
                "agent_name": agent_name,
                "workflow_run_id": workflow_run_id,
                "error": str(exc),
            })

    async def check_autonomous_participation(
        self,
        *,
        room_id: str,
        org_id: str,
        user_id: str,
    ) -> None:
        """Check all agents in the room for autonomous participation eligibility."""
        async with get_session() as session:
            repo = MeetingRepository(session)

            room_agents = await repo.get_agents(org_id, room_id)
            if not room_agents:
                return

            recent_msgs = await repo.list_messages(
                org_id=org_id, room_id=room_id, after_seq=0, limit=30
            )
            recent_content = " ".join(m.content for m in recent_msgs[-10:])
            recent_dicts = [
                {"role": m.message_type, "username": m.username, "content": m.content}
                for m in recent_msgs[-20:]
            ]

            for ra in room_agents:
                agent_def = await repo.get_agent_definition(org_id, ra.agent_id)
                if not agent_def or not agent_def.is_active:
                    continue

                adapter = self._factory.get_for_agent(agent_def)

                # Calculate messages since last and time since last
                last_time = _last_agent_message.get((room_id, ra.agent_id))
                seconds_since = (datetime.utcnow() - last_time).total_seconds() if last_time else 999999
                msg_count_since = sum(
                    1 for m in recent_msgs
                    if last_time and m.created_at and m.created_at > last_time
                ) if last_time else len(recent_msgs)

                try:
                    if await adapter.should_participate(
                        agent_def=agent_def,
                        messages_since_last=msg_count_since,
                        seconds_since_last=seconds_since,
                        recent_content=recent_content,
                    ):
                        workflow_run_id = str(uuid7())
                        agent_message_id = str(uuid7())
                        agent_name = agent_def.name

                        async def emit(event: dict[str, Any]) -> None:
                            event.setdefault("ts", datetime.utcnow().isoformat())
                            await meeting_stream_broker.publish(room_id, event)

                        await emit({
                            "event": "agent_run_started",
                            "room_id": room_id,
                            "message_id": agent_message_id,
                            "agent_id": ra.agent_id,
                            "agent_name": agent_name,
                            "workflow_run_id": workflow_run_id,
                        })

                        content = await adapter.generate_autonomous_reply(
                            room_id=room_id,
                            agent_def=agent_def,
                            recent_messages=recent_dicts,
                            emit=emit,
                        )

                        if content:
                            await repo.create_message(
                                org_id=org_id,
                                room_id=room_id,
                                user_id=user_id,
                                username=agent_name,
                                content=content,
                                message_type="agent",
                                agent_id=ra.agent_id,
                            )
                            await session.commit()

                            _last_agent_message[(room_id, ra.agent_id)] = datetime.utcnow()

                            await emit({
                                "event": "message_final",
                                "room_id": room_id,
                                "message_id": agent_message_id,
                                "agent_id": ra.agent_id,
                                "agent_name": agent_name,
                                "workflow_run_id": workflow_run_id,
                                "content": content,
                            })
                except NotImplementedError:
                    continue  # Pipeline adapter not ready yet
                except Exception as exc:
                    logger.exception(
                        "autonomous participation failed room_id=%s agent_id=%s",
                        room_id, ra.agent_id,
                    )
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/meeting_agent_service.py
git commit -m "refactor: use adapter pattern in MeetingAgentService, add autonomous participation"
```

---

### Task 11: Trigger Autonomous Check in MeetingService

**Files:**
- Modify: `backend/app/services/meeting_service.py`

- [ ] **Step 1: Add autonomous check call after send_message**

In `send_message`, after the existing mention handling block (lines 93-109), add:

```python
        # Trigger autonomous participation check for all room agents
        asyncio.create_task(
            agent_service.check_autonomous_participation(
                room_id=room_id,
                org_id=self._org_id,
                user_id=self._user_id,
            )
        )
```

Also update the `from app.services.meeting_agent_service import MeetingAgentService` import inside `send_message` to be at the top of the file (move the import from inside the `if mentions:` block to the top-level imports). Change:

At the top, add after `from app.services.stream_service import meeting_stream_broker`:
```python
from app.services.meeting_agent_service import MeetingAgentService
```

And remove the inline import `from app.services.meeting_agent_service import MeetingAgentService` from inside the `if mentions:` block (line 95).

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/meeting_service.py
git commit -m "feat: trigger autonomous agent participation after each message"
```

---

### Task 12: Update parse_mentions to use new agent definitions

**Files:**
- Modify: `backend/app/services/meeting_service.py`

- [ ] **Step 1: Update `_parse_mentions` to resolve against agent definitions**

Replace the `_parse_mentions` method to use `meeting_agent_definitions` instead of the topology catalog:

```python
    async def _parse_mentions(self, content: str, room_id: str) -> list[dict]:
        """Extract @AgentName mentions and validate agents exist in the room."""
        raw_names = set()
        for m in _MENTION_RE.finditer(content):
            raw_names.add(m.group(1))

        if not raw_names:
            return []

        # Lookup agents in the room by name from meeting_agent_definitions
        room_agents = await self._repo.get_agents(self._org_id, room_id)
        room_agent_ids = {str(ra.agent_id) for ra in room_agents}

        # Load agent definitions for room agents
        from app.models.meeting import MeetingAgentDefinition
        from sqlalchemy import select
        agent_defs_result = await self._session.execute(
            select(MeetingAgentDefinition).where(
                MeetingAgentDefinition.id.in_(list(room_agent_ids)),
                MeetingAgentDefinition.deleted_at.is_(None),
            )
        )
        agent_defs = {str(ad.id): ad for ad in agent_defs_result.scalars().all()}

        mentions = []
        for name in raw_names:
            for agent_id, ad in agent_defs.items():
                if ad.name.lower() == name.lower() and agent_id in room_agent_ids:
                    mentions.append({"agent_id": agent_id, "agent_name": ad.name})
                    break
        return mentions
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/meeting_service.py
git commit -m "refactor: resolve @mentions against meeting_agent_definitions"
```

---

### Task 13: Update MeetingService._resolve_agent_name

**Files:**
- Modify: `backend/app/services/meeting_service.py`

- [ ] **Step 1: Update `_resolve_agent_name` to check agent definitions first**

```python
    def _resolve_agent_name(self, agent_id: str) -> str:
        """Look up agent display name from agent definitions or topology catalog."""
        # This is a sync helper — for full resolution use the repo
        try:
            from agent.topology_catalog import get_registered_subgraphs
            for item in get_registered_subgraphs():
                if item.get("subgraph_key") == agent_id:
                    return item.get("name") or agent_id
        except Exception:
            pass
        return agent_id
```

(Keep it as-is for backward compat, since `add_agent_to_room` still uses this sync helper. The actual name resolution for display happens in `MeetingAdminService.get_room_detail` which already tries the agent repo.)

- [ ] **Step 2: No separate commit — this is a minor update to the previous task**

---

### Task 14: API Endpoints

**Files:**
- Modify: `backend/app/api/v1/meetings.py`

- [ ] **Step 1: Add agent definition endpoints**

After the existing `# ── Available Agents ──` section (after line 173), add:

```python
# ── Agent Definitions ─────────────────────────────────────────────

@router.get("/agent-defs", response_model=ResponseEnvelope[list[dict]])
async def list_agent_definitions(
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """List active agent definitions available for this org."""
    require_role("meeting", current.role)
    from app.repositories.meeting_repo import MeetingRepository
    repo = MeetingRepository(db)
    defs = await repo.list_active_agent_definitions(current.org_id)
    return ResponseEnvelope(data=[
        {
            "id": str(ad.id),
            "name": ad.name,
            "system_prompt": ad.system_prompt,
            "model": ad.model,
            "adapter_type": ad.adapter_type,
            "participation_strategy": ad.participation_strategy,
            "is_active": ad.is_active,
        }
        for ad in defs
    ])
```

Also update the `list_room_agents` endpoint to include agent names from definitions. In the `list_room_agents` handler (line 178-185), update the service call to resolve names:

Replace the existing `list_room_agents` with:

```python
@router.get("/rooms/{room_id}/agents", response_model=ResponseEnvelope[list[MeetingRoomAgentResponse]])
async def list_room_agents(
    room_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = _build_service(db, current)
    return ResponseEnvelope(data=await service.list_room_agents(room_id))
```

Then update `MeetingService.list_room_agents` in `meeting_service.py` to resolve names from agent definitions:

```python
    async def list_room_agents(self, room_id: str) -> list[MeetingRoomAgentResponse]:
        await self._ensure_member(room_id)
        rows = await self._repo.get_agents(self._org_id, room_id)
        
        # Load agent definitions for name resolution
        agent_ids = [str(r.agent_id) for r in rows]
        from app.models.meeting import MeetingAgentDefinition
        from sqlalchemy import select
        result = await self._session.execute(
            select(MeetingAgentDefinition).where(
                MeetingAgentDefinition.id.in_(agent_ids),
            )
        )
        defs_by_id = {str(ad.id): ad for ad in result.scalars().all()}
        
        results = []
        for row in rows:
            ad = defs_by_id.get(str(row.agent_id))
            name = ad.name if ad else self._resolve_agent_name(row.agent_id)
            results.append(MeetingRoomAgentResponse(
                id=str(row.id), room_id=str(row.room_id), agent_id=str(row.agent_id),
                agent_name=name, role=str(row.role), added_by=str(row.added_by),
            ))
        return results
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/v1/meetings.py backend/app/services/meeting_service.py
git commit -m "feat: add agent-defs API endpoint, resolve agent names from definitions"
```

---

### Task 15: Frontend API Layer

**Files:**
- Modify: `frontend/src/api/meeting.api.ts`

- [ ] **Step 1: Add agent definition API calls**

After the existing `// ── Agent management ──` section, add:

```typescript
  // ── Agent Definitions ─────────────────────────────────────────

  listAgentDefs() {
    return http.get<Array<{
      id: string;
      name: string;
      system_prompt: string;
      model: string;
      adapter_type: string;
      participation_strategy: Record<string, unknown> | null;
      is_active: boolean;
    }>>("/v1/meetings/agent-defs");
  },
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/meeting.api.ts
git commit -m "feat: add agent-defs API call to frontend"
```

---

### Task 16: Frontend Store — Agent Management

**Files:**
- Modify: `frontend/src/stores/meeting.store.ts`

- [ ] **Step 1: Add agent definition state and actions**

Add new state after `aiThinking`:

```typescript
  const availableAgentDefs = ref<Array<{
    id: string;
    name: string;
    system_prompt: string;
    model: string;
    adapter_type: string;
    participation_strategy: Record<string, unknown> | null;
    is_active: boolean;
  }>>([]);
```

Add new actions after `removeAgent`:

```typescript
  async function loadAvailableAgentDefs() {
    try {
      const { data } = await meetingApi.listAgentDefs();
      availableAgentDefs.value = (data as { data?: typeof availableAgentDefs.value }).data
        || (data as unknown as typeof availableAgentDefs.value);
    } catch {
      availableAgentDefs.value = [];
    }
  }

  async function addAgentToRoom(agentDefId: string, role = "participant") {
    if (!activeRoom.value) return null;
    const { data } = await meetingApi.addAgent(activeRoom.value.id, { agent_id: agentDefId, role });
    const agent = (data as { data?: MeetingRoomAgent }).data || (data as unknown as MeetingRoomAgent);
    agents.value = [...agents.value, agent];
    return agent;
  }

  async function removeAgentFromRoom(agentId: string) {
    if (!activeRoom.value) return;
    await meetingApi.removeAgent(activeRoom.value.id, agentId);
    agents.value = agents.value.filter((a) => a.agent_id !== agentId);
  }

  async function toggleAgentAuto(agentId: string, enabled: boolean) {
    // Future: call API to toggle participation strategy
    // For now, this is a placeholder for the UI toggle
  }
```

Update the return statement to include the new exports:

```typescript
  return {
    // state
    rooms, messages, agents, activeRoomId, eventSource, streamConnected,
    streamingContent, loadingRooms, loadingMessages, sending, messageReactions,
    availableAgentDefs,
    // computed
    activeRoom, canSend, lastMessageSeq,
    // actions
    loadRooms, createRoom, joinRoom,
    loadMessages, sendMessage,
    aiEnabled, aiThinking, aiChat,
    loadAgents, addAgent, removeAgent, deleteRoom,
    loadAvailableAgentDefs, addAgentToRoom, removeAgentFromRoom, toggleAgentAuto,
    connectStream, disconnectStream, handleStreamEvent,
    setReaction,
  };
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/stores/meeting.store.ts
git commit -m "feat: add agent definition state and actions to meeting store"
```

---

### Task 17: Frontend UI — Agent Management Panel

**Files:**
- Modify: `frontend/src/views/MeetingRoomView.vue`

- [ ] **Step 1: Add agent management UI in room header**

In the `<template>`, replace the header-right area (around the existing AI toggle button):

```vue
        <div class="room-header-right">
          <!-- Agent Management -->
          <el-popover
            v-if="store.activeRoom"
            placement="bottom-end"
            :width="320"
            trigger="click"
          >
            <template #reference>
              <el-button size="small">
                管理 Agent ({{ store.agents.length }})
              </el-button>
            </template>
            <div class="agent-panel">
              <div class="agent-panel-head">
                <span>会议室 Agent</span>
                <el-dropdown @command="(id: string) => store.addAgentToRoom(id)">
                  <el-button size="small" text type="primary">
                    + 添加
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item
                        v-for="ad in store.availableAgentDefs"
                        :key="ad.id"
                        :command="ad.id"
                        :disabled="store.agents.some(a => a.agent_id === ad.id)"
                      >
                        {{ ad.name }}
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
              <div v-if="store.agents.length === 0" class="agent-panel-empty">
                暂未添加 Agent，点击"+ 添加"选择
              </div>
              <div v-for="agent in store.agents" :key="agent.id" class="agent-item">
                <span class="agent-item-name">{{ agent.agent_name }}</span>
                <span class="agent-item-role">{{ agent.role === 'observer' ? '观察者' : '参与者' }}</span>
                <el-button
                  size="small"
                  type="danger"
                  text
                  @click="store.removeAgentFromRoom(agent.agent_id)"
                >
                  移除
                </el-button>
              </div>
            </div>
          </el-popover>

          <!-- AI Toggle (keep existing) -->
          <el-button
            v-if="store.activeRoom"
            :type="store.aiEnabled ? 'primary' : 'default'"
            :icon="MagicStick"
            :loading="store.aiThinking"
            size="small"
            @click="store.aiEnabled = !store.aiEnabled"
          >
            AI 助手{{ store.aiEnabled ? ' · 开' : '' }}
          </el-button>
          <div v-if="store.activeRoom" class="room-code">
            <span>会议码</span>
            <strong>{{ store.activeRoom.access_code }}</strong>
          </div>
          <el-button v-if="store.activeRoom && store.activeRoom.created_by === auth.userId" text type="danger" :icon="Delete" @click="handleDeleteRoom">
            删除
          </el-button>
        </div>
```

- [ ] **Step 2: Add agent panel styles**

Add after the existing `.room-code strong` block in `<style scoped>`:

```css
/* Agent Panel */
.agent-panel {
  max-height: 360px;
  overflow-y: auto;
}

.agent-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid #f4f4f5;
}

.agent-panel-head span {
  font-weight: 700;
  font-size: 14px;
  color: #111827;
}

.agent-panel-empty {
  padding: 20px 0;
  color: #a1a1aa;
  font-size: 13px;
  text-align: center;
}

.agent-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px solid #fafafa;
}

.agent-item-name {
  flex: 1;
  font-weight: 600;
  font-size: 13px;
  color: #111827;
}

.agent-item-role {
  font-size: 11px;
  color: #71717a;
  background: #f4f4f5;
  padding: 1px 6px;
  border-radius: 4px;
}
```

- [ ] **Step 3: Load agent defs on room change**

Add to the `watch` on `activeRoomId` (after `store.loadMessages(0)`):

```typescript
  await store.loadAgents();
  await store.loadAvailableAgentDefs();
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/MeetingRoomView.vue
git commit -m "feat: add agent management panel to meeting room UI"
```

---

### Task 18: Wire Autonomous Participation from Frontend

**Files:**
- Modify: `frontend/src/views/MeetingRoomView.vue`

- [ ] **Step 1: Remove old aiChat auto-trigger, agent participation is now server-side**

In `sendMessage()`, remove the auto AI trigger block:

```typescript
async function sendMessage() {
  if (!store.canSend) return;
  const content = input.value.trim();
  await store.sendMessage(content);
  input.value = "";
  await scrollToBottom();
  // Autonomous agent participation is now handled server-side via SSE
}
```

(Remove the `if (store.aiEnabled)` block that calls `store.aiChat()`.)

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/MeetingRoomView.vue
git commit -m "refactor: remove client-side aiChat trigger, agent participation is now server-driven"
```

---

### Task 19: Integration Verification

- [ ] **Step 1: Run backend migration to verify it applies cleanly**

```bash
cd backend && python -m alembic upgrade head
```
Expected: Migration 0053 applies without error.

- [ ] **Step 2: Verify adapter imports work**

```bash
cd backend && python -c "from agent.adapters import BaseAgentAdapter, LLMAgentAdapter, PipelineAgentAdapter, AgentAdapterFactory; print('All imports OK')"
```
Expected: `All imports OK`

- [ ] **Step 3: Commit final verification**

```bash
git add -A
git commit -m "chore: verify adapter integration imports and migration"
```
