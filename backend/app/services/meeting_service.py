from __future__ import annotations

import asyncio
import logging
import re
import secrets
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.ids import uuid7
from app.core.permissions import (
    ROLE_ADMIN,
    ROLE_ALGORITHM_ENGINEER,
    ROLE_APP_DEVELOPER,
    ROLE_EXPERT,
    ROLE_PLATFORM_OPERATOR,
    ROLE_USER,
)
from app.core.security import hash_password, verify_password
from app.models.memory import MemoryItem
from app.repositories.meeting_repo import MeetingRepository
from app.repositories.user_repo import UserRepository
from app.schemas.meeting import (
    MeetingActionItemCreateRequest,
    MeetingActionItemResponse,
    MeetingActionItemUpdateRequest,
    MeetingAgentQueryAuditResponse,
    MeetingAgentRunRequest,
    MeetingAgentRunResponse,
    MeetingCandidateMemoryResponse,
    MeetingContextPreviewResponse,
    MeetingDiscussionStartResponse,
    MeetingMemoryExtractRequest,
    MeetingMemoryResponse,
    MeetingMemoryScopeRequest,
    MeetingMemorySourceResponse,
    MeetingMemoryTransferRequest,
    MeetingMemoryUpdateRequest,
    MeetingMessageResponse,
    MeetingRoomAgentResponse,
    MeetingRoomDetailResponse,
    MeetingRoomMemberResponse,
    MeetingRoomResponse,
)
from app.services.agent_manager_service import AgentManagerService
from app.services.chat_context_service import ChatContextService
from app.services.meeting_agent_service import MeetingAgentService
from app.services.stream_service import meeting_stream_broker
from infra.database.session import get_session

_MENTION_DELIMITER_RE = re.compile(r"(?=$|[\s,.;:!?，。；：！？])")
_MEETING_AI_AGENT_NAME = "AI助手"
_MEETING_GENERAL_AGENT_ID = "general_agent"
_MEETING_GENERAL_AGENT_NAME = "会议Agent"
_DEFAULT_PROJECT_ID = "default"
logger = logging.getLogger(__name__)

_ALL_DATA_DOMAINS = [
    "quality",
    "standard",
    "meeting",
    "memory",
    "platform_ops",
    "model_billing",
    "org_admin",
    "data_access",
    "security_audit",
    "ai_conversation",
]
_ROOM_TYPE_LABELS = {
    "quality_business": "质检业务会议室",
    "platform_ops": "平台运营会议室",
    "org_admin": "组织管理会议室",
    "data_ops": "数据接入会议室",
    "memory_governance": "记忆治理会议室",
    "general": "普通协作会议室",
}
_ROOM_TYPE_DOMAIN_DEFAULTS = {
    "quality_business": ["quality", "standard", "meeting", "memory"],
    "platform_ops": ["platform_ops", "model_billing", "data_access", "meeting", "memory"],
    "org_admin": ["org_admin", "security_audit", "meeting"],
    "data_ops": ["data_access", "platform_ops", "meeting", "memory"],
    "memory_governance": ["memory", "meeting", "security_audit"],
    "general": ["meeting", "memory"],
}
_ROLE_DOMAIN_ALLOW = {
    ROLE_USER: {"quality", "standard", "meeting", "memory", "ai_conversation"},
    ROLE_EXPERT: {"quality", "standard", "meeting", "memory", "ai_conversation"},
    ROLE_PLATFORM_OPERATOR: {"platform_ops", "model_billing", "data_access", "meeting", "memory", "security_audit"},
    ROLE_APP_DEVELOPER: {"platform_ops", "model_billing", "data_access", "meeting", "memory", "security_audit"},
    ROLE_ALGORITHM_ENGINEER: {"platform_ops", "model_billing", "data_access", "meeting", "memory"},
    ROLE_ADMIN: set(_ALL_DATA_DOMAINS),
}
_ROOM_QUERY_EXAMPLES = {
    "quality_business": ["前两天质检任务情况怎么样？", "这个批次有哪些待复核风险？", "这个标准版本怎么判？"],
    "platform_ops": ["当前有哪些 Agent 在运行？", "模型配置和成本情况是什么？", "最近路由失败率为什么升高？"],
    "org_admin": ["组织成员和角色有哪些？", "谁最近改过权限？", "管理员操作记录有哪些？"],
    "data_ops": ["有哪些数据源接入？", "RAG 空间同步状态如何？", "哪些连接器最近失败？"],
    "memory_governance": ["有哪些候选记忆待确认？", "共享记忆有没有冲突？", "哪些记忆需要回滚？"],
    "general": ["总结当前会议。", "提取会议待办。", "把刚才讨论整理成候选记忆。"],
}
_ROOM_GUARDRAILS = [
    "Agent 只能代用户查询其本来有权限的数据。",
    "具体事实查业务库，经验规律查记忆库。",
    "AI 会话内容是原始事件，不自动成为共享记忆。",
    "API Key、Token、密码、连接串等敏感凭据不会明文返回。",
]
_SENSITIVE_QUERY_TERMS = (
    "api key",
    "apikey",
    "secret",
    "token",
    "password",
    "passwd",
    "pwd",
    "connection string",
    "连接串",
    "密钥",
    "密码",
    "令牌",
    "私钥",
)
_CORE_CONTEXT_DOMAINS = {"meeting", "memory"}


def _is_valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


def _normalize_name(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


class MeetingService:
    def __init__(self, session: AsyncSession, org_id: str, user_id: str, role: str = ROLE_USER):
        self._session = session
        self._org_id = org_id
        self._user_id = user_id
        self._role = role or ROLE_USER
        self._repo = MeetingRepository(session)
        self._users = UserRepository(session)

    async def list_rooms(self, limit: int = 100) -> list[MeetingRoomResponse]:
        rooms = await self._repo.list_joined_rooms(self._org_id, self._user_id, limit=limit)
        return await self._serialize_rooms(rooms)

    async def create_room(
        self,
        title: str,
        password: str | None = None,
        room_type: str = "quality_business",
        visibility: str = "private",
        allowed_data_domains: list[str] | None = None,
    ) -> MeetingRoomResponse:
        clean_title = title.strip() or "会议室"
        normalized_room_type = self._normalize_room_type(room_type)
        effective_domains = self._effective_domains_for_create(normalized_room_type, allowed_data_domains)
        room = await self._repo.create_room(
            org_id=self._org_id,
            user_id=self._user_id,
            title=clean_title[:120],
            access_code=await self._generate_access_code(),
            password_hash=hash_password(password) if password else None,
            room_type=normalized_room_type,
            visibility=visibility or "private",
            allowed_data_domains=effective_domains,
            memory_policy={
                "candidate_default_scope": "meeting_room",
                "publish_requires_confirmation": True,
            },
            audit_policy={
                "enabled": True,
                "record_agent_queries": True,
                "redact_sensitive_fields": True,
            },
        )
        return (await self._serialize_rooms([room]))[0]

    async def join_room(self, access_code: str, password: str | None = None) -> MeetingRoomResponse:
        room = await self._repo.get_room_by_code(self._org_id, access_code.strip().upper())
        if not room:
            raise NotFoundError("meeting room not found")
        if str(room.status) == "archived":
            raise ForbiddenError("meeting room is archived")
        if room.password_hash and not verify_password(password or "", room.password_hash):
            raise ForbiddenError("meeting password is invalid")
        await self._repo.add_member(org_id=self._org_id, room_id=str(room.id), user_id=self._user_id)
        return (await self._serialize_rooms([room]))[0]

    async def update_room_title(self, room_id: str, title: str) -> MeetingRoomResponse:
        await self._ensure_host(room_id)
        clean_title = title.strip()
        if not clean_title:
            raise ForbiddenError("meeting room title cannot be empty")
        room = await self._repo.update_room(self._org_id, room_id, title=clean_title[:120])
        if not room:
            raise NotFoundError("meeting room not found")
        await self._publish_system_message(room_id, f"会议标题已更新为「{clean_title[:120]}」。")
        return (await self._serialize_rooms([room]))[0]

    async def update_room_settings(
        self,
        room_id: str,
        *,
        title: str | None = None,
        room_type: str | None = None,
        visibility: str | None = None,
        allowed_data_domains: list[str] | None = None,
    ) -> MeetingRoomResponse:
        await self._ensure_host(room_id)
        room = await self._repo.get_room(self._org_id, room_id)
        if not room:
            raise NotFoundError("meeting room not found")
        normalized_room_type = self._normalize_room_type(room_type or str(getattr(room, "room_type", "quality_business")))
        effective_domains = (
            self._effective_domains_for_create(normalized_room_type, allowed_data_domains)
            if allowed_data_domains is not None or room_type is not None
            else None
        )
        updated = await self._repo.update_room(
            self._org_id,
            room_id,
            title=title.strip()[:120] if title else None,
            room_type=normalized_room_type if room_type is not None else None,
            visibility=visibility,
            allowed_data_domains=effective_domains,
        )
        if not updated:
            raise NotFoundError("meeting room not found")
        await self._publish_system_message(room_id, "会议室权限边界已更新。")
        return (await self._serialize_rooms([updated]))[0]

    async def close_room(self, room_id: str) -> MeetingRoomResponse:
        await self._ensure_host(room_id)
        room = await self._repo.update_room(self._org_id, room_id, status="closed")
        if not room:
            raise NotFoundError("meeting room not found")
        await self._publish_system_message(room_id, "会议已关闭，后续消息发送已暂停。")
        return (await self._serialize_rooms([room]))[0]

    async def archive_room(self, room_id: str) -> MeetingRoomResponse:
        await self._ensure_host(room_id)
        room = await self._repo.update_room(self._org_id, room_id, status="archived")
        if not room:
            raise NotFoundError("meeting room not found")
        await self._publish_system_message(room_id, "会议已归档，可继续查看历史内容。")
        return (await self._serialize_rooms([room]))[0]

    async def list_messages(self, room_id: str, after_seq: int = 0, limit: int = 200) -> list[MeetingMessageResponse]:
        await self._ensure_member(room_id)
        messages = await self._repo.list_messages(
            org_id=self._org_id,
            room_id=room_id,
            after_seq=after_seq,
            limit=limit,
        )
        return [MeetingMessageResponse.model_validate(item) for item in messages]

    async def quote_message(
        self,
        room_id: str,
        message_id: str,
        content: str,
    ) -> MeetingMessageResponse:
        return await self.send_message(room_id, content, quote_message_id=message_id)

    async def send_message(
        self,
        room_id: str,
        content: str,
        quote_message_id: str | None = None,
        skip_agent_trigger: bool = False,
    ) -> MeetingMessageResponse:
        await self._ensure_active_member(room_id)
        user = await self._users.get_by_id(self._org_id, self._user_id)
        username = user.username if user else self._user_id[-8:]
        clean_content = content.strip()
        if quote_message_id:
            quoted = await self._repo.get_message(self._org_id, room_id, quote_message_id)
            if not quoted:
                raise NotFoundError("quoted meeting message not found")
        general_agent_mentioned = self._contains_general_agent_mention(clean_content)
        legacy_ai_alias_mentioned = not general_agent_mentioned and self._contains_meeting_ai_mention(clean_content)
        mentions = [] if (general_agent_mentioned or legacy_ai_alias_mentioned) else await self._parse_mentions(clean_content, room_id)
        general_agent_mentioned = general_agent_mentioned or legacy_ai_alias_mentioned
        stored_mentions = list(mentions)
        if general_agent_mentioned:
            stored_mentions.append({"agent_id": _MEETING_GENERAL_AGENT_ID, "agent_name": _MEETING_GENERAL_AGENT_NAME})

        message = await self._repo.create_message(
            org_id=self._org_id,
            room_id=room_id,
            user_id=self._user_id,
            username=username,
            content=clean_content,
            message_type="user",
            mentions=stored_mentions if stored_mentions else None,
            quote_message_id=quote_message_id,
        )
        response = MeetingMessageResponse.model_validate(message)

        await self._session.commit()
        await meeting_stream_broker.publish(
            room_id,
            {"event": "message_created", "room_id": room_id, "message": response.model_dump()},
        )

        if mentions:
            agent_service = MeetingAgentService()
            for mention in mentions:
                asyncio.create_task(
                    agent_service.invoke_agent(
                        room_id=room_id,
                        agent_def_id=mention["agent_id"],
                        agent_name=mention["agent_name"],
                        message_id=str(message.id),
                        query=clean_content,
                        org_id=self._org_id,
                        user_id=self._user_id,
                        username=username,
                    )
                )
        if general_agent_mentioned and not skip_agent_trigger:
            asyncio.create_task(
                self._invoke_general_agent_reply(room_id=room_id, query=clean_content)
            )
        return response

    async def start_agent_discussion(
        self,
        room_id: str,
        topic: str,
        max_agents: int = 3,
    ) -> MeetingDiscussionStartResponse:
        await self._ensure_active_member(room_id)
        user = await self._users.get_by_id(self._org_id, self._user_id)
        username = user.username if user else self._user_id[-8:]
        clean_topic = topic.strip()

        topic_message = await self._repo.create_message(
            org_id=self._org_id,
            room_id=room_id,
            user_id=self._user_id,
            username=username,
            content=clean_topic,
            message_type="user",
        )
        await self._session.commit()

        participant_count = await MeetingAgentService().start_discussion_round(
            room_id=room_id,
            org_id=self._org_id,
            user_id=self._user_id,
            username=username,
            query=clean_topic,
            max_agents=max_agents,
        )
        return MeetingDiscussionStartResponse(
            started=participant_count > 0,
            participant_count=participant_count,
            topic_message=MeetingMessageResponse.model_validate(topic_message),
        )

    async def add_agent_to_room(
        self,
        room_id: str,
        agent_id: str,
        role: str = "participant",
        allowed_domains: list[str] | None = None,
        allowed_tools: list[str] | None = None,
    ) -> MeetingRoomAgentResponse:
        await self._ensure_member(room_id)
        room = await self._repo.get_room(self._org_id, room_id)
        if not room:
            raise NotFoundError("meeting room not found")
        existing = await self._repo.get_agent(self._org_id, room_id, agent_id)
        if existing:
            raise ForbiddenError("agent is already in this meeting room")

        agent_name = await self._resolve_visible_agent_name(agent_id)
        effective_domains = self._agent_allowed_domains(room, allowed_domains)
        row = await self._repo.add_agent(
            org_id=self._org_id,
            room_id=room_id,
            agent_id=agent_id,
            added_by=self._user_id,
            role=role,
            allowed_domains=effective_domains,
            allowed_tools=self._normalize_tool_list(allowed_tools),
        )
        return self._serialize_agent_row(row, agent_name=agent_name)

    async def remove_agent_from_room(self, room_id: str, agent_id: str) -> None:
        await self._ensure_member(room_id)
        removed = await self._repo.remove_agent(self._org_id, room_id, agent_id)
        if not removed:
            raise NotFoundError("agent not found in this meeting room")

    async def list_room_agents(self, room_id: str) -> list[MeetingRoomAgentResponse]:
        await self._ensure_member(room_id)
        rows = await self._repo.get_agents(self._org_id, room_id)
        results: list[MeetingRoomAgentResponse] = []
        for row in rows:
            agent_id = str(row.agent_id)
            agent_name = await self._resolve_visible_agent_name(agent_id)
            results.append(self._serialize_agent_row(row, agent_name=agent_name))
        return results

    async def list_room_members(self, room_id: str) -> list[MeetingRoomMemberResponse]:
        await self._ensure_member(room_id)
        rows = await self._repo.list_members(self._org_id, room_id)
        return [await self._serialize_member(row) for row in rows]

    async def update_member_role(
        self,
        room_id: str,
        member_user_id: str,
        role: str,
    ) -> MeetingRoomMemberResponse:
        room = await self._repo.get_room(self._org_id, room_id)
        if not room:
            raise NotFoundError("meeting room not found")
        if str(room.created_by) != self._user_id:
            raise ForbiddenError("only the meeting creator can assign member permissions")
        if str(member_user_id) == str(room.created_by) and role != "host":
            raise ForbiddenError("the meeting creator must remain a host")
        row = await self._repo.update_member_role(self._org_id, room_id, member_user_id, role)
        if row is None:
            raise NotFoundError("meeting member not found")
        await self._publish_system_message(
            room_id,
            f"成员「{(await self._serialize_member(row)).username}」已设为{self._member_role_label(role)}。",
        )
        return await self._serialize_member(row)

    async def delete_room(self, room_id: str) -> None:
        room = await self._repo.get_room(self._org_id, room_id)
        if not room:
            raise NotFoundError("meeting room not found")
        if str(room.created_by) != self._user_id:
            raise ForbiddenError("only the meeting host can delete the room")
        await self._repo.delete_room_admin(self._org_id, room_id)

    async def get_room_detail(self, room_id: str) -> MeetingRoomDetailResponse:
        await self._ensure_member(room_id)
        from app.services.meeting_admin_service import MeetingAdminService

        admin_svc = MeetingAdminService(self._session, self._org_id)
        return await admin_svc.get_room_detail(room_id)

    async def get_context_preview(self, room_id: str) -> MeetingContextPreviewResponse:
        room = await self._repo.get_room(self._org_id, room_id)
        if not room:
            raise NotFoundError("meeting room not found")
        member = await self._repo.get_member(self._org_id, room_id, self._user_id)
        if not member:
            raise ForbiddenError("join the meeting room before viewing context")

        allowed_domains = self._effective_domains_for_room(room)
        denied_domains = [domain for domain in _ALL_DATA_DOMAINS if domain not in allowed_domains]
        agent_rows = await self._repo.get_agents(self._org_id, room_id)
        agent_permissions: list[dict[str, Any]] = []
        for row in agent_rows:
            agent_id = str(row.agent_id)
            agent_permissions.append(
                {
                    "agent_id": agent_id,
                    "agent_name": await self._resolve_visible_agent_name(agent_id),
                    "role": str(row.role),
                    "allowed_domains": self._agent_allowed_domains(room, getattr(row, "allowed_domains", None)),
                    "allowed_tools": self._normalize_tool_list(getattr(row, "allowed_tools", None)),
                }
            )

        room_type = self._normalize_room_type(str(getattr(room, "room_type", "quality_business")))
        return MeetingContextPreviewResponse(
            room_id=room_id,
            room_type=room_type,
            room_type_label=_ROOM_TYPE_LABELS.get(room_type, room_type),
            user_role=self._role,
            room_role=str(getattr(member, "role", "member") or "member"),
            allowed_domains=allowed_domains,
            denied_domains=denied_domains,
            agent_permissions=agent_permissions,
            query_examples=list(_ROOM_QUERY_EXAMPLES.get(room_type) or _ROOM_QUERY_EXAMPLES["general"]),
            guardrails=list(_ROOM_GUARDRAILS),
        )

    async def list_agent_query_audits(self, room_id: str, limit: int = 50) -> list[MeetingAgentQueryAuditResponse]:
        await self._ensure_host(room_id)
        rows = await self._repo.list_agent_query_audits(org_id=self._org_id, room_id=room_id, limit=limit)
        return [self._serialize_agent_query_audit(row) for row in rows]

    async def run_general_agent(
        self,
        room_id: str,
        request: MeetingAgentRunRequest,
    ) -> MeetingAgentRunResponse:
        await self._ensure_member(room_id)
        room = await self._repo.get_room(self._org_id, room_id)
        if not room:
            raise NotFoundError("meeting room not found")
        workflow_run_id = str(uuid7())
        agent_message_id = str(uuid7())
        await meeting_stream_broker.publish(
            room_id,
            {
                "event": "agent_run_started",
                "room_id": room_id,
                "message_id": agent_message_id,
                "agent_id": _MEETING_GENERAL_AGENT_ID,
                "agent_name": _MEETING_GENERAL_AGENT_NAME,
                "workflow_run_id": workflow_run_id,
            },
        )

        try:
            selected_subgraph = self._select_general_agent_subgraph(request.query, request.mode)
            if selected_subgraph == "agent_manager":
                return await self._run_agent_manager_for_meeting(room_id, request, room=room)

            memory_sources: list[MeetingMemorySourceResponse] = []
            recent_messages: list[Any] = []
            memory_sources = await self._collect_memory_sources(room_id, request.memory_scope)
            recent_messages = await self._repo.list_recent_messages(
                org_id=self._org_id,
                room_id=room_id,
                limit=80,
            )
            answer = self._build_general_agent_answer(
                selected_subgraph=selected_subgraph,
                query=request.query,
                messages=recent_messages,
                memory_sources=memory_sources,
            )
            candidate_memories: list[MeetingCandidateMemoryResponse] = []
            if selected_subgraph in {"meeting_summary", "memory_transfer"}:
                candidate_memories = await self._extract_candidate_memories_from_messages(
                    room_id,
                    max_items=2 if selected_subgraph == "meeting_summary" else 3,
                    topic=request.query,
                )

            message = await self._repo.create_message(
                org_id=self._org_id,
                room_id=room_id,
                user_id=self._user_id,
                username=_MEETING_GENERAL_AGENT_NAME,
                content=answer,
                message_type="agent",
                agent_id=_MEETING_GENERAL_AGENT_ID,
                metadata_json={
                    "selected_subgraph": selected_subgraph,
                    "memory_sources": [item.model_dump(mode="json") for item in memory_sources],
                    "candidate_memories": [item.model_dump(mode="json") for item in candidate_memories],
                },
            )
            response_message = MeetingMessageResponse.model_validate(message)
            await self._record_agent_query_audit(
                room=room,
                question=request.query,
                intent=selected_subgraph,
                source_refs=[
                    {"type": "meeting_message", "id": str(message.id)},
                    *[
                        {"type": "memory", "id": item.memory_id, "scope": item.scope}
                        for item in memory_sources
                    ],
                ],
                tool_calls=[],
            )
            await self._session.commit()
            await meeting_stream_broker.publish(
                room_id,
                {"event": "message_created", "room_id": room_id, "message": response_message.model_dump()},
            )
            return MeetingAgentRunResponse(
                selected_subgraph=selected_subgraph,
                answer=answer,
                message=response_message,
                memory_sources=memory_sources,
                candidate_memories=candidate_memories,
            )
        except Exception as exc:
            await meeting_stream_broker.publish(
                room_id,
                {
                    "event": "agent_run_failed",
                    "room_id": room_id,
                    "message_id": agent_message_id,
                    "agent_id": _MEETING_GENERAL_AGENT_ID,
                    "agent_name": _MEETING_GENERAL_AGENT_NAME,
                    "workflow_run_id": workflow_run_id,
                    "error": str(exc) or exc.__class__.__name__,
                },
            )
            raise

    async def list_room_memories(self, room_id: str) -> list[MeetingMemoryResponse]:
        await self._ensure_member(room_id)
        items = await self._repo.list_memory_items_for_room(
            org_id=self._org_id,
            room_id=room_id,
            project_id=_DEFAULT_PROJECT_ID,
            include_project_shared=True,
            statuses=["candidate", "active"],
            limit=100,
        )
        return [self._serialize_memory_item(item, room_id=room_id) for item in items]

    async def extract_memories(
        self,
        room_id: str,
        request: MeetingMemoryExtractRequest,
    ) -> list[MeetingCandidateMemoryResponse]:
        await self._ensure_host(room_id)
        return await self._extract_candidate_memories_from_messages(
            room_id,
            max_items=request.max_items,
            topic=request.topic or "",
        )

    async def confirm_memory(
        self,
        memory_id: str,
        request: MeetingMemoryUpdateRequest | None = None,
    ) -> MeetingMemoryResponse:
        item = await self._repo.get_memory_item(self._org_id, memory_id)
        if item is None:
            raise NotFoundError("meeting memory not found")
        room_id = self._memory_room_id(item)
        if not room_id:
            raise ForbiddenError("memory is not sourced from a meeting room")
        await self._ensure_host(room_id)

        content_json = dict(item.content_json or {})
        if request and request.title:
            content_json["title"] = request.title.strip()
        if request and request.content:
            content_json["content"] = request.content.strip()
        content_json["confirmed_by"] = self._user_id
        content_json["confirmed_at"] = datetime.utcnow().isoformat()
        content_json["recommended_scope"] = (request.scope if request else None) or "project_shared"
        content = str(content_json.get("content") or item.content_summary or "")
        updated = await self._repo.update_memory_item(
            org_id=self._org_id,
            memory_id=memory_id,
            status="active",
            content_summary=content[:1000],
            content_json=content_json,
        )
        await self._repo.create_memory_scope_binding(
            org_id=self._org_id,
            memory_id=memory_id,
            scope_type="project",
            scope_id=str(content_json.get("project_id") or _DEFAULT_PROJECT_ID),
            permission="read",
            created_by=self._user_id,
        )
        await self._repo.create_memory_transfer_log(
            org_id=self._org_id,
            memory_id=memory_id,
            from_scope_type="meeting_room",
            from_scope_id=room_id,
            to_scope_type="project",
            to_scope_id=str(content_json.get("project_id") or _DEFAULT_PROJECT_ID),
            transfer_reason="会议候选记忆经用户确认后发布为项目共享记忆",
            status="confirmed",
            operator_id=self._user_id,
        )
        await self._publish_system_message(room_id, f"候选记忆「{content_json.get('title') or '会议记忆'}」已确认并发布为项目共享记忆。")
        return self._serialize_memory_item(updated or item, room_id=room_id)

    async def reject_memory(self, memory_id: str) -> MeetingMemoryResponse:
        item = await self._repo.get_memory_item(self._org_id, memory_id)
        if item is None:
            raise NotFoundError("meeting memory not found")
        room_id = self._memory_room_id(item)
        if not room_id:
            raise ForbiddenError("memory is not sourced from a meeting room")
        await self._ensure_host(room_id)
        updated = await self._repo.update_memory_item(
            org_id=self._org_id,
            memory_id=memory_id,
            status="rejected",
        )
        await self._repo.create_memory_transfer_log(
            org_id=self._org_id,
            memory_id=memory_id,
            from_scope_type="meeting_room",
            from_scope_id=room_id,
            to_scope_type="project",
            to_scope_id=_DEFAULT_PROJECT_ID,
            transfer_reason="用户拒绝候选记忆",
            status="rejected",
            operator_id=self._user_id,
        )
        await self._publish_system_message(room_id, "一条候选记忆已被拒绝。")
        return self._serialize_memory_item(updated or item, room_id=room_id)

    async def transfer_memory(
        self,
        memory_id: str,
        request: MeetingMemoryTransferRequest,
    ) -> MeetingMemoryResponse:
        item = await self._repo.get_memory_item(self._org_id, memory_id)
        if item is None:
            raise NotFoundError("meeting memory not found")
        room_id = self._memory_room_id(item)
        if room_id:
            await self._ensure_member(room_id)
        await self._repo.create_memory_scope_binding(
            org_id=self._org_id,
            memory_id=memory_id,
            scope_type=request.to_scope_type,
            scope_id=request.to_scope_id,
            permission="read",
            created_by=self._user_id,
        )
        await self._repo.create_memory_transfer_log(
            org_id=self._org_id,
            memory_id=memory_id,
            from_scope_type="meeting_room",
            from_scope_id=room_id or "unknown",
            to_scope_type=request.to_scope_type,
            to_scope_id=request.to_scope_id,
            transfer_reason=request.transfer_reason,
            status="confirmed",
            operator_id=self._user_id,
        )
        return self._serialize_memory_item(item, room_id=room_id or "")

    async def list_action_items(self, room_id: str) -> list[MeetingActionItemResponse]:
        await self._ensure_member(room_id)
        rows = await self._repo.list_action_items(self._org_id, room_id)
        return [await self._serialize_action_item(row) for row in rows]

    async def create_action_item(
        self,
        room_id: str,
        request: MeetingActionItemCreateRequest,
    ) -> MeetingActionItemResponse:
        await self._ensure_member(room_id)
        if request.source_message_id:
            message = await self._repo.get_message(self._org_id, room_id, request.source_message_id)
            if message is None:
                raise NotFoundError("source meeting message not found")
        row = await self._repo.create_action_item(
            org_id=self._org_id,
            room_id=room_id,
            title=request.title.strip(),
            description=request.description,
            owner_id=request.owner_id,
            due_at=request.due_at,
            source_message_id=request.source_message_id,
            created_by=self._user_id,
        )
        await self._publish_system_message(room_id, f"已新增会议待办：{row.title}")
        return await self._serialize_action_item(row)

    async def update_action_item(
        self,
        action_item_id: str,
        request: MeetingActionItemUpdateRequest,
    ) -> MeetingActionItemResponse:
        row = await self._repo.get_action_item(self._org_id, action_item_id)
        if row is None:
            raise NotFoundError("meeting action item not found")
        await self._ensure_member(str(row.room_id))
        updated = await self._repo.update_action_item(
            self._org_id,
            action_item_id,
            title=request.title.strip() if request.title else None,
            description=request.description,
            owner_id=request.owner_id,
            due_at=request.due_at,
            status=request.status,
        )
        return await self._serialize_action_item(updated or row)

    async def complete_action_item(self, action_item_id: str) -> MeetingActionItemResponse:
        row = await self._repo.get_action_item(self._org_id, action_item_id)
        if row is None:
            raise NotFoundError("meeting action item not found")
        await self._ensure_member(str(row.room_id))
        updated = await self._repo.update_action_item(self._org_id, action_item_id, status="done")
        await self._publish_system_message(str(row.room_id), f"会议待办已完成：{row.title}")
        return await self._serialize_action_item(updated or row)

    async def _ensure_member(self, room_id: str) -> None:
        room = await self._repo.get_room(self._org_id, room_id)
        if not room:
            raise NotFoundError("meeting room not found")
        member = await self._repo.get_member(self._org_id, room_id, self._user_id)
        if not member:
            raise ForbiddenError("join the meeting room before sending messages")

    async def _ensure_active_member(self, room_id: str) -> None:
        room = await self._repo.get_room(self._org_id, room_id)
        if not room:
            raise NotFoundError("meeting room not found")
        member = await self._repo.get_member(self._org_id, room_id, self._user_id)
        if not member:
            raise ForbiddenError("join the meeting room before sending messages")
        if str(getattr(room, "status", "active")) != "active":
            raise ForbiddenError("meeting room is not active")

    async def _ensure_host(self, room_id: str) -> None:
        room = await self._repo.get_room(self._org_id, room_id)
        if not room:
            raise NotFoundError("meeting room not found")
        member = await self._repo.get_member(self._org_id, room_id, self._user_id)
        if not member:
            raise ForbiddenError("join the meeting room before managing it")
        if str(room.created_by) != self._user_id and str(member.role) != "host":
            raise ForbiddenError("only the meeting host can manage the room")

    async def _publish_system_message(self, room_id: str, content: str) -> MeetingMessageResponse:
        message = await self._repo.create_message(
            org_id=self._org_id,
            room_id=room_id,
            user_id=self._user_id,
            username="系统",
            content=content,
            message_type="system",
        )
        response = MeetingMessageResponse.model_validate(message)
        await meeting_stream_broker.publish(
            room_id,
            {"event": "message_created", "room_id": room_id, "message": response.model_dump()},
        )
        return response

    async def _serialize_member(self, row: Any) -> MeetingRoomMemberResponse:
        user_id = str(row.user_id)
        user = await self._users.get_by_id(self._org_id, user_id)
        return MeetingRoomMemberResponse(
            id=str(row.id),
            room_id=str(row.room_id),
            user_id=user_id,
            username=user.username if user else user_id[-8:],
            role=str(row.role),
            joined_at=row.created_at,
        )

    @staticmethod
    def _member_role_label(role: str) -> str:
        return "主持人" if role == "host" else "成员"

    def _select_general_agent_subgraph(self, query: str, mode: str) -> str:
        if mode != "auto":
            return "action_items" if mode == "action_items" else mode
        normalized = query.lower()
        compact = _normalize_name(query)
        intro_phrases = (
            "你会干什么",
            "你能做什么",
            "你会做什么",
            "你可以做什么",
            "能干什么",
            "有什么功能",
            "介绍一下",
        )
        if any(phrase in normalized or phrase in compact for phrase in intro_phrases):
            return "capability_intro"
        if any(word in normalized for word in ("总结", "纪要", "归纳", "小结", "summary", "summarize")):
            return "meeting_summary"
        if any(word in normalized for word in ("记忆", "沉淀", "共享", "transfer", "memory")):
            return "memory_transfer"
        if any(word in normalized for word in ("行动项", "待办", "todo", "action")):
            return "action_items"
        return "agent_manager"

    async def _run_agent_manager_for_meeting(
        self,
        room_id: str,
        request: MeetingAgentRunRequest,
        *,
        room: Any | None = None,
    ) -> MeetingAgentRunResponse:
        room = room or await self._repo.get_room(self._org_id, room_id)
        if not room:
            raise NotFoundError("meeting room not found")
        recent_messages = await self._repo.list_recent_messages(
            org_id=self._org_id,
            room_id=room_id,
            limit=24,
        )
        room_type = self._normalize_room_type(str(getattr(room, "room_type", "quality_business") or "quality_business"))
        allowed_domains = self._effective_domains_for_room(room)
        query = self._clean_general_agent_query(request.query)
        payload = {
            "request_id": str(uuid7()),
            "workflow_run_id": str(uuid7()),
            "session_id": f"meeting:{room_id}",
            "assistant_message_id": str(uuid7()),
            "org_id": self._org_id,
            "user_id": self._user_id,
            "workspace": "meeting_room",
            "plan_tier": "basic",
            "capabilities": [],
            "query": query,
            "metadata": {
                "source": "meeting_room",
                "room_id": room_id,
                "project_id": _DEFAULT_PROJECT_ID,
                "meeting_agent_name": _MEETING_GENERAL_AGENT_NAME,
                "room_type": room_type,
                "allowed_data_domains": allowed_domains,
            },
            "ext": {
                "surface": "chat",
                "allowed_modes": ["answer", "report"],
                "forbidden_modes": ["action"],
                "history_messages": self._meeting_history_messages(recent_messages),
                "inspection_context": await self._build_meeting_inspection_context(),
                "meeting_context": {
                    "room_id": room_id,
                    "room_type": room_type,
                    "project_id": _DEFAULT_PROJECT_ID,
                    "allowed_data_domains": allowed_domains,
                    "denied_data_domains": [domain for domain in _ALL_DATA_DOMAINS if domain not in allowed_domains],
                    "recent_messages": self._meeting_context_messages(recent_messages),
                    "project_binding": "unbound",
                },
            },
            "attachments": [],
            "image_urls": [],
        }
        router_output = await AgentManagerService().run_chat(payload, db_session=self._session)
        route_decision = router_output.route_decision
        agent_output = dict(router_output.agent_output or {})
        answer = self._agent_manager_answer(agent_output, router_output.status)
        selected_subgraph = str(route_decision.sub_route or "general_chat")
        message = await self._repo.create_message(
            org_id=self._org_id,
            room_id=room_id,
            user_id=self._user_id,
            username=_MEETING_GENERAL_AGENT_NAME,
            content=answer,
            message_type="agent",
            agent_id=_MEETING_GENERAL_AGENT_ID,
            metadata_json={
                "selected_subgraph": selected_subgraph,
                "route_source": "agent_manager",
                "selected_agent": route_decision.selected_agent,
                "route_decision": route_decision.model_dump(mode="json"),
                "manager_status": router_output.status,
                "degrade_reason": router_output.degrade_reason,
                "capabilities_used": list(agent_output.get("capabilities_used") or []),
                "message_type": agent_output.get("message_type"),
                "trace_id": agent_output.get("trace_id"),
                "trace_url": agent_output.get("trace_url"),
                "citations": list(agent_output.get("citations") or []),
                "rag_summary": agent_output.get("rag_summary"),
            },
        )
        response_message = MeetingMessageResponse.model_validate(message)
        await self._record_agent_query_audit(
            room=room,
            question=request.query,
            intent=selected_subgraph,
            source_refs=[
                {"type": "meeting_message", "id": str(message.id)},
                *[
                    {"type": "citation", **citation}
                    for citation in list(agent_output.get("citations") or [])
                    if isinstance(citation, dict)
                ],
            ],
            tool_calls=[
                {"name": str(item), "source": "agent_manager"}
                for item in list(agent_output.get("capabilities_used") or [])
            ],
        )
        await self._session.commit()
        await meeting_stream_broker.publish(
            room_id,
            {"event": "message_created", "room_id": room_id, "message": response_message.model_dump()},
        )
        return MeetingAgentRunResponse(
            selected_subgraph=selected_subgraph,
            answer=answer,
            message=response_message,
            memory_sources=[],
            candidate_memories=[],
        )

    async def _build_meeting_inspection_context(self) -> dict[str, Any]:
        try:
            user = await self._users.get_by_id(self._org_id, self._user_id)
            role = str(getattr(user, "role", "") or ROLE_USER)
            return await ChatContextService(
                self._session,
                org_id=self._org_id,
                user_id=self._user_id,
                role=role,
            ).build_inspection_context(recent_limit=6, summary_window=12)
        except Exception:
            logger.debug("meeting inspection context build skipped", exc_info=True)
            return {}

    @staticmethod
    def _agent_manager_answer(agent_output: dict[str, Any], status: str) -> str:
        answer = str(agent_output.get("answer") or agent_output.get("summary") or "").strip()
        if answer:
            return answer
        if status == "blocked":
            return "当前请求被页面边界阻止：会议室只能做只读问答和上下文整理，不能直接创建或执行正式质检任务。"
        if status == "failed":
            return "会议Agent这次没有生成有效回复，请稍后重试。"
        return "我已收到你的请求，但当前没有生成有效回复。"

    @staticmethod
    def _meeting_history_messages(messages: list[Any]) -> list[dict[str, str]]:
        history: list[dict[str, str]] = []
        for message in messages[-12:]:
            content = str(getattr(message, "content", "") or "").strip()
            if not content:
                continue
            message_type = str(getattr(message, "message_type", "user") or "user")
            role = "assistant" if message_type in {"agent", "agent_streaming", "summary", "system"} else "user"
            username = str(getattr(message, "username", "") or "").strip()
            history.append({"role": role, "content": f"{username}: {content}"[:1200] if username else content[:1200]})
        return history

    @staticmethod
    def _meeting_context_messages(messages: list[Any]) -> list[dict[str, Any]]:
        context: list[dict[str, Any]] = []
        for message in messages[-12:]:
            content = str(getattr(message, "content", "") or "").strip()
            if not content:
                continue
            context.append(
                {
                    "seq_no": int(getattr(message, "seq_no", 0) or 0),
                    "username": str(getattr(message, "username", "") or ""),
                    "message_type": str(getattr(message, "message_type", "") or ""),
                    "content": content[:1200],
                }
            )
        return context

    @staticmethod
    def _clean_general_agent_query(query: str) -> str:
        cleaned = str(query or "").strip()
        mention_pattern = re.compile(
            r"@\s*(会议\s*Agent|AI\s*助手|智能助手|总\s*Agent|总智能体|agent|general\s*agent)",
            re.IGNORECASE,
        )
        cleaned = mention_pattern.sub("", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ，。；:：")
        return cleaned or str(query or "").strip()

    async def _collect_memory_sources(
        self,
        room_id: str,
        scope: MeetingMemoryScopeRequest,
    ) -> list[MeetingMemorySourceResponse]:
        if not scope.include_project_shared:
            return []
        items = await self._repo.list_memory_items_for_room(
            org_id=self._org_id,
            room_id=room_id,
            project_id=_DEFAULT_PROJECT_ID,
            include_project_shared=True,
            statuses=["active"],
            limit=5,
        )
        sources: list[MeetingMemorySourceResponse] = []
        for item in items:
            content_json = item.content_json or {}
            title = str(content_json.get("title") or item.content_summary or item.memory_id)
            sources.append(
                MeetingMemorySourceResponse(
                    memory_id=str(item.memory_id),
                    scope=str(content_json.get("recommended_scope") or "project_shared"),
                    title=title,
                    summary=str(item.content_summary or ""),
                )
            )
        return sources

    def _build_general_agent_answer(
        self,
        *,
        selected_subgraph: str,
        query: str,
        messages: list[Any],
        memory_sources: list[MeetingMemorySourceResponse],
    ) -> str:
        user_messages = [
            str(msg.content).strip()
            for msg in messages
            if str(getattr(msg, "content", "")).strip()
            and str(getattr(msg, "message_type", "user")) in {"user", "system"}
        ]
        recent = user_messages[-8:]
        source_lines = "\n".join(f"- {item.title}: {item.summary}" for item in memory_sources[:5])
        if selected_subgraph == "capability_intro":
            return (
                "我是会议Agent，负责在这个会议室里把讨论内容整理成可执行、可追溯的结果。\n\n"
                "我现在可以做这些事：\n"
                "1. 回答你在会议里点名提出的问题。\n"
                "2. 基于当前会议内容生成会议纪要。\n"
                "3. 从讨论中提取候选记忆，等你确认后再发布为项目共享记忆。\n"
                "4. 整理会议待办线索，辅助分配责任人和后续跟进。\n"
                "5. 根据会议上下文做检测风险、检测证据、标准解释的讨论型整理。\n\n"
                "当前版本还没有真正绑定项目和质检任务，所以我不会自动知道全部质检任务；需要你在会议里提到产品、批次、任务，或后续接入结构化绑定。"
            )
        if selected_subgraph == "risk_forecast":
            return (
                "我先基于会议上下文和已确认共享记忆给出讨论型预测建议：\n"
                "1. 优先关注会议中被反复提及的产品、批次和缺陷类型。\n"
                "2. 对缺少检测任务或结果来源的结论标记为待核验。\n"
                "3. 后续接入 inspection_tasks / inspection_results 后，可补充分数化风险排序。\n\n"
                f"本次查询：{query}\n"
                f"可用共享记忆：\n{source_lines or '- 暂无已确认共享记忆'}"
            )
        if selected_subgraph == "evidence_query":
            return (
                "我会先从会议上下文中定位产品、批次、任务 ID 等线索；真正的检测证据列表需要后续接入检测任务与结果表。\n\n"
                f"本次查询：{query}\n"
                f"会议线索：\n{self._bullet_recent(recent)}"
            )
        if selected_subgraph == "standard_explain":
            return (
                "我会把会议中的判定争议、标准名和缺陷描述整理为待解释问题；接入 RAG 标准条款后可返回具体引用依据。\n\n"
                f"本次查询：{query}\n"
                f"相关上下文：\n{self._bullet_recent(recent)}"
            )
        if selected_subgraph == "memory_transfer":
            return (
                "我已根据会议内容生成候选记忆，等待用户确认后才会发布为项目共享记忆；原始会议聊天不会跨会议共享。\n\n"
                f"候选依据：\n{self._bullet_recent(recent[-5:])}"
            )
        if selected_subgraph == "action_items":
            return (
                "建议把会议中的明确责任、截止时间和复核要求拆成会议待办；右侧面板可以继续新增、更新和完成。\n\n"
                f"可提取线索：\n{self._bullet_recent(recent[-5:])}"
            )
        return (
            "下面是基于当前会议上下文的第一版整理：\n\n"
            f"核心讨论：\n{self._bullet_recent(recent)}\n\n"
            f"已确认共享记忆：\n{source_lines or '- 暂无'}\n\n"
            "可沉淀内容已生成候选记忆，请在右侧面板确认后再发布为项目共享记忆。"
        )

    @staticmethod
    def _bullet_recent(items: list[str]) -> str:
        if not items:
            return "- 暂无足够会议上下文"
        return "\n".join(f"- {item[:160]}" for item in items)

    async def _extract_candidate_memories_from_messages(
        self,
        room_id: str,
        *,
        max_items: int,
        topic: str = "",
    ) -> list[MeetingCandidateMemoryResponse]:
        messages = await self._repo.list_recent_messages(
            org_id=self._org_id,
            room_id=room_id,
            limit=80,
        )
        candidate_lines = self._candidate_lines_from_messages(messages, topic=topic, max_items=max_items)
        results: list[MeetingCandidateMemoryResponse] = []
        existing = await self._repo.list_memory_items_for_room(
            org_id=self._org_id,
            room_id=room_id,
            project_id=_DEFAULT_PROJECT_ID,
            include_project_shared=False,
            statuses=["candidate"],
            limit=100,
        )
        existing_summaries = {str(item.content_summary or "").strip() for item in existing}
        for index, line in enumerate(candidate_lines, 1):
            if line in existing_summaries:
                continue
            memory_id = f"mem_meeting_{uuid.uuid4().hex[:12]}"
            title = self._memory_title_from_line(line, index)
            source_message_id = self._latest_user_message_id(messages)
            item = MemoryItem(
                id=str(uuid7()),
                memory_id=memory_id,
                org_id=self._org_id,
                user_id=None,
                workspace="app",
                memory_type="task_episode",
                scope_json={"meeting_room_id": room_id, "project_id": _DEFAULT_PROJECT_ID},
                content_summary=line,
                content_json={
                    "title": title,
                    "content": line,
                    "memory_type": "decision",
                    "recommended_scope": "project_shared",
                    "source_type": "meeting",
                    "source_id": room_id,
                    "source_message_id": source_message_id,
                    "project_id": _DEFAULT_PROJECT_ID,
                },
                source_event_ids=[source_message_id] if source_message_id else None,
                evidence_pointers={"meeting_room_id": room_id, "source_message_id": source_message_id},
                trust_score=0.65,
                confidence=0.65,
                visibility_scope={"meeting_room_id": room_id},
                usage_policy="context_only",
                ttl_policy="never",
                privacy_level="tenant_private",
                status="candidate",
                created_by=self._user_id,
                created_by_type="agent",
                trace_id=f"meeting:{room_id}:{memory_id}",
                expires_at=None,
            )
            await self._repo.create_memory_item(item)
            await self._repo.create_memory_scope_binding(
                org_id=self._org_id,
                memory_id=memory_id,
                scope_type="meeting_room",
                scope_id=room_id,
                permission="confirm",
                created_by=self._user_id,
            )
            await self._repo.create_memory_transfer_log(
                org_id=self._org_id,
                memory_id=memory_id,
                from_scope_type="meeting_room",
                from_scope_id=room_id,
                to_scope_type="project",
                to_scope_id=_DEFAULT_PROJECT_ID,
                transfer_reason="会议Agent从会议上下文提取候选记忆",
                status="candidate",
                operator_id=self._user_id,
            )
            results.append(
                MeetingCandidateMemoryResponse(
                    memory_id=memory_id,
                    title=title,
                    content=line,
                    summary=line,
                    memory_type="decision",
                    status="candidate",
                    recommended_scope="project_shared",
                    confidence=0.65,
                    source_message_id=source_message_id,
                    created_at=item.created_at,
                )
            )
        return results

    @staticmethod
    def _candidate_lines_from_messages(messages: list[Any], *, topic: str, max_items: int) -> list[str]:
        keywords = ("确认", "结论", "决定", "风险", "需要", "建议", "复核", "行动", "待办", "标准", "检测")
        lines: list[str] = []
        for msg in reversed(messages):
            if str(getattr(msg, "message_type", "user")) not in {"user", "summary", "action_item"}:
                continue
            content = re.sub(r"\s+", " ", str(getattr(msg, "content", "")).strip())
            if not content or content.startswith("@"):
                continue
            if any(keyword in content for keyword in keywords) or (topic and topic[:12] in content):
                lines.append(content[:260])
            if len(lines) >= max_items:
                break
        if not lines:
            compact = "；".join(
                re.sub(r"\s+", " ", str(getattr(msg, "content", "")).strip())[:120]
                for msg in messages[-5:]
                if str(getattr(msg, "content", "")).strip()
            )
            if compact:
                lines.append(f"会议形成待确认结论：{compact[:260]}")
        return list(reversed(lines[:max_items]))

    @staticmethod
    def _memory_title_from_line(line: str, index: int) -> str:
        compact = re.sub(r"[。！？；;,.，\s]+", " ", line).strip()
        return (compact[:36] or f"会议候选记忆 {index}").strip()

    @staticmethod
    def _latest_user_message_id(messages: list[Any]) -> str | None:
        for msg in reversed(messages):
            if str(getattr(msg, "message_type", "")) == "user":
                return str(getattr(msg, "id", "") or "") or None
        return None

    def _serialize_memory_item(self, item: MemoryItem, *, room_id: str) -> MeetingMemoryResponse:
        content_json = item.content_json or {}
        return MeetingMemoryResponse(
            memory_id=str(item.memory_id),
            title=str(content_json.get("title") or item.content_summary or item.memory_id),
            content=str(content_json.get("content") or item.content_summary or ""),
            summary=str(item.content_summary or ""),
            memory_type=str(content_json.get("memory_type") or item.memory_type),
            status=str(item.status),
            scope=str(content_json.get("recommended_scope") or ("meeting" if str(item.status) == "candidate" else "project_shared")),
            confidence=float(item.confidence) if item.confidence is not None else None,
            source_message_id=content_json.get("source_message_id"),
            created_by=str(item.created_by) if item.created_by else None,
            confirmed_by=content_json.get("confirmed_by"),
            confirmed_at=self._parse_datetime(content_json.get("confirmed_at")),
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    @staticmethod
    def _memory_room_id(item: MemoryItem) -> str | None:
        scope_json = item.scope_json or {}
        content_json = item.content_json or {}
        return str(scope_json.get("meeting_room_id") or content_json.get("source_id") or "") or None

    @staticmethod
    def _normalize_room_type(value: str | None) -> str:
        room_type = str(value or "quality_business").strip()
        return room_type if room_type in _ROOM_TYPE_DOMAIN_DEFAULTS else "quality_business"

    @staticmethod
    def _ordered_domains(domains: set[str] | list[str] | tuple[str, ...]) -> list[str]:
        domain_set = set(domains)
        return [domain for domain in _ALL_DATA_DOMAINS if domain in domain_set]

    @staticmethod
    def _normalize_domain_list(values: Any) -> list[str]:
        if values is None:
            return []
        if isinstance(values, str):
            raw_values = re.split(r"[\s,，;；]+", values)
        elif isinstance(values, (list, tuple, set)):
            raw_values = list(values)
        else:
            return []

        seen: set[str] = set()
        result: list[str] = []
        valid_domains = set(_ALL_DATA_DOMAINS)
        for value in raw_values:
            domain = str(value or "").strip()
            if not domain or domain not in valid_domains or domain in seen:
                continue
            seen.add(domain)
            result.append(domain)
        return result

    def _role_allowed_domains(self) -> set[str]:
        role = str(self._role or ROLE_USER)
        if role in _ROLE_DOMAIN_ALLOW:
            return set(_ROLE_DOMAIN_ALLOW[role])
        if role in {"member", "quality_operator"}:
            return {"quality", "standard", "meeting", "memory", "ai_conversation"}
        if role in {"quality_expert", "quality_manager"}:
            return {"quality", "standard", "meeting", "memory", "security_audit", "ai_conversation"}
        if role == "platform_operator":
            return set(_ROLE_DOMAIN_ALLOW[ROLE_PLATFORM_OPERATOR])
        if role == "org_admin":
            return {"org_admin", "security_audit", "meeting", "memory", "ai_conversation"}
        return set(_ROLE_DOMAIN_ALLOW[ROLE_USER])

    def _room_default_domains(self, room_type: str) -> list[str]:
        normalized = self._normalize_room_type(room_type)
        return list(_ROOM_TYPE_DOMAIN_DEFAULTS.get(normalized) or _ROOM_TYPE_DOMAIN_DEFAULTS["quality_business"])

    def _effective_domains_for_create(self, room_type: str, requested: list[str] | None) -> list[str]:
        role_allowed = self._role_allowed_domains()
        requested_domains = self._normalize_domain_list(requested)
        base_domains = set(requested_domains or self._room_default_domains(room_type))
        effective = base_domains & role_allowed
        if "meeting" in role_allowed:
            effective.add("meeting")
        if not effective and "memory" in role_allowed:
            effective.add("memory")
        return self._ordered_domains(effective)

    def _effective_domains_for_room(self, room: Any) -> list[str]:
        room_type = self._normalize_room_type(str(getattr(room, "room_type", "quality_business") or "quality_business"))
        stored_domains = self._normalize_domain_list(getattr(room, "allowed_data_domains", None))
        role_allowed = self._role_allowed_domains()
        effective = set(stored_domains or self._room_default_domains(room_type)) & role_allowed
        if "meeting" in role_allowed:
            effective.add("meeting")
        return self._ordered_domains(effective)

    def _agent_allowed_domains(self, room: Any, requested: list[str] | None) -> list[str]:
        room_domains = set(self._effective_domains_for_room(room))
        requested_domains = self._normalize_domain_list(requested)
        if not requested_domains:
            return self._ordered_domains(room_domains)
        return self._ordered_domains(set(requested_domains) & room_domains)

    @staticmethod
    def _normalize_tool_list(tools: Any) -> list[str]:
        if tools is None:
            return []
        if isinstance(tools, str):
            raw_tools = re.split(r"[\s,，;；]+", tools)
        elif isinstance(tools, (list, tuple, set)):
            raw_tools = list(tools)
        else:
            return []

        seen: set[str] = set()
        result: list[str] = []
        for value in raw_tools:
            tool = re.sub(r"\s+", "", str(value or "").strip())
            if not tool or tool in seen:
                continue
            if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", tool):
                continue
            seen.add(tool)
            result.append(tool)
        return result

    def _requested_domains_for_intent(self, intent: str | None, question: str) -> list[str]:
        intent_key = str(intent or "").strip()
        if intent_key in {"capability_intro", "meeting_summary", "action_items", "memory_transfer"}:
            return ["meeting", "memory"]
        if intent_key in {"risk_forecast", "evidence_query", "standard_explain"}:
            return ["quality", "standard", "meeting", "memory"]

        normalized = str(question or "").lower()
        compact = _normalize_name(question)
        domains: set[str] = set(_CORE_CONTEXT_DOMAINS)
        keyword_groups = [
            (("质检", "检测", "任务", "缺陷", "复核", "批次", "产品", "quality", "inspection"), {"quality", "standard"}),
            (("标准", "条款", "判定", "standard"), {"standard"}),
            (("模型", "价格", "成本", "供应商", "billing", "model", "price", "cost"), {"platform_ops", "model_billing"}),
            (("agent", "智能体", "路由", "trace", "prompt", "运行", "队列"), {"platform_ops"}),
            (("组织", "成员", "角色", "权限", "部门", "admin", "审计记录"), {"org_admin", "security_audit"}),
            (("数据源", "连接器", "rag", "同步", "索引", "dataset", "connector"), {"data_access", "platform_ops"}),
            (("会话", "聊天记录", "私聊", "conversation", "chat history"), {"ai_conversation", "security_audit"}),
            (("记忆", "候选记忆", "共享记忆", "memory"), {"memory"}),
        ]
        for keywords, mapped_domains in keyword_groups:
            if any(keyword in normalized or keyword in compact for keyword in keywords):
                domains.update(mapped_domains)
        return self._ordered_domains(domains)

    @staticmethod
    def _redacted_fields_for_question(question: str) -> list[str]:
        normalized = str(question or "").lower()
        if not any(term in normalized for term in _SENSITIVE_QUERY_TERMS):
            return []
        return ["api_key", "secret_key", "token", "password", "connection_string"]

    def _serialize_agent_row(self, row: Any, *, agent_name: str = "") -> MeetingRoomAgentResponse:
        return MeetingRoomAgentResponse(
            id=str(row.id),
            room_id=str(row.room_id),
            agent_id=str(row.agent_id),
            agent_name=agent_name,
            role=str(row.role),
            added_by=str(row.added_by),
            allowed_domains=self._normalize_domain_list(getattr(row, "allowed_domains", None)),
            allowed_tools=self._normalize_tool_list(getattr(row, "allowed_tools", None)),
        )

    def _serialize_agent_query_audit(self, row: Any) -> MeetingAgentQueryAuditResponse:
        return MeetingAgentQueryAuditResponse(
            id=str(row.id),
            room_id=str(row.room_id),
            user_id=str(row.user_id),
            agent_id=str(row.agent_id),
            question=str(row.question),
            intent=str(row.intent) if row.intent else None,
            requested_domains=self._normalize_domain_list(getattr(row, "requested_domains", None)),
            allowed_domains=self._normalize_domain_list(getattr(row, "allowed_domains", None)),
            denied_domains=self._normalize_domain_list(getattr(row, "denied_domains", None)),
            tool_calls=list(getattr(row, "tool_calls", None) or []),
            source_refs=list(getattr(row, "source_refs", None) or []),
            redacted_fields=[str(item) for item in (getattr(row, "redacted_fields", None) or [])],
            decision=str(getattr(row, "decision", "allowed") or "allowed"),
            created_at=getattr(row, "created_at", None),
        )

    async def _record_agent_query_audit(
        self,
        *,
        room: Any,
        question: str,
        intent: str | None,
        source_refs: list[dict] | None = None,
        tool_calls: list[dict] | None = None,
    ) -> None:
        create_audit = getattr(self._repo, "create_agent_query_audit", None)
        if create_audit is None:
            return

        requested_domains = self._requested_domains_for_intent(intent, question)
        room_domains = set(self._effective_domains_for_room(room))
        allowed_domains = self._ordered_domains(set(requested_domains) & room_domains)
        denied_domains = self._ordered_domains(set(requested_domains) - room_domains)
        decision = "allowed" if not denied_domains else ("partial" if allowed_domains else "denied")
        await create_audit(
            org_id=self._org_id,
            room_id=str(getattr(room, "id", "") or ""),
            user_id=self._user_id,
            agent_id=_MEETING_GENERAL_AGENT_ID,
            question=str(question or "").strip()[:4000],
            intent=intent,
            requested_domains=requested_domains,
            allowed_domains=allowed_domains,
            denied_domains=denied_domains,
            tool_calls=tool_calls or [],
            source_refs=source_refs or [],
            redacted_fields=self._redacted_fields_for_question(question),
            decision=decision,
        )

    async def _serialize_action_item(self, row) -> MeetingActionItemResponse:
        owner_name = ""
        if row.owner_id:
            user = await self._users.get_by_id(self._org_id, str(row.owner_id))
            owner_name = user.username if user else str(row.owner_id)[-8:]
        return MeetingActionItemResponse(
            id=str(row.id),
            room_id=str(row.room_id),
            title=str(row.title),
            description=row.description,
            owner_id=str(row.owner_id) if row.owner_id else None,
            owner_name=owner_name,
            due_at=row.due_at,
            status=str(row.status),
            source_message_id=str(row.source_message_id) if row.source_message_id else None,
            created_by=str(row.created_by),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def _serialize_rooms(self, rooms) -> list[MeetingRoomResponse]:
        room_ids = [str(room.id) for room in rooms]
        counts = await self._repo.count_members(self._org_id, room_ids)
        agent_counts = await self._repo.count_agents(self._org_id, room_ids)
        return [
            MeetingRoomResponse(
                id=str(room.id),
                org_id=str(room.org_id),
                title=str(room.title),
                access_code=str(room.access_code),
                created_by=str(room.created_by),
                status=str(getattr(room, "status", "active") or "active"),
                room_type=self._normalize_room_type(str(getattr(room, "room_type", "quality_business") or "quality_business")),
                visibility=str(getattr(room, "visibility", "private") or "private"),
                allowed_data_domains=self._effective_domains_for_room(room),
                memory_policy=getattr(room, "memory_policy", None) or {},
                audit_policy=getattr(room, "audit_policy", None) or {},
                member_count=counts.get(str(room.id), 0),
                agent_count=agent_counts.get(str(room.id), 0),
                last_message_at=getattr(room, "last_message_at", None),
                created_at=getattr(room, "created_at", None),
                updated_at=getattr(room, "updated_at", None),
            )
            for room in rooms
        ]

    async def _generate_access_code(self) -> str:
        for _ in range(10):
            code = secrets.token_hex(3).upper()
            if not await self._repo.get_room_by_code(self._org_id, code):
                return code
        return secrets.token_hex(4).upper()

    async def _resolve_visible_agent_name(self, agent_id: str) -> str:
        if _is_valid_uuid(agent_id):
            agent_def = await self._repo.get_visible_agent_definition(self._org_id, agent_id)
            if agent_def:
                return str(agent_def.name)
        return self._resolve_agent_name(agent_id)

    def _resolve_agent_name(self, agent_id: str) -> str:
        from agent.topology_catalog import get_registered_subgraphs

        for item in get_registered_subgraphs():
            if item.get("subgraph_key") == agent_id:
                return item.get("name") or agent_id
        return agent_id

    async def _parse_mentions(self, content: str, room_id: str) -> list[dict]:
        if "@" not in content:
            return []

        mentions: list[dict] = []
        seen_agent_ids: set[str] = set()
        room_agents = await self._repo.get_agents(self._org_id, room_id)
        participant_agents = [
            room_agent
            for room_agent in room_agents
            if getattr(room_agent, "role", "participant") == "participant"
        ]

        for room_agent in participant_agents:
            agent_id = str(room_agent.agent_id)
            agent_name = await self._resolve_visible_agent_name(agent_id)
            aliases = {agent_name}
            compact_name = _normalize_name(agent_name)
            if compact_name and compact_name != agent_name.lower():
                aliases.add(compact_name)
            if len(participant_agents) == 1:
                aliases.update({"agent", "aent", "ai"})

            matched = False
            for alias in aliases:
                if not alias:
                    continue
                pattern = re.compile(rf"@{re.escape(alias)}{_MENTION_DELIMITER_RE.pattern}", re.IGNORECASE)
                if pattern.search(content):
                    matched = True
                    break

            if matched and agent_id not in seen_agent_ids:
                seen_agent_ids.add(agent_id)
                mentions.append({"agent_id": agent_id, "agent_name": agent_name})

        return mentions

    def _contains_meeting_ai_mention(self, content: str) -> bool:
        aliases = {_MEETING_AI_AGENT_NAME, "AI 助手", "AI助手", "智能助手"}
        compact_name = _normalize_name(_MEETING_AI_AGENT_NAME)
        if compact_name:
            aliases.add(compact_name)

        for alias in aliases:
            pattern = re.compile(rf"@{re.escape(alias)}{_MENTION_DELIMITER_RE.pattern}", re.IGNORECASE)
            if pattern.search(content):
                return True
        return False

    def _contains_general_agent_mention(self, content: str) -> bool:
        compact_content = _normalize_name(content)
        compact_builtin_mentions = {
            f"@{_normalize_name(_MEETING_GENERAL_AGENT_NAME)}",
            "@agent",
            "@会议agent",
            "@总agent",
            "@总智能体",
        }
        if any(item in compact_content for item in compact_builtin_mentions):
            return True

        aliases = {
            _MEETING_GENERAL_AGENT_NAME,
            "agent",
            "会议 Agent",
            "会议Agent",
            "总智能体",
            "总Agent",
            "总 Agent",
            "总AI",
            "总 AI",
            "general agent",
        }
        compact_name = _normalize_name(_MEETING_GENERAL_AGENT_NAME)
        if compact_name:
            aliases.add(compact_name)

        for alias in aliases:
            normalized_alias = _normalize_name(alias)
            candidates = {alias}
            if normalized_alias:
                candidates.add(normalized_alias)
            for candidate in candidates:
                pattern = re.compile(rf"@{re.escape(candidate)}{_MENTION_DELIMITER_RE.pattern}", re.IGNORECASE)
                if pattern.search(content):
                    return True
        return False

    async def _invoke_general_agent_reply(self, *, room_id: str, query: str) -> None:
        try:
            async with get_session() as session:
                service = MeetingService(session, self._org_id, self._user_id, role=self._role)
                await service.run_general_agent(
                    room_id,
                    MeetingAgentRunRequest(query=query, mode="auto"),
                )
                await session.commit()
        except Exception as exc:
            logger.exception("meeting general agent invocation failed room_id=%s", room_id)
            await self._publish_general_agent_failure(room_id=room_id, error=str(exc) or exc.__class__.__name__)

    async def _publish_general_agent_failure(self, *, room_id: str, error: str) -> None:
        try:
            async with get_session() as session:
                repo = MeetingRepository(session)
                message = await repo.create_message(
                    org_id=self._org_id,
                    room_id=room_id,
                    user_id=self._user_id,
                    username=_MEETING_GENERAL_AGENT_NAME,
                    content=f"[会议Agent] 响应失败: {error}",
                    message_type="agent",
                    agent_id=_MEETING_GENERAL_AGENT_ID,
                    metadata_json={"selected_subgraph": "failure"},
                )
                response = MeetingMessageResponse.model_validate(message)
                await session.commit()
                await meeting_stream_broker.publish(
                    room_id,
                    {"event": "message_created", "room_id": room_id, "message": response.model_dump()},
                )
        except Exception:
            logger.exception("meeting general agent failure message publish failed room_id=%s", room_id)
