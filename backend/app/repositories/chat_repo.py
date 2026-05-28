from __future__ import annotations

from datetime import datetime

from sqlalchemy import case, exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime import utcnow
from app.models.agent_ops import AgentDefinition, IntentRoute
from app.models.chat import ChatMessage, ChatSession


class ChatSessionRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, org_id: str, user_id: str, title: str | None = None) -> ChatSession:
        obj = ChatSession(org_id=org_id, user_id=user_id, title=title, status="active")
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj, attribute_names=["created_at", "updated_at"])
        return obj

    async def get(self, org_id: str, user_id: str, session_id: str) -> ChatSession | None:
        result = await self._session.execute(
            select(ChatSession).where(
                ChatSession.org_id == org_id,
                ChatSession.user_id == user_id,
                ChatSession.id == session_id,
                ChatSession.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(self, org_id: str, user_id: str, limit: int = 100) -> list[ChatSession]:
        has_message = (
            select(ChatMessage.id)
            .where(
                ChatMessage.session_id == ChatSession.id,
                ChatMessage.deleted_at.is_(None),
            )
            .correlate(ChatSession)
            .limit(1)
        )
        result = await self._session.execute(
            select(ChatSession)
            .where(
                ChatSession.org_id == org_id,
                ChatSession.user_id == user_id,
                ChatSession.deleted_at.is_(None),
                exists(has_message),
            )
            .order_by(ChatSession.last_message_at.desc(), ChatSession.updated_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def touch(self, org_id: str, user_id: str, session_id: str, ts: datetime | None = None) -> None:
        await self._session.execute(
            update(ChatSession)
            .where(
                ChatSession.org_id == org_id,
                ChatSession.user_id == user_id,
                ChatSession.id == session_id,
                ChatSession.deleted_at.is_(None),
            )
            .values(last_message_at=ts or utcnow())
        )

    async def soft_delete(self, org_id: str, user_id: str, session_id: str) -> bool:
        result = await self._session.execute(
            update(ChatSession)
            .where(
                ChatSession.org_id == org_id,
                ChatSession.user_id == user_id,
                ChatSession.id == session_id,
                ChatSession.deleted_at.is_(None),
            )
            .values(status="deleted", deleted_at=utcnow())
        )
        return bool(result.rowcount and result.rowcount > 0)


class ChatMessageRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def _next_seq(self, session_id: str) -> int:
        max_seq = await self._session.scalar(
            select(func.max(ChatMessage.seq_no)).where(ChatMessage.session_id == session_id)
        )
        return int(max_seq or 0) + 1

    async def create(
        self,
        *,
        session_id: str,
        org_id: str,
        user_id: str | None,
        role: str,
        content: str,
        message_type: str = "text",
        payload: dict | None = None,
    ) -> ChatMessage:
        obj = ChatMessage(
            session_id=session_id,
            org_id=org_id,
            user_id=user_id,
            seq_no=await self._next_seq(session_id),
            role=role,
            content=content,
            message_type=message_type,
            payload=payload,
        )
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj, attribute_names=["created_at", "updated_at"])
        return obj

    async def get(self, org_id: str, message_id: str) -> ChatMessage | None:
        result = await self._session.execute(
            select(ChatMessage).where(
                ChatMessage.org_id == org_id,
                ChatMessage.id == message_id,
                ChatMessage.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_for_session(
        self,
        *,
        org_id: str,
        session_id: str,
        after_seq: int = 0,
        limit: int = 200,
    ) -> list[ChatMessage]:
        result = await self._session.execute(
            select(ChatMessage)
            .with_hint(ChatMessage, "FORCE INDEX (idx_chat_messages_org_session_seq)", dialect_name="mysql")
            .where(
                ChatMessage.org_id == org_id,
                ChatMessage.session_id == session_id,
                ChatMessage.seq_no > after_seq,
                ChatMessage.deleted_at.is_(None),
            )
            .order_by(ChatMessage.seq_no.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_assistant_for_org(
        self,
        org_id: str | None,
        *,
        start_date=None,
        end_date=None,
        limit: int | None = 100,
    ) -> list[ChatMessage]:
        stmt = (
            select(ChatMessage)
            .where(
                ChatMessage.role == "assistant",
                ChatMessage.deleted_at.is_(None),
            )
            .order_by(ChatMessage.created_at.desc())
        )
        if org_id:
            stmt = stmt.where(ChatMessage.org_id == org_id)
        if start_date:
            stmt = stmt.where(ChatMessage.created_at >= start_date)
        if end_date:
            stmt = stmt.where(ChatMessage.created_at <= end_date)
        if limit:
            stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update_assistant_message(
        self,
        *,
        org_id: str,
        message_id: str,
        content: str,
        message_type: str = "text",
        payload: dict | None = None,
    ) -> ChatMessage | None:
        obj = await self.get(org_id, message_id)
        if not obj:
            return None
        obj.content = content
        obj.message_type = message_type
        obj.payload = payload
        await self._session.flush()
        await self._session.refresh(obj, attribute_names=["updated_at"])
        return obj


class ChatOpsRepository:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id

    async def ensure_chat_binding(self) -> None:
        agent_result = await self._session.execute(
            select(AgentDefinition)
            .where(
                AgentDefinition.org_id == self._org_id,
                AgentDefinition.workflow_binding == "quality_chat_v2",
                AgentDefinition.deleted_at.is_(None),
            )
            .order_by(
                case((AgentDefinition.subgraph_key == "chat", 0), else_=1),
                AgentDefinition.created_at.asc(),
                AgentDefinition.id.asc(),
            )
            .limit(1)
        )
        agent = agent_result.scalars().first()
        if agent is None:
            agent = AgentDefinition(
                org_id=self._org_id,
                name="质量检测聊天智能体",
                description="面向质量检测问答场景的聊天子图",
                workflow_binding="quality_chat_v2",
                subgraph_key="chat",
                entry_graph="MemoryManagerGraph",
                supports_start_stop=True,
                graph_version="v2",
                is_active=True,
            )
            agent.name = "QualityChatAgent"
            agent.description = "QualityChat agent for general chat and RAG QA."
            self._session.add(agent)
            await self._session.flush()
        else:
            agent.name = "QualityChatAgent"
            agent.description = getattr(agent, "description", None) or "QualityChat agent for general chat and RAG QA."
            agent.subgraph_key = "chat"
            agent.entry_graph = str(agent.entry_graph or "MemoryManagerGraph")
            agent.graph_version = str(agent.graph_version or "v2")

        route_result = await self._session.execute(
            select(IntentRoute)
            .where(
                IntentRoute.org_id == self._org_id,
                IntentRoute.intent_name == "chat",
                IntentRoute.deleted_at.is_(None),
            )
            .order_by(IntentRoute.priority.desc(), IntentRoute.created_at.asc(), IntentRoute.id.asc())
            .limit(1)
        )
        route = route_result.scalars().first()
        if route is None:
            route = IntentRoute(
                org_id=self._org_id,
                intent_name="chat",
                agent_id=agent.id,
                priority=100,
                sample_count=0,
                is_active=True,
            )
            self._session.add(route)
            await self._session.flush()
