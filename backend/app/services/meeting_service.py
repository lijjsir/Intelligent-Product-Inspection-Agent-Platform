from __future__ import annotations

import asyncio
import logging
import re
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.core.ids import uuid7
from app.core.permissions import (
    ROLE_ADMIN,
    ROLE_ALGORITHM_ENGINEER,
    ROLE_APP_DEVELOPER,
    ROLE_EXPERT,
    ROLE_PLATFORM_OPERATOR,
    ROLE_USER,
)
from app.core.data_domain_policy import (
    ALL_DATA_DOMAINS,
    DEFAULT_ROOM_DOMAINS,
    SENSITIVE_DOMAINS,
    authorize_agent_domains,
    authorize_meeting_query,
    authorize_room_domains,
    infer_requested_domains_for_query,
    normalize_domains,
    ordered_domains,
    redacted_fields_for_question,
    role_allowed_domains,
)
from app.core.security import hash_password, verify_password
from app.models.memory import MemoryItem
from app.repositories.meeting_repo import MeetingRepository
from app.repositories.task_repo import TaskRepository
from app.repositories.user_repo import UserRepository
from app.schemas.meeting import (
    MeetingActionItemCreateRequest,
    MeetingActionItemResponse,
    MeetingActionItemUpdateRequest,
    MeetingConflictEventResponse,
    MeetingConflictResolveRequest,
    MeetingAgentQueryAuditResponse,
    MeetingAgentRunRequest,
    MeetingAgentRunResponse,
    MeetingBusinessContext,
    MeetingBusinessContextTask,
    MeetingBusinessContextUpdateRequest,
    MeetingCandidateMemoryResponse,
    MeetingContextPreviewResponse,
    MeetingDiscussionStartResponse,
    MeetingMemoryExtractRequest,
    MeetingMemoryDisputeRequest,
    MeetingMemoryResponse,
    MeetingMemoryShareApprovalResponse,
    MeetingMemoryScopeRequest,
    MeetingMemoryShareRequest,
    MeetingMemorySourceResponse,
    MeetingMemoryTransferRequest,
    MeetingMemoryUpdateRequest,
    MeetingMessageResponse,
    MeetingRoomAgentResponse,
    MeetingRoomDetailResponse,
    MeetingRoomMemberResponse,
    MeetingRoomResponse,
)
from app.schemas.memory import EventType, MemoryEventPayload, Workspace
from app.services.agent_manager_service import AgentManagerService
from app.services.chat_context_service import ChatContextService
from app.services.meeting_agent_cancel_registry import meeting_agent_cancel_registry
from app.services.meeting_agent_service import MeetingAgentService
from app.services.memory_service import MemoryService
from app.services.rag_space_service import RagSpaceService
from app.services.stream_service import meeting_stream_broker
from infra.database.session import get_session

_MENTION_DELIMITER_RE = re.compile(r"(?=$|[\s,.;:!?，。；：！？、）)])")
_MEETING_AI_AGENT_NAME = "AI助手"
_MEETING_GENERAL_AGENT_ID = "general_agent"
_MEETING_GENERAL_AGENT_NAME = "会议Agent"
logger = logging.getLogger(__name__)

_MESSAGE_RECALL_WINDOW = timedelta(minutes=2)
_AGENT_RUN_CANCELLED_MESSAGE = "会议Agent回复已停止"

_ALL_DATA_DOMAINS = list(ALL_DATA_DOMAINS)
_ROOM_QUERY_EXAMPLES = ["总结当前会议。", "提取会议待办。", "把刚才讨论整理成候选记忆。"]
_ROOM_GUARDRAILS = [
    "Agent 只能代用户查询其本来有权限的数据。",
    "具体事实查业务库，经验规律查记忆库。",
    "AI 对话内容是原始事件，不会自动成为已确认记忆。",
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
_PRIVATE_CONTEXT_QUERY_TERMS = (
    "我的",
    "我自己",
    "个人",
    "私有",
    "私聊",
    "偏好",
    "草稿",
    "只给我",
)
_BUSINESS_MEMORY_CATEGORY = "business_memory"
_MEETING_MEMORY_CATEGORY = "meeting_memory"
_REJECTED_MEMORY_CATEGORY = "rejected_noise"
_MEMORY_TYPE_QUALITY_FACT = "quality_fact"
_MEMORY_TYPE_RISK_INSIGHT = "risk_insight"
_MEMORY_TYPE_QUALITY_PATTERN = "quality_pattern"
_MEMORY_TYPE_ACTION_SUGGESTION = "action_suggestion"
_WORKSPACE_RISK_LIBRARY_SCOPE_ID = "quality_risk_library"
_MEMORY_SCOPE_MEETING_ROOM = "meeting_room"
_MEMORY_SCOPE_COLLAB_THREAD = "collab_thread"
_MEMORY_SCOPE_USER = "user"
_MEMORY_SCOPE_AGENT = "agent"
_MEMORY_SCOPE_ORG_SPACE = "org_space"
_MEMORY_PUBLISH_SCOPES = {
    _MEMORY_SCOPE_MEETING_ROOM,
    _MEMORY_SCOPE_COLLAB_THREAD,
    _MEMORY_SCOPE_USER,
    _MEMORY_SCOPE_AGENT,
    _MEMORY_SCOPE_ORG_SPACE,
}
_MEMORY_SCOPE_ALIASES = {
    "meeting": _MEMORY_SCOPE_MEETING_ROOM,
    "workspace": _MEMORY_SCOPE_ORG_SPACE,
    "organization": _MEMORY_SCOPE_ORG_SPACE,
}
_RESPONSE_VISIBILITY_ROOM = "room"
_RESPONSE_VISIBILITY_PRIVATE = "private"
_BUSINESS_TAG_TYPES = {
    "inspection_task": "task",
    "task": "task",
    "product": "product",
    "batch": "batch",
    "standard": "standard",
}
_LEGACY_BUSINESS_SCOPES = {"inspection_task", "product", "standard", "batch"}
_MEETING_ONLY_SCOPES = {_MEMORY_SCOPE_MEETING_ROOM}
_OBJECT_RESOLUTION_RESOLVED = "resolved"
_OBJECT_RESOLUTION_AMBIGUOUS = "ambiguous"
_OBJECT_RESOLUTION_UNRESOLVED = "unresolved"


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
        rooms = await self._repo.list_joined_rooms(
            self._org_id,
            self._user_id,
            limit=limit,
        )
        return await self._serialize_rooms(rooms)

    async def create_room(
        self,
        title: str,
        password: str | None = None,
        visibility: str = "private",
        allowed_data_domains: list[str] | None = None,
        business_context: dict | None = None,
    ) -> MeetingRoomResponse:
        clean_title = title.strip() or "会议室"
        effective_domains = self._effective_domains_for_create(allowed_data_domains)
        normalized_context = await self._normalize_business_context(business_context or {})
        room = await self._repo.create_room(
            org_id=self._org_id,
            user_id=self._user_id,
            title=clean_title[:120],
            access_code=await self._generate_access_code(),
            password_hash=hash_password(password) if password else None,
            visibility=visibility or "private",
            allowed_data_domains=effective_domains,
            memory_policy={
                "candidate_default_scope": "meeting_room",
                "publish_requires_confirmation": True,
                "business_context": normalized_context.model_dump(mode="json"),
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
        if str(room.status) != "active":
            raise ForbiddenError("meeting room is not active")
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
        visibility: str | None = None,
        allowed_data_domains: list[str] | None = None,
        business_context: dict | None = None,
    ) -> MeetingRoomResponse:
        await self._ensure_host(room_id)
        room = await self._repo.get_room(self._org_id, room_id)
        if not room:
            raise NotFoundError("meeting room not found")
        effective_domains = (
            self._effective_domains_for_create(allowed_data_domains)
            if allowed_data_domains is not None
            else None
        )
        memory_policy = None
        if business_context is not None:
            memory_policy = self._with_business_context(
                getattr(room, "memory_policy", None),
                await self._normalize_business_context(business_context),
            )
        updated = await self._repo.update_room(
            self._org_id,
            room_id,
            title=title.strip()[:120] if title else None,
            visibility=visibility,
            allowed_data_domains=effective_domains,
            memory_policy=memory_policy,
        )
        if not updated:
            raise NotFoundError("meeting room not found")
        await self._publish_system_message(room_id, "会议室权限边界已更新。")
        return (await self._serialize_rooms([updated]))[0]

    async def update_business_context(
        self,
        room_id: str,
        request: MeetingBusinessContextUpdateRequest,
    ) -> MeetingBusinessContext:
        await self._ensure_host(room_id)
        room = await self._repo.get_room(self._org_id, room_id)
        if not room:
            raise NotFoundError("meeting room not found")
        context = await self._normalize_business_context(request.model_dump())
        memory_policy = self._with_business_context(getattr(room, "memory_policy", None), context)
        await self._repo.update_room(self._org_id, room_id, memory_policy=memory_policy)
        await self._publish_system_message(room_id, "会议业务标签线索已更新。")
        await self._session.commit()
        return context

    async def close_room(self, room_id: str) -> MeetingRoomResponse:
        await self._ensure_host(room_id)
        room = await self._repo.update_room(self._org_id, room_id, status="closed")
        if not room:
            raise NotFoundError("meeting room not found")
        await self._publish_system_message(room_id, "会议已结束，后续消息发送与新成员加入已暂停。")
        return (await self._serialize_rooms([room]))[0]

    async def list_messages(self, room_id: str, after_seq: int = 0, limit: int = 200) -> list[MeetingMessageResponse]:
        await self._ensure_member(room_id)
        messages = await self._repo.list_messages(
            org_id=self._org_id,
            room_id=room_id,
            after_seq=after_seq,
            limit=limit,
            visible_user_id=self._user_id,
        )
        return [MeetingMessageResponse.model_validate(item) for item in messages]

    async def update_message(self, room_id: str, message_id: str, content: str) -> MeetingMessageResponse:
        await self._ensure_active_member(room_id)
        message = await self._repo.get_message(self._org_id, room_id, message_id)
        if not message:
            raise NotFoundError("meeting message not found")
        self._ensure_message_mutable(message)
        if self._message_recipient_user_id(message) and not self._is_agent_sidecar_question(message):
            raise ForbiddenError("private messages cannot be edited")
        clean_content = content.strip()
        if not clean_content:
            raise ValidationError("message content required")
        metadata = dict(message.metadata_json or {})
        metadata["edited_at"] = datetime.utcnow().isoformat()
        metadata.pop("recalled_at", None)
        updated = await self._repo.update_message_content(
            org_id=self._org_id,
            room_id=room_id,
            message_id=message_id,
            content=clean_content,
            metadata_json=metadata or None,
        )
        if not updated:
            raise NotFoundError("meeting message not found")
        response = MeetingMessageResponse.model_validate(updated)
        await self._session.commit()
        await self._publish_message_event(room_id, response)
        return response

    async def recall_message(self, room_id: str, message_id: str) -> MeetingMessageResponse:
        await self._ensure_active_member(room_id)
        message = await self._repo.get_message(self._org_id, room_id, message_id)
        if not message:
            raise NotFoundError("meeting message not found")
        self._ensure_message_mutable(message)
        if not self._is_message_recallable(message):
            raise ForbiddenError("消息只能在发送后 2 分钟内撤回")
        metadata = dict(message.metadata_json or {})
        metadata["recalled_at"] = datetime.utcnow().isoformat()
        metadata["original_content"] = message.content
        updated = await self._repo.update_message_content(
            org_id=self._org_id,
            room_id=room_id,
            message_id=message_id,
            content="",
            metadata_json=metadata,
        )
        if not updated:
            raise NotFoundError("meeting message not found")
        response = MeetingMessageResponse.model_validate(updated)
        await self._session.commit()
        await self._publish_message_event(room_id, response)
        return response

    async def quote_message(
        self,
        room_id: str,
        message_id: str,
        content: str,
        attachments: list[dict] | None = None,
    ) -> MeetingMessageResponse:
        return await self.send_message(room_id, content, quote_message_id=message_id, attachments=attachments)

    async def upload_attachments(self, room_id: str, files: list[UploadFile]) -> list[dict]:
        await self._ensure_active_member(room_id)
        service = RagSpaceService(self._session, org_id=self._org_id, user_id=self._user_id)
        return await service.upload_attachments(files=files)

    async def send_message(
        self,
        room_id: str,
        content: str,
        quote_message_id: str | None = None,
        private_recipient_user_id: str | None = None,
        skip_agent_trigger: bool = False,
        attachments: list[dict] | None = None,
        quote_snapshot: dict | None = None,
    ) -> MeetingMessageResponse:
        await self._ensure_active_member(room_id)
        user = await self._users.get_by_id(self._org_id, self._user_id)
        username = user.username if user else self._user_id[-8:]
        clean_content = content.strip()
        attachment_echo = self._normalize_message_attachments(attachments)
        normalized_quote_snapshot = self._normalize_quote_snapshot(quote_snapshot)
        if not clean_content and not attachment_echo and not normalized_quote_snapshot:
            raise ValidationError("message content or attachments required")
        if quote_message_id:
            quoted = await self._repo.get_message(self._org_id, room_id, quote_message_id)
            if not quoted:
                raise NotFoundError("quoted meeting message not found")
        private_recipient_user_id = str(private_recipient_user_id or "").strip() or None
        if private_recipient_user_id:
            if private_recipient_user_id == self._user_id:
                raise ValidationError("cannot send private message to self")
            recipient = await self._repo.get_member(self._org_id, room_id, private_recipient_user_id)
            if not recipient:
                raise NotFoundError("private message recipient not found in meeting room")
        general_agent_mentioned = self._contains_general_agent_mention(clean_content)
        legacy_ai_alias_mentioned = not general_agent_mentioned and self._contains_meeting_ai_mention(clean_content)
        agent_alias_mentioned = general_agent_mentioned or legacy_ai_alias_mentioned
        should_invoke_general_agent = bool(agent_alias_mentioned and not skip_agent_trigger and not private_recipient_user_id)
        agent_sidecar_private = bool(skip_agent_trigger and not private_recipient_user_id and agent_alias_mentioned)
        mentions = [] if (private_recipient_user_id or agent_alias_mentioned) else await self._parse_mentions(clean_content, room_id)
        stored_mentions = list(mentions)
        if agent_alias_mentioned and not private_recipient_user_id:
            stored_mentions.append({"agent_id": _MEETING_GENERAL_AGENT_ID, "agent_name": _MEETING_GENERAL_AGENT_NAME})
        message_metadata = {"attachment_echo": attachment_echo} if attachment_echo else {}
        if normalized_quote_snapshot:
            message_metadata["quote_snapshot"] = normalized_quote_snapshot
        if agent_sidecar_private:
            message_metadata["private_recipient_user_id"] = self._user_id
            message_metadata["agent_sidecar_question"] = True

        message = await self._repo.create_message(
            org_id=self._org_id,
            room_id=room_id,
            user_id=self._user_id,
            username=username,
            content=clean_content,
            message_type="user",
            mentions=stored_mentions if stored_mentions else None,
            quote_message_id=quote_message_id,
            metadata_json=message_metadata or None,
            private_recipient_user_id=private_recipient_user_id,
        )
        response = MeetingMessageResponse.model_validate(message)

        await self._session.commit()
        await self._publish_message_event(room_id, response)

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
                        user_role=self._role,
                    )
                )
        if should_invoke_general_agent:
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

    async def leave_room(self, room_id: str) -> None:
        room = await self._repo.get_room(self._org_id, room_id)
        if not room:
            raise NotFoundError("meeting room not found")
        member = await self._repo.get_member(self._org_id, room_id, self._user_id)
        if not member:
            raise ForbiddenError("you are not a member of this meeting room")
        if str(room.created_by) == self._user_id:
            raise ForbiddenError("meeting creator cannot leave the room; delete it instead")
        user = await self._users.get_by_id(self._org_id, self._user_id)
        username = user.username if user else self._user_id[-8:]
        removed = await self._repo.remove_member(self._org_id, room_id, self._user_id)
        if not removed:
            raise NotFoundError("meeting member not found")
        await self._publish_system_message(room_id, f"成员「{username}」已退出会议。")

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

        room_configured_domains = self._normalize_domain_list(getattr(room, "allowed_data_domains", None))
        allowed_domains = self._effective_domains_for_room(room)
        role_domains = role_allowed_domains(self._role)
        comparable_domains = self._normalize_domain_list(room_configured_domains or _ALL_DATA_DOMAINS)
        denied_domains = [
            domain
            for domain in comparable_domains
            if domain not in allowed_domains and domain in role_domains
        ]
        denied_domains.extend(
            domain
            for domain in comparable_domains
            if domain not in allowed_domains and domain not in role_domains
        )
        denied_domains = self._ordered_domains(denied_domains)
        sensitive_domains = [domain for domain in allowed_domains if domain in SENSITIVE_DOMAINS]
        query_auth = authorize_meeting_query(
            role=self._role,
            requested_domains=comparable_domains,
            room_domains=room_configured_domains or allowed_domains,
            agent_domains=allowed_domains,
            question="",
        )
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

        business_context = self._business_context_from_room(room)
        return MeetingContextPreviewResponse(
            room_id=room_id,
            user_role=self._role,
            room_role=str(getattr(member, "role", "member") or "member"),
            allowed_domains=allowed_domains,
            denied_domains=denied_domains,
            effective_domains=allowed_domains,
            room_configured_domains=room_configured_domains,
            sensitive_domains=sensitive_domains,
            denied_reasons=query_auth.denied_reasons,
            agent_permissions=agent_permissions,
            query_examples=list(_ROOM_QUERY_EXAMPLES),
            guardrails=list(_ROOM_GUARDRAILS),
            business_context=business_context,
            share_policy=self._meeting_share_policy(),
            conflict_rules=self._meeting_conflict_rules(),
            visibility_rules=self._meeting_visibility_rules(),
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
        access = self._authorize_general_agent_request(room=room, question=request.query, intent=request.mode)
        response_visibility = (
            _RESPONSE_VISIBILITY_PRIVATE
            if access.response_visibility == _RESPONSE_VISIBILITY_PRIVATE
            or self._response_visibility_for_request(request) == _RESPONSE_VISIBILITY_PRIVATE
            else _RESPONSE_VISIBILITY_ROOM
        )
        private_user_ids = self._private_user_ids_for_visibility(response_visibility)
        if access.decision == "denied":
            workflow_run_id = str(request.workflow_run_id or uuid7())
            agent_message_id = str(request.replace_message_id or uuid7())
            denial_answer = "当前请求超出你的会议室权限范围，无法回答该问题。"
            response_message = await self._upsert_general_agent_message(
                room_id=room_id,
                message_id=agent_message_id,
                content=denial_answer,
                metadata_json={
                    "query": request.query,
                    "selected_subgraph": "access_denied",
                    "allowed_data_domains": access.allowed_domains,
                    "denied_data_domains": access.denied_domains,
                    "response_visibility": response_visibility,
                    "visibility": response_visibility,
                    "audience_scope_type": _MEMORY_SCOPE_USER if response_visibility == _RESPONSE_VISIBILITY_PRIVATE else _MEMORY_SCOPE_MEETING_ROOM,
                    "audience_scope_id": self._user_id if response_visibility == _RESPONSE_VISIBILITY_PRIVATE else room_id,
                    "private_recipient_user_id": self._user_id if response_visibility == _RESPONSE_VISIBILITY_PRIVATE else None,
                },
                private_recipient_user_id=self._user_id if response_visibility == _RESPONSE_VISIBILITY_PRIVATE else None,
            )
            await self._record_agent_query_audit(
                room=room,
                question=request.query,
                intent="access_denied",
                source_refs=[],
                tool_calls=[],
                response_visibility=response_visibility,
            )
            await self._session.commit()
            await meeting_stream_broker.publish(
                room_id,
                {
                    "event": "message_created",
                    "room_id": room_id,
                    "message": MeetingMessageResponse.model_validate(response_message).model_dump(),
                    **({"private_user_ids": private_user_ids} if private_user_ids else {}),
                },
            )
            return MeetingAgentRunResponse(
                selected_subgraph="access_denied",
                answer=denial_answer,
                message=MeetingMessageResponse.model_validate(response_message),
                memory_sources=[],
                candidate_memories=[],
                response_visibility=response_visibility,
                escalation_required=False,
            )
        workflow_run_id = str(request.workflow_run_id or uuid7())
        agent_message_id = str(request.replace_message_id or uuid7())
        attachment_echo = self._normalize_message_attachments(request.attachments)
        response_visibility = (
            _RESPONSE_VISIBILITY_PRIVATE
            if access.response_visibility == _RESPONSE_VISIBILITY_PRIVATE
            or self._response_visibility_for_request(request) == _RESPONSE_VISIBILITY_PRIVATE
            else _RESPONSE_VISIBILITY_ROOM
        )
        response_metadata = self._response_visibility_metadata(response_visibility, room_id=room_id)
        private_user_ids = self._private_user_ids_for_visibility(response_visibility)
        meeting_agent_cancel_registry.clear(room_id, workflow_run_id)
        await meeting_stream_broker.publish(
            room_id,
            {
                "event": "agent_run_started",
                "room_id": room_id,
                "message_id": agent_message_id,
                "agent_id": _MEETING_GENERAL_AGENT_ID,
                "agent_name": _MEETING_GENERAL_AGENT_NAME,
                "workflow_run_id": workflow_run_id,
                "query": request.query,
                "attachments": attachment_echo,
                **({"private_user_ids": private_user_ids} if private_user_ids else {}),
            },
        )

        try:
            if self._is_general_agent_cancelled(room_id, workflow_run_id):
                raise asyncio.CancelledError()
            selected_subgraph = self._select_general_agent_subgraph(request.query, request.mode)
            if selected_subgraph == "agent_manager":
                return await self._run_agent_manager_for_meeting(room_id, request, room=room, workflow_run_id=workflow_run_id)

            memory_sources: list[MeetingMemorySourceResponse] = []
            recent_messages: list[Any] = []
            business_context = self._business_context_from_room(room)
            memory_sources = await self._collect_memory_sources(
                room_id,
                request.memory_scope,
                business_context=business_context,
            )
            recent_messages = await self._list_recent_messages(room_id=room_id, limit=80)
            if self._is_general_agent_cancelled(room_id, workflow_run_id):
                raise asyncio.CancelledError()
            answer = self._build_general_agent_answer(
                selected_subgraph=selected_subgraph,
                query=request.query,
                messages=recent_messages,
                memory_sources=memory_sources,
            )
            candidate_memories: list[MeetingCandidateMemoryResponse] = []
            if selected_subgraph in {"meeting_summary", "memory_transfer", "risk_forecast"}:
                candidate_memories = await self._extract_candidate_memories_from_messages(
                    room_id,
                    max_items=1 if selected_subgraph == "risk_forecast" else (2 if selected_subgraph == "meeting_summary" else 3),
                    topic=request.query,
                    intent=selected_subgraph,
                )
            if self._is_general_agent_cancelled(room_id, workflow_run_id):
                raise asyncio.CancelledError()

            message = await self._upsert_general_agent_message(
                room_id=room_id,
                message_id=agent_message_id,
                content=answer,
                metadata_json={
                    "query": request.query,
                    "selected_subgraph": selected_subgraph,
                    "memory_sources": [item.model_dump(mode="json") for item in memory_sources],
                    "candidate_memories": [item.model_dump(mode="json") for item in candidate_memories],
                    "business_context": business_context.model_dump(mode="json"),
                    "source_scope_refs": self._source_scope_refs(memory_sources),
                    "conflict_ref_ids": [],
                    **response_metadata,
                    **({"attachment_echo": attachment_echo} if attachment_echo else {}),
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
                response_visibility=response_visibility,
            )
            await self._session.commit()
            await meeting_stream_broker.publish(
                room_id,
                {
                    "event": "message_created",
                    "room_id": room_id,
                    "message": response_message.model_dump(),
                    **({"private_user_ids": private_user_ids} if private_user_ids else {}),
                },
            )
            return MeetingAgentRunResponse(
                selected_subgraph=selected_subgraph,
                answer=answer,
                message=response_message,
                memory_sources=memory_sources,
                candidate_memories=candidate_memories,
                response_visibility=response_visibility,
                escalation_required=False,
            )
        except asyncio.CancelledError:
            await self._publish_general_agent_cancelled(room_id=room_id, workflow_run_id=workflow_run_id, message_id=agent_message_id)
            return self._cancelled_general_agent_response(
                room_id=room_id,
                query=request.query,
                selected_subgraph="cancelled",
                memory_sources=[],
                candidate_memories=[],
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
                    **({"private_user_ids": private_user_ids} if private_user_ids else {}),
                },
            )
            raise
        finally:
            meeting_agent_cancel_registry.clear(room_id, workflow_run_id)

    async def _upsert_general_agent_message(
        self,
        *,
        room_id: str,
        message_id: str,
        content: str,
        metadata_json: dict,
        private_recipient_user_id: str | None = None,
    ) -> Any:
        existing = None
        get_message = getattr(self._repo, "get_message", None)
        if callable(get_message):
            existing = await get_message(self._org_id, room_id, message_id)
        if (
            existing
            and str(getattr(existing, "message_type", "")) == "agent"
            and str(getattr(existing, "agent_id", "")) == _MEETING_GENERAL_AGENT_ID
            and str(getattr(existing, "user_id", "")) == self._user_id
        ):
            return await self._repo.update_message_content(
                org_id=self._org_id,
                room_id=room_id,
                message_id=message_id,
                content=content,
                metadata_json=metadata_json,
            )
        return await self._repo.create_message(
            org_id=self._org_id,
            room_id=room_id,
            user_id=self._user_id,
            username=_MEETING_GENERAL_AGENT_NAME,
            content=content,
            message_type="agent",
            agent_id=_MEETING_GENERAL_AGENT_ID,
            metadata_json=metadata_json,
            private_recipient_user_id=private_recipient_user_id,
        )

    async def cancel_general_agent_run(self, room_id: str, workflow_run_id: str) -> dict[str, str | bool]:
        await self._ensure_member(room_id)
        clean_workflow_run_id = str(workflow_run_id or "").strip()
        if not clean_workflow_run_id:
            raise ValidationError("workflow_run_id required")
        meeting_agent_cancel_registry.cancel(room_id, clean_workflow_run_id)
        await self._publish_general_agent_cancelled(
            room_id=room_id,
            workflow_run_id=clean_workflow_run_id,
            message_id="",
        )
        return {"cancelled": True, "workflow_run_id": clean_workflow_run_id}

    def _is_general_agent_cancelled(self, room_id: str, workflow_run_id: str) -> bool:
        return meeting_agent_cancel_registry.is_cancelled(room_id, workflow_run_id)

    async def _publish_general_agent_cancelled(self, *, room_id: str, workflow_run_id: str, message_id: str) -> None:
        await meeting_stream_broker.publish(
            room_id,
            {
                "event": "agent_run_failed",
                "room_id": room_id,
                "message_id": message_id,
                "agent_id": _MEETING_GENERAL_AGENT_ID,
                "agent_name": _MEETING_GENERAL_AGENT_NAME,
                "workflow_run_id": workflow_run_id,
                "error": _AGENT_RUN_CANCELLED_MESSAGE,
                "private_user_ids": [self._user_id],
            },
        )

    def _cancelled_general_agent_response(
        self,
        *,
        room_id: str,
        query: str,
        selected_subgraph: str,
        memory_sources: list[MeetingMemorySourceResponse],
        candidate_memories: list[MeetingCandidateMemoryResponse],
    ) -> MeetingAgentRunResponse:
        message = MeetingMessageResponse(
            id="cancelled",
            room_id=room_id,
            user_id=_MEETING_GENERAL_AGENT_ID,
            username=_MEETING_GENERAL_AGENT_NAME,
            seq_no=0,
            content=_AGENT_RUN_CANCELLED_MESSAGE,
            message_type="agent",
            agent_id=_MEETING_GENERAL_AGENT_ID,
            metadata_json={"query": query, "cancelled": True},
            private_recipient_user_id=self._user_id,
        )
        return MeetingAgentRunResponse(
            selected_subgraph=selected_subgraph,
            answer=_AGENT_RUN_CANCELLED_MESSAGE,
            message=message,
            memory_sources=memory_sources,
            candidate_memories=candidate_memories,
            response_visibility=_RESPONSE_VISIBILITY_PRIVATE,
        )

    async def list_room_memories(self, room_id: str) -> list[MeetingMemoryResponse]:
        await self._ensure_member(room_id)
        room = await self._repo.get_room(self._org_id, room_id)
        business_context = self._business_context_from_room(room)
        items = await self._list_memory_items_for_room(
            org_id=self._org_id,
            room_id=room_id,
            business_context=business_context.model_dump(mode="json"),
            include_confirmed=True,
            statuses=["candidate", "confirmed", "active", "disputed", "superseded"],
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
        original_content_json = dict(content_json)
        original_scope_json = dict(item.scope_json or {})
        original_status = str(getattr(item, "status", "") or "")
        if request and request.title:
            content_json["title"] = request.title.strip()
        if request and request.content:
            content_json["content"] = request.content.strip()
        if request and request.affected_objects is not None:
            content_json["affected_objects"] = self._normalize_affected_objects(request.affected_objects)
        if request and request.object_resolution_status:
            content_json["object_resolution_status"] = request.object_resolution_status
        if request and request.related_memory_ids is not None:
            content_json["related_memory_ids"] = self._dedupe_text_values(request.related_memory_ids, limit=20, max_length=64)
        content_json["qdl_json"] = self._memory_qdl_json(
            str(content_json.get("memory_type") or "decision"),
            str(content_json.get("title") or item.content_summary or ""),
            str(content_json.get("content") or item.content_summary or ""),
            content_json,
        )
        content_json["confirmed_by"] = self._user_id
        content_json["confirmed_at"] = datetime.utcnow().isoformat()
        requested_scope = self._normalize_memory_scope((request.scope if request else None) or "meeting_room")
        publish_reason = str((request.publish_reason if request else None) or "").strip()
        if publish_reason:
            content_json["publish_reason"] = publish_reason
        original_category = str(original_content_json.get("memory_category") or _MEETING_MEMORY_CATEGORY)
        room = await self._repo.get_room(self._org_id, room_id)
        business_context = self._business_context_from_room(room)
        inferred_type = self._infer_candidate_memory_type(
            str(content_json.get("title") or ""),
            str(content_json.get("content") or item.content_summary or ""),
        )
        if inferred_type != "decision" or not content_json.get("memory_type"):
            content_json["memory_type"] = inferred_type
        affected_objects = content_json.get("affected_objects") if isinstance(content_json.get("affected_objects"), dict) else {}
        object_resolution_status = str(content_json.get("object_resolution_status") or _OBJECT_RESOLUTION_UNRESOLVED)
        affected_context = self._business_context_from_affected_objects(affected_objects)
        effective_context = self._merge_business_context(business_context, affected_context)
        content_json["business_context"] = effective_context.model_dump(mode="json")
        inferred_category = self._classify_candidate_memory(
            str(content_json.get("title") or ""),
            str(content_json.get("content") or item.content_summary or ""),
            effective_context,
            memory_type=str(content_json.get("memory_type") or "decision"),
        )
        if original_category != _REJECTED_MEMORY_CATEGORY:
            content_json["memory_category"] = inferred_category
        if request and request.is_business_memory is not None and original_category != _REJECTED_MEMORY_CATEGORY:
            content_json["memory_category"] = (
                _BUSINESS_MEMORY_CATEGORY if request.is_business_memory else _MEETING_MEMORY_CATEGORY
            )
        content_json["dedupe_key"] = self._candidate_dedupe_key(
            str(content_json.get("memory_type") or "decision"),
            str(content_json.get("content") or item.content_summary or ""),
            affected_objects,
        )
        content_json["shareability"] = self._memory_shareability(
            str(content_json.get("memory_category") or _MEETING_MEMORY_CATEGORY),
            effective_context,
            memory_type=str(content_json.get("memory_type") or "decision"),
            object_resolution_status=object_resolution_status,
        )
        content_json["warnings"] = self._candidate_warnings(
            str(content_json.get("memory_category") or _MEETING_MEMORY_CATEGORY),
            str(content_json.get("content") or item.content_summary or ""),
            memory_type=str(content_json.get("memory_type") or "decision"),
            business_context=effective_context,
            object_resolution_status=object_resolution_status,
            related_memory_ids=list(content_json.get("related_memory_ids") or []),
        )
        await self._ensure_memory_publish_allowed(item, requested_scope, request.scope_id if request else None, content_json)
        target_scope_type, target_scope_id = self._resolve_memory_publish_scope(
            room_id=room_id,
            scope=requested_scope,
            scope_id=request.scope_id if request else None,
            business_context=business_context,
        )
        content_json["published_scope"] = requested_scope
        content_json["target_scope_type"] = target_scope_type
        content_json["target_scope_id"] = target_scope_id
        content = str(content_json.get("content") or item.content_summary or "")
        status = str(getattr(item, "status", "") or "")
        has_confirmed_before = status in {"active", "confirmed", "disputed", "superseded"} or bool(original_content_json.get("confirmed_at"))
        is_revision = has_confirmed_before and self._has_memory_revision(original_content_json, content_json, requested_scope, request.scope_id if request else None)
        updated = None
        if is_revision:
            updated = await self._create_memory_revision(
                item=item,
                room_id=room_id,
                target_scope_type=target_scope_type,
                target_scope_id=target_scope_id,
                requested_scope=requested_scope,
                content_json=content_json,
                content=content,
            )
            await self._repo.update_memory_item(
                org_id=self._org_id,
                memory_id=memory_id,
                status="superseded",
                content_json={
                    **original_content_json,
                    "superseded_by": str(updated.memory_id),
                    "superseded_at": datetime.utcnow().isoformat(),
                    "superseded_by_user": self._user_id,
                },
            )
        else:
            updated = await self._repo.update_memory_item(
                org_id=self._org_id,
                memory_id=memory_id,
                status="confirmed",
                content_summary=content[:1000],
                content_json=content_json,
                scope_json=self._memory_scope_json(
                    target_scope_type,
                    target_scope_id,
                    source_room_id=room_id,
                ),
            )
            await self._repo.create_memory_scope_binding(
                org_id=self._org_id,
                memory_id=memory_id,
                scope_type=target_scope_type,
                scope_id=target_scope_id,
                permission="read",
                created_by=self._user_id,
            )
        await self._repo.replace_memory_tags(
            org_id=self._org_id,
            memory_id=str(getattr(updated, "memory_id", memory_id)),
            tags=self._memory_tags_from_content(content_json),
        )
        await self._record_meeting_memory_event(
            event_type=EventType.MEMORY_WRITE_CREATED,
            memory_id=str(getattr(updated, "memory_id", memory_id)),
            room_id=room_id,
            payload={
                "action": "revision" if is_revision else "confirm",
                "from_status": original_status,
                "from_scope": original_scope_json,
                "to_scope_type": target_scope_type,
                "to_scope_id": target_scope_id,
                "published_scope": requested_scope,
                "memory_category": content_json.get("memory_category"),
                "source_refs": content_json.get("source_refs") or [],
                "publish_reason": publish_reason,
            },
        )
        await self._repo.create_memory_transfer_log(
            org_id=self._org_id,
            memory_id=str(getattr(updated, "memory_id", memory_id)),
            from_scope_type="meeting_room",
            from_scope_id=room_id,
            to_scope_type=target_scope_type,
            to_scope_id=target_scope_id,
            transfer_reason=publish_reason or ("会议记忆修订后沉淀为新版本" if is_revision else "会议候选记忆经用户确认后进入已确认记忆"),
            status="confirmed",
            operator_id=self._user_id,
        )
        await self._publish_system_message(
            room_id,
            f"记忆「{content_json.get('title') or '会议记忆'}」已确认并沉淀到{self._memory_scope_label(target_scope_type)}。"
            if not is_revision
            else f"记忆「{content_json.get('title') or '会议记忆'}」已生成修订版本并沉淀到{self._memory_scope_label(target_scope_type)}。",
        )
        return self._serialize_memory_item(updated or item, room_id=room_id)

    async def reject_memory(
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
        reject_reason = str((request.content if request else "") or "").strip()
        content_json = dict(item.content_json or {})
        content_json["rejected_by"] = self._user_id
        content_json["rejected_at"] = datetime.utcnow().isoformat()
        if reject_reason:
            content_json["reject_reason"] = reject_reason[:1000]
        updated = await self._repo.update_memory_item(
            org_id=self._org_id,
            memory_id=memory_id,
            status="rejected",
            content_json=content_json,
        )
        await self._record_meeting_memory_event(
            event_type=EventType.MEMORY_WRITE_REJECTED,
            memory_id=memory_id,
            room_id=room_id,
            payload={
                "action": "reject",
                "reason": reject_reason,
                "source_refs": content_json.get("source_refs") or [],
            },
        )
        await self._repo.create_memory_transfer_log(
            org_id=self._org_id,
            memory_id=memory_id,
            from_scope_type="meeting_room",
            from_scope_id=room_id,
            to_scope_type="meeting_room",
            to_scope_id=room_id,
            transfer_reason=f"用户拒绝候选记忆：{reject_reason[:200]}" if reject_reason else "用户拒绝候选记忆",
            status="rejected",
            operator_id=self._user_id,
        )
        await self._publish_system_message(
            room_id,
            f"一条候选记忆已被拒绝，理由：{reject_reason[:120]}" if reject_reason else "一条候选记忆已被拒绝。",
        )
        return self._serialize_memory_item(updated or item, room_id=room_id)

    async def dispute_memory(
        self,
        memory_id: str,
        request: MeetingMemoryDisputeRequest,
    ) -> MeetingMemoryResponse:
        item = await self._repo.get_memory_item(self._org_id, memory_id)
        if item is None:
            raise NotFoundError("meeting memory not found")
        room_id = self._memory_room_id(item)
        if not room_id:
            raise ForbiddenError("memory is not sourced from a meeting room")
        await self._ensure_member(room_id)
        content_json = dict(item.content_json or {})
        disputes = list(content_json.get("disputes") or [])
        dispute = {
            "reason": request.reason.strip(),
            "conflicting_memory_id": request.conflicting_memory_id,
            "created_by": self._user_id,
            "created_at": datetime.utcnow().isoformat(),
        }
        disputes.append(dispute)
        content_json["disputes"] = disputes
        content_json["last_disputed_by"] = self._user_id
        content_json["last_disputed_at"] = dispute["created_at"]
        updated = await self._repo.update_memory_item(
            org_id=self._org_id,
            memory_id=memory_id,
            status="disputed",
            content_json=content_json,
        )
        await self._record_meeting_memory_event(
            event_type=EventType.MEMORY_CONFLICT_DETECTED,
            memory_id=memory_id,
            room_id=room_id,
            payload={"action": "dispute", **dispute},
        )
        await self._publish_system_message(room_id, f"记忆「{content_json.get('title') or '会议记忆'}」已被标记为有争议。")
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
            await self._ensure_host(room_id)
        target_scope_type = self._normalize_memory_scope(request.to_scope_type)
        target_scope_id = request.to_scope_id
        if target_scope_type == _MEMORY_SCOPE_MEETING_ROOM:
            if room_id and target_scope_id in {"current", room_id}:
                target_scope_id = room_id
            elif not target_scope_id:
                raise ValidationError("meeting_room scope requires scope_id")
        await self._ensure_memory_publish_allowed(item, target_scope_type, target_scope_id, dict(item.content_json or {}), transfer=True)
        requires_approval = await self._memory_transfer_requires_approval(
            item,
            source_room_id=room_id,
            target_scope_type=target_scope_type,
            target_scope_id=target_scope_id,
        )
        if requires_approval:
            transfer_log = await self._repo.create_memory_transfer_log(
                org_id=self._org_id,
                memory_id=memory_id,
                from_scope_type=_MEMORY_SCOPE_MEETING_ROOM,
                from_scope_id=room_id or "unknown",
                to_scope_type=target_scope_type,
                to_scope_id=target_scope_id,
                transfer_reason=request.transfer_reason,
                status="pending_approval",
                operator_id=self._user_id,
            )
            content_json = dict(item.content_json or {})
            content_json["target_scope_type"] = target_scope_type
            content_json["target_scope_id"] = target_scope_id
            content_json["published_scope"] = str(content_json.get("published_scope") or self._memory_current_scope(item) or _MEMORY_SCOPE_MEETING_ROOM)
            content_json["share_reason"] = request.transfer_reason
            content_json["shareability"] = self._shareability_with_target(
                content_json.get("shareability"),
                target_scope_type,
                target_scope_id,
                requires_approval=True,
                approval_role=self._approval_role_for_scope(target_scope_type),
            )
            content_json["pending_transfer_id"] = str(transfer_log.id)
            updated = await self._repo.update_memory_item(
                org_id=self._org_id,
                memory_id=memory_id,
                content_json=content_json,
            )
            if room_id:
                await self._publish_system_message(room_id, "记忆共享请求已提交，等待目标范围确认。")
            return self._serialize_memory_item(updated or item, room_id=room_id or "")
        await self._repo.create_memory_scope_binding(
            org_id=self._org_id,
            memory_id=memory_id,
            scope_type=target_scope_type,
            scope_id=target_scope_id,
            permission="read",
            created_by=self._user_id,
        )
        await self._repo.create_memory_transfer_log(
            org_id=self._org_id,
            memory_id=memory_id,
            from_scope_type="meeting_room",
            from_scope_id=room_id or "unknown",
            to_scope_type=target_scope_type,
            to_scope_id=target_scope_id,
            transfer_reason=request.transfer_reason,
            status="executed",
            operator_id=self._user_id,
        )
        content_json = dict(item.content_json or {})
        content_json["target_scope_type"] = target_scope_type
        content_json["target_scope_id"] = target_scope_id
        content_json["published_scope"] = target_scope_type
        content_json["share_reason"] = request.transfer_reason
        content_json["shareability"] = self._shareability_with_target(
            content_json.get("shareability"),
            target_scope_type,
            target_scope_id,
            requires_approval=False,
            approval_role="none",
        )
        content_json["qdl_json"] = self._memory_qdl_json(
            str(content_json.get("memory_type") or "decision"),
            str(content_json.get("title") or item.content_summary or ""),
            str(content_json.get("content") or item.content_summary or ""),
            content_json,
        )
        await self._repo.replace_memory_tags(
            org_id=self._org_id,
            memory_id=memory_id,
            tags=self._memory_tags_from_content(content_json),
        )
        updated = await self._repo.update_memory_item(
            org_id=self._org_id,
            memory_id=memory_id,
            content_json=content_json,
            scope_json=self._memory_scope_json(
                target_scope_type,
                target_scope_id,
                source_room_id=room_id,
            ),
        )
        return self._serialize_memory_item(updated or item, room_id=room_id or "")

    async def share_memory(
        self,
        memory_id: str,
        request: MeetingMemoryShareRequest,
    ) -> MeetingMemoryResponse:
        return await self.transfer_memory(
            memory_id,
            MeetingMemoryTransferRequest(
                to_scope_type=request.target_scope_type,
                to_scope_id=request.target_scope_id,
                transfer_reason=request.share_reason,
            ),
        )

    async def list_pending_memory_shares(self, room_id: str | None = None) -> list[MeetingMemoryShareApprovalResponse]:
        target_room_ids: list[str] | None = None
        if room_id:
            await self._ensure_member(room_id)
            target_room_ids = [room_id]
        rows = await self._repo.list_pending_memory_transfer_logs(
            org_id=self._org_id,
            target_room_ids=target_room_ids,
            limit=100,
        )
        responses: list[MeetingMemoryShareApprovalResponse] = []
        for row in rows:
            if not await self._can_view_or_approve_share(row):
                continue
            responses.append(await self._serialize_memory_share_approval(row))
        return responses

    async def approve_memory_share(self, transfer_id: str) -> MeetingMemoryResponse:
        row = await self._repo.get_memory_transfer_log(self._org_id, transfer_id)
        if row is None:
            raise NotFoundError("memory share request not found")
        if str(row.status) != "pending_approval":
            raise ValidationError("memory share request is not pending approval")
        await self._ensure_memory_share_approver(row)
        item = await self._repo.get_memory_item(self._org_id, str(row.memory_id))
        if item is None:
            raise NotFoundError("meeting memory not found")
        try:
            await self._repo.create_memory_scope_binding(
                org_id=self._org_id,
                memory_id=str(row.memory_id),
                scope_type=str(row.to_scope_type),
                scope_id=str(row.to_scope_id),
                permission="read",
                created_by=self._user_id,
            )
            content_json = dict(item.content_json or {})
            content_json["target_scope_type"] = str(row.to_scope_type)
            content_json["target_scope_id"] = str(row.to_scope_id)
            content_json["published_scope"] = str(row.to_scope_type)
            content_json["share_reason"] = row.transfer_reason
            content_json["pending_transfer_id"] = None
            content_json["approved_transfer_id"] = str(row.id)
            content_json["shareability"] = self._shareability_with_target(
                content_json.get("shareability"),
                str(row.to_scope_type),
                str(row.to_scope_id),
                requires_approval=False,
                approval_role="approved",
            )
            await self._repo.replace_memory_tags(
                org_id=self._org_id,
                memory_id=str(row.memory_id),
                tags=self._memory_tags_from_content(content_json),
            )
            updated = await self._repo.update_memory_item(
                org_id=self._org_id,
                memory_id=str(row.memory_id),
                content_json=content_json,
                scope_json=self._memory_scope_json(
                    str(row.to_scope_type),
                    str(row.to_scope_id),
                    source_room_id=str(row.from_scope_id) if str(row.from_scope_type) == _MEMORY_SCOPE_MEETING_ROOM else None,
                ),
            )
            await self._repo.update_memory_transfer_log_status(
                org_id=self._org_id,
                transfer_id=transfer_id,
                status="executed",
                operator_id=self._user_id,
            )
            if str(row.from_scope_type) == _MEMORY_SCOPE_MEETING_ROOM:
                await self._publish_system_message(str(row.from_scope_id), "一条记忆共享请求已通过审批并生效。")
            return self._serialize_memory_item(updated or item, room_id=str(row.from_scope_id or ""))
        except Exception:
            logger.exception("approve_memory_share failed for transfer_id=%s", transfer_id)
            raise

    async def reject_memory_share(self, transfer_id: str) -> MeetingMemoryShareApprovalResponse:
        row = await self._repo.get_memory_transfer_log(self._org_id, transfer_id)
        if row is None:
            raise NotFoundError("memory share request not found")
        await self._ensure_memory_share_approver(row)
        updated = await self._repo.update_memory_transfer_log_status(
            org_id=self._org_id,
            transfer_id=transfer_id,
            status="rejected",
            operator_id=self._user_id,
        )
        if str(row.from_scope_type) == _MEMORY_SCOPE_MEETING_ROOM:
            await self._publish_system_message(str(row.from_scope_id), "一条记忆共享请求已被拒绝。")
        return await self._serialize_memory_share_approval(updated or row)

    async def list_conflicts(self, room_id: str, limit: int = 50) -> list[MeetingConflictEventResponse]:
        await self._ensure_member(room_id)
        rows = await self._repo.list_conflict_events(org_id=self._org_id, room_id=room_id, limit=limit)
        return [self._serialize_conflict_event(row) for row in rows]

    async def resolve_conflict(
        self,
        conflict_id: str,
        request: MeetingConflictResolveRequest,
    ) -> MeetingConflictEventResponse:
        row = await self._repo.get_conflict_event(self._org_id, conflict_id)
        if row is None:
            raise NotFoundError("meeting conflict not found")
        await self._ensure_host(str(row.room_id))
        status = "rejected" if request.selected_action == "reject" else "resolved"
        updated = await self._repo.resolve_conflict_event(
            org_id=self._org_id,
            conflict_id=conflict_id,
            selected_action=request.selected_action,
            resolved_by=self._user_id,
            status=status,
        )
        await self._publish_system_message(str(row.room_id), f"会议冲突已处理：{request.selected_action}")
        return self._serialize_conflict_event(updated or row)

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

    def _ensure_message_mutable(self, message: Any) -> None:
        if str(getattr(message, "user_id", "")) != self._user_id:
            raise ForbiddenError("only the sender can edit this message")
        if str(getattr(message, "message_type", "")) != "user":
            raise ForbiddenError("only user messages can be edited")
        metadata = getattr(message, "metadata_json", None) or {}
        if isinstance(metadata, dict) and metadata.get("recalled_at"):
            raise ForbiddenError("recalled messages cannot be edited")

    def _is_agent_sidecar_question(self, message: Any) -> bool:
        if str(getattr(message, "message_type", "")) != "user":
            return False
        if str(getattr(message, "user_id", "")) != self._user_id:
            return False
        metadata = getattr(message, "metadata_json", None) or {}
        if isinstance(metadata, dict) and metadata.get("agent_sidecar_question") is True:
            return True
        recipient_id = self._message_recipient_user_id(message)
        sender_label = str(getattr(message, "username", "") or "").strip()
        if recipient_id and recipient_id not in {self._user_id, sender_label}:
            return False
        mentions = getattr(message, "mentions", None) or []
        if isinstance(mentions, list):
            for mention in mentions:
                if not isinstance(mention, dict):
                    continue
                if str(mention.get("agent_id") or "") == _MEETING_GENERAL_AGENT_ID:
                    return True
                if str(mention.get("agent_name") or "") == _MEETING_GENERAL_AGENT_NAME:
                    return True
        content = str(getattr(message, "content", "") or "")
        return self._contains_general_agent_mention(content) or self._contains_meeting_ai_mention(content)

    @staticmethod
    def _is_message_recallable(message: Any) -> bool:
        created_at = getattr(message, "created_at", None)
        if not isinstance(created_at, datetime):
            return False
        return datetime.utcnow() - created_at <= _MESSAGE_RECALL_WINDOW

    @staticmethod
    def _message_recipient_user_id(message: MeetingMessageResponse | Any) -> str:
        direct_value = getattr(message, "private_recipient_user_id", None)
        if isinstance(direct_value, str) and direct_value.strip():
            return direct_value.strip()
        metadata = getattr(message, "metadata_json", None) or {}
        metadata_value = metadata.get("private_recipient_user_id") if isinstance(metadata, dict) else None
        return metadata_value.strip() if isinstance(metadata_value, str) and metadata_value.strip() else ""

    async def _publish_message_event(self, room_id: str, message: MeetingMessageResponse) -> None:
        payload = {"event": "message_created", "room_id": room_id, "message": message.model_dump()}
        recipient_id = self._message_recipient_user_id(message)
        if recipient_id:
            payload["private_user_ids"] = [self._user_id, recipient_id]
        await meeting_stream_broker.publish(room_id, payload)

    async def _list_recent_messages(self, *, room_id: str, limit: int = 50) -> list[Any]:
        list_recent = getattr(self._repo, "list_recent_messages", None)
        if list_recent:
            try:
                return await list_recent(
                    org_id=self._org_id,
                    room_id=room_id,
                    limit=limit,
                    visible_user_id=self._user_id,
                )
            except TypeError:
                return await list_recent(org_id=self._org_id, room_id=room_id, limit=limit)
        try:
            messages = await self._repo.list_messages(
                org_id=self._org_id,
                room_id=room_id,
                after_seq=0,
                limit=limit,
                visible_user_id=self._user_id,
            )
        except TypeError:
            messages = await self._repo.list_messages(
                org_id=self._org_id,
                room_id=room_id,
                after_seq=0,
                limit=limit,
            )
        return messages[-limit:]

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
            username="绯荤粺",
            content=content,
            message_type="system",
        )
        response = MeetingMessageResponse.model_validate(message)
        await self._session.commit()
        await self._publish_message_event(room_id, response)
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
        quality_terms = (
            "质检",
            "检测",
            "检验",
            "质量",
            "inspection",
            "quality",
            "结果",
            "通过",
            "没通过",
            "未通过",
            "不通过",
            "失败",
            "不合格",
            "评分",
            "耗时",
            "批次",
            "产品",
        )
        quality_question_terms = (
            "最近",
            "当前",
            "状态",
            "状况",
            "情况",
            "分析",
            "为什么",
            "原因",
            "怎么",
            "查询",
            "查看",
            "多少",
            "哪些",
            "哪",
            "总结",
        )
        if any(term in normalized or term in compact for term in quality_terms) and any(
            term in normalized or term in compact for term in quality_question_terms
        ):
            return "agent_manager"
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
        workflow_run_id: str | None = None,
    ) -> MeetingAgentRunResponse:
        room = room or await self._repo.get_room(self._org_id, room_id)
        if not room:
            raise NotFoundError("meeting room not found")
        workflow_run_id = str(workflow_run_id or request.workflow_run_id or uuid7())
        agent_message_id = str(request.replace_message_id or uuid7())
        access = self._authorize_general_agent_request(room=room, question=request.query, intent="agent_manager")
        if access.decision == "denied":
            denial_content = "当前请求超出你的会议室权限范围，无法回答该问题。"
            denial_message = await self._upsert_general_agent_message(
                room_id=room_id,
                message_id=agent_message_id,
                content=denial_content,
                metadata_json={
                    "query": request.query,
                    "selected_subgraph": "access_denied",
                    "allowed_data_domains": access.allowed_domains,
                    "denied_data_domains": access.denied_domains,
                    "visibility": access.response_visibility,
                    "response_visibility": access.response_visibility,
                    "audience_scope_type": _MEMORY_SCOPE_USER if access.response_visibility == _RESPONSE_VISIBILITY_PRIVATE else _MEMORY_SCOPE_MEETING_ROOM,
                    "audience_scope_id": self._user_id if access.response_visibility == _RESPONSE_VISIBILITY_PRIVATE else room_id,
                },
                private_recipient_user_id=self._user_id if access.response_visibility == _RESPONSE_VISIBILITY_PRIVATE else None,
            )
            denial_response = MeetingMessageResponse.model_validate(denial_message)
            await self._record_agent_query_audit(
                room=room,
                question=request.query,
                intent="access_denied",
                source_refs=[],
                tool_calls=[],
                response_visibility=access.response_visibility,
            )
            await self._session.commit()
            await meeting_stream_broker.publish(
                room_id,
                {
                    "event": "message_created",
                    "room_id": room_id,
                    "message": denial_response.model_dump(),
                    **({"private_user_ids": [self._user_id]} if access.response_visibility == _RESPONSE_VISIBILITY_PRIVATE else {}),
                },
            )
            return MeetingAgentRunResponse(
                selected_subgraph="access_denied",
                answer=denial_response.content,
                message=denial_response,
                memory_sources=[],
                candidate_memories=[],
                response_visibility=access.response_visibility,
                escalation_required=False,
            )
        if self._is_general_agent_cancelled(room_id, workflow_run_id):
            raise asyncio.CancelledError()
        response_visibility = (
            _RESPONSE_VISIBILITY_PRIVATE
            if access.response_visibility == _RESPONSE_VISIBILITY_PRIVATE
            or self._response_visibility_for_request(request) == _RESPONSE_VISIBILITY_PRIVATE
            else _RESPONSE_VISIBILITY_ROOM
        )
        response_metadata = self._response_visibility_metadata(response_visibility, room_id=room_id)
        private_user_ids = self._private_user_ids_for_visibility(response_visibility)
        recent_messages = await self._list_recent_messages(room_id=room_id, limit=24)
        allowed_domains = access.allowed_domains or self._effective_domains_for_room(room)
        query = self._clean_general_agent_query(request.query)
        attachment_echo = self._normalize_message_attachments(request.attachments)
        inspection_context = await self._call_build_meeting_inspection_context(room)
        business_context = self._merge_business_context(
            self._business_context_from_room(room),
            self._business_context_from_inspection_context(inspection_context),
        )
        memory_sources = await self._collect_memory_sources(
            room_id,
            request.memory_scope,
            business_context=business_context,
        )
        payload = {
            "request_id": str(uuid7()),
            "workflow_run_id": workflow_run_id,
            "session_id": f"meeting:{room_id}",
            "assistant_message_id": agent_message_id,
            "org_id": self._org_id,
            "user_id": self._user_id,
            "workspace": "meeting_room",
            "plan_tier": "basic",
            "capabilities": [],
            "query": query,
            "metadata": {
                "source": "meeting_room",
                "room_id": room_id,
                "meeting_agent_name": _MEETING_GENERAL_AGENT_NAME,
                "allowed_data_domains": allowed_domains,
                "user_role": self._role,
                "query": request.query,
                "attachments_count": len(attachment_echo),
            },
            "ext": {
                "surface": "chat",
                "allowed_modes": ["answer", "report"],
                "forbidden_modes": ["action"],
                "history_messages": self._meeting_history_messages(recent_messages),
                "inspection_context": inspection_context,
                "memory_sources": [item.model_dump(mode="json") for item in memory_sources],
                "meeting_context": {
                    "room_id": room_id,
                    "allowed_data_domains": allowed_domains,
                    "denied_data_domains": [domain for domain in self._normalize_domain_list(_ALL_DATA_DOMAINS) if domain not in allowed_domains],
                    "recent_messages": self._meeting_context_messages(recent_messages),
                    "business_binding": business_context.model_dump(mode="json"),
                },
            },
            "attachments": attachment_echo,
            "image_urls": [
                str(item.get("url") or "")
                for item in attachment_echo
                if str(item.get("kind") or "") == "image" and item.get("url")
            ],
        }
        if self._is_general_agent_cancelled(room_id, workflow_run_id):
            raise asyncio.CancelledError()
        router_output = await AgentManagerService().run_chat(payload, db_session=self._session)
        if self._is_general_agent_cancelled(room_id, workflow_run_id):
            raise asyncio.CancelledError()
        route_decision = router_output.route_decision
        agent_output = dict(router_output.agent_output or {})
        answer = self._agent_manager_answer(agent_output, router_output.status)
        selected_subgraph = str(route_decision.sub_route or "general_chat")
        message = await self._upsert_general_agent_message(
            room_id=room_id,
            message_id=agent_message_id,
            content=answer,
            metadata_json={
                "query": request.query,
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
                "inspection_context_snapshot": self._inspection_context_memory_snapshot(inspection_context),
                "memory_sources": [item.model_dump(mode="json") for item in memory_sources],
                "source_scope_refs": self._source_scope_refs(memory_sources),
                "conflict_ref_ids": [],
                "allowed_data_domains": access.allowed_domains,
                "denied_data_domains": access.denied_domains,
                "requested_data_domains": access.requested_domains,
                "denied_reasons": access.denied_reasons,
                **response_metadata,
                **({"attachment_echo": attachment_echo} if attachment_echo else {}),
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
            response_visibility=response_visibility,
        )
        await self._session.commit()
        await meeting_stream_broker.publish(
            room_id,
            {
                "event": "message_created",
                "room_id": room_id,
                "message": response_message.model_dump(),
                **({"private_user_ids": private_user_ids} if private_user_ids else {}),
            },
        )
        return MeetingAgentRunResponse(
            selected_subgraph=selected_subgraph,
            answer=answer,
            message=response_message,
            memory_sources=memory_sources,
            candidate_memories=[],
            response_visibility=response_visibility,
            escalation_required=False,
        )

    async def _build_meeting_inspection_context(self, room: Any | None = None) -> dict[str, Any]:
        try:
            user = await self._users.get_by_id(self._org_id, self._user_id)
            role = str(getattr(user, "role", "") or self._role or ROLE_USER)
            business_context = self._business_context_from_room(room)
            context = await ChatContextService(
                self._session,
                org_id=self._org_id,
                user_id=self._user_id,
                role=role,
            ).build_inspection_context(
                recent_limit=12,
                summary_window=24,
                selected_task_ids=business_context.task_ids,
            )
            if room is not None:
                context["meeting_business_context"] = business_context.model_dump(mode="json")
            return context
        except Exception:
            logger.debug("meeting inspection context build skipped", exc_info=True)
            return {}

    @staticmethod
    def _inspection_context_memory_snapshot(context: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(context, dict):
            return {}
        return {
            "stats": context.get("stats") if isinstance(context.get("stats"), dict) else {},
            "quality_insights": context.get("quality_insights") if isinstance(context.get("quality_insights"), dict) else {},
            "latest_task": MeetingService._inspection_task_memory_snapshot(context.get("latest_task")),
            "recent_failures": [
                item
                for item in (
                    MeetingService._inspection_task_memory_snapshot(raw)
                    for raw in list(context.get("recent_failures") or [])[:3]
                )
                if item
            ],
            "selected_tasks": [
                item
                for item in (
                    MeetingService._inspection_task_memory_snapshot(raw)
                    for raw in list(context.get("selected_tasks") or [])[:5]
                )
                if item
            ],
        }

    @staticmethod
    def _inspection_task_memory_snapshot(task: Any) -> dict[str, Any]:
        if not isinstance(task, dict):
            return {}
        keys = (
            "task_id",
            "product_id",
            "spec_code",
            "status",
            "verdict",
            "overall_score",
            "risk_level",
            "risk_score",
            "prompt_version",
            "model_key",
            "tokens_used",
            "latency_ms",
            "failed_rules",
            "root_cause",
            "defects",
            "defect_summary",
            "failure_reasons",
            "reasoning_summary",
            "manual_review",
            "created_at",
            "finished_at",
        )
        snapshot = {key: task.get(key) for key in keys if task.get(key) not in (None, "", [], {})}
        if isinstance(snapshot.get("defects"), list):
            snapshot["defects"] = list(snapshot["defects"])[:5]
        if isinstance(snapshot.get("failure_reasons"), list):
            snapshot["failure_reasons"] = [str(item)[:300] for item in list(snapshot["failure_reasons"])[:6]]
        return snapshot

    @staticmethod
    def _agent_manager_answer(agent_output: dict[str, Any], status: str) -> str:
        answer = str(agent_output.get("answer") or agent_output.get("summary") or "").strip()
        if answer:
            return answer
        if status == "blocked":
            return "当前请求被会议室边界阻止：会议室只负责只读问答和上下文整理，不能直接创建或执行正式质检任务。"
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
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ，。；:：?")
        return cleaned or str(query or "").strip()

    async def _collect_memory_sources(
        self,
        room_id: str,
        scope: MeetingMemoryScopeRequest,
        *,
        business_context: MeetingBusinessContext | None = None,
    ) -> list[MeetingMemorySourceResponse]:
        if not scope.include_confirmed:
            return []
        items_with_scope: list[tuple[MemoryItem, str]] = []
        if scope.include_meeting:
            room_items = await self._list_memory_items_for_room(
                org_id=self._org_id,
                room_id=room_id,
                business_context=(business_context or MeetingBusinessContext()).model_dump(mode="json"),
                include_confirmed=True,
                statuses=["confirmed", "active"],
                limit=5,
            )
            items_with_scope.extend((item, _MEMORY_SCOPE_MEETING_ROOM) for item in room_items)
        scope_pairs: list[tuple[str, str]] = []
        if scope.include_user or scope.include_personal_authorized:
            scope_pairs.append((_MEMORY_SCOPE_USER, self._user_id))
        if scope.include_agent:
            scope_pairs.append((_MEMORY_SCOPE_AGENT, _MEETING_GENERAL_AGENT_ID))
        if scope.include_org_space:
            scope_pairs.extend([
                (_MEMORY_SCOPE_ORG_SPACE, self._org_id),
                (_MEMORY_SCOPE_ORG_SPACE, "current"),
                (_MEMORY_SCOPE_ORG_SPACE, "org"),
                (_MEMORY_SCOPE_ORG_SPACE, "organization"),
            ])
        if scope_pairs:
            list_scoped = getattr(self._repo, "list_memory_items_for_scopes", None)
            scoped_items = await list_scoped(
                org_id=self._org_id,
                scope_pairs=scope_pairs,
                statuses=["confirmed", "active"],
                limit=15,
            ) if list_scoped else []
            for item in scoped_items:
                items_with_scope.append((item, self._memory_source_scope_for_item(item, scope_pairs)))
        items_with_scope = [
            (item, source_scope)
            for item, source_scope in items_with_scope
            if self._memory_is_retrievable(item)
        ]
        seen: set[str] = set()
        sources: list[MeetingMemorySourceResponse] = []
        for item, source_scope in sorted(
            items_with_scope,
            key=lambda pair: self._memory_updated_sort_value(pair[0]),
            reverse=True,
        ):
            memory_id = str(item.memory_id)
            if memory_id in seen:
                continue
            seen.add(memory_id)
            content_json = item.content_json or {}
            title = str(content_json.get("title") or item.content_summary or item.memory_id)
            sources.append(
                MeetingMemorySourceResponse(
                    memory_id=memory_id,
                    scope=source_scope,
                    title=title,
                    summary=str(item.content_summary or ""),
                )
            )
            if len(sources) >= 15:
                break
        return sources

    @staticmethod
    def _memory_updated_sort_value(item: MemoryItem) -> float:
        value = getattr(item, "updated_at", None)
        if hasattr(value, "timestamp"):
            return float(value.timestamp())
        if isinstance(value, (int, float)):
            return float(value)
        return 0.0

    @staticmethod
    def _memory_source_scope_for_item(item: MemoryItem, scope_pairs: list[tuple[str, str]]) -> str:
        normalized_pairs = {(str(scope_type), str(scope_id)) for scope_type, scope_id in scope_pairs}
        matched_scope_type = str(getattr(item, "_matched_scope_type", "") or "").strip()
        matched_scope_id = str(getattr(item, "_matched_scope_id", "") or "").strip()
        if matched_scope_type and matched_scope_id and (matched_scope_type, matched_scope_id) in normalized_pairs:
            return matched_scope_type
        content_json = item.content_json or {}
        target_scope_type = str(content_json.get("target_scope_type") or content_json.get("published_scope") or "").strip()
        target_scope_id = str(content_json.get("target_scope_id") or "").strip()
        if target_scope_type and target_scope_id and (target_scope_type, target_scope_id) in normalized_pairs:
            return target_scope_type
        scope_json = item.scope_json or {}
        scope_type = str(scope_json.get("scope_type") or "").strip()
        scope_id = str(scope_json.get("scope_id") or "").strip()
        if scope_type and scope_id and (scope_type, scope_id) in normalized_pairs:
            return scope_type
        if target_scope_type in {_MEMORY_SCOPE_USER, _MEMORY_SCOPE_AGENT, _MEMORY_SCOPE_ORG_SPACE}:
            return target_scope_type
        if scope_type in {_MEMORY_SCOPE_USER, _MEMORY_SCOPE_AGENT, _MEMORY_SCOPE_ORG_SPACE}:
            return scope_type
        return _MEMORY_SCOPE_MEETING_ROOM

    async def _call_build_meeting_inspection_context(self, room: Any | None = None) -> dict[str, Any]:
        try:
            return await self._build_meeting_inspection_context(room)
        except TypeError as exc:
            if "positional" not in str(exc) and "argument" not in str(exc):
                raise
            return await self._build_meeting_inspection_context()

    async def _list_memory_items_for_room(self, **kwargs) -> list[MemoryItem]:
        if not hasattr(self._repo, "list_memory_items_for_room"):
            return []
        try:
            items = await self._repo.list_memory_items_for_room(**kwargs)
        except TypeError as exc:
            if "business_context" not in str(exc):
                raise
            fallback = dict(kwargs)
            fallback.pop("business_context", None)
            items = await self._repo.list_memory_items_for_room(**fallback)
        return [item for item in items if self._memory_allowed_in_room_list(item)]

    @staticmethod
    def _memory_allowed_in_room_list(item: MemoryItem) -> bool:
        status = str(getattr(item, "status", "") or "")
        if status in {"isolated", "disabled", "deleted", "expired"}:
            return False
        content_json = getattr(item, "content_json", None) or {}
        if status in {"active", "confirmed"} and content_json.get("superseded_by"):
            return False
        return True

    @staticmethod
    def _memory_is_retrievable(item: MemoryItem) -> bool:
        if getattr(item, "deleted_at", None):
            return False
        status = str(getattr(item, "status", "") or "")
        return status in {"active", "confirmed"} and not (getattr(item, "content_json", None) or {}).get("superseded_by")

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
                "我是会议Agent，负责把会议室里的讨论整理成可执行、可追溯的结果。\n\n"
                "我现在可以做这些事：\n"
                "1. 回答你在会议里点名提出的问题。\n"
                "2. 基于当前会议内容生成会议纪要。\n"
                "3. 从讨论中提取候选记忆，等待确认后进入已确认记忆。\n"
                "4. 整理会议待办线索，辅助分配责任人和后续跟进。\n"
                "5. 根据会议上下文做检测风险、检测证据、标准解释的讨论型整理。\n\n"
                "如果当前会议带有任务、产品、批次或标准线索，我会把它们作为讨论和记忆召回的标签上下文。"
            )
        if selected_subgraph == "risk_forecast":
            return (
                "我先基于会议上下文和已确认记忆给出讨论型预测建议：\n"
                "1. 优先关注会议中被反复提及的产品、批次和缺陷类型。\n"
                "2. 对缺少检测任务或结果来源的结论标记为待核验。\n"
                "3. 后续接入 inspection_tasks / inspection_results 后，可以补充分数化风险排序。\n\n"
                f"本次查询：{query}\n"
                f"可用已确认记忆：\n{source_lines or '- 暂无已确认记忆'}"
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
                "我已根据会议内容生成候选记忆，等待用户确认后才会进入已确认记忆；原始会议聊天不会自动共享到其他会议室。\n\n"
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
            f"已确认记忆：\n{source_lines or '- 暂无'}\n\n"
            "可沉淀内容已生成候选记忆，请在右侧面板确认后再进入已确认记忆。"
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
        intent: str = "",
    ) -> list[MeetingCandidateMemoryResponse]:
        messages = await self._list_recent_messages(room_id=room_id, limit=80)
        room = await self._repo.get_room(self._org_id, room_id)
        business_context = self._business_context_from_room(room)
        candidate_entries = (
            self._risk_forecast_candidate_entries(messages, business_context, topic=topic, max_items=max_items)
            if intent == "risk_forecast"
            else self._candidate_entries_from_messages(messages, topic=topic, max_items=max_items)
        )
        results: list[MeetingCandidateMemoryResponse] = []
        existing = await self._list_memory_items_for_room(
            org_id=self._org_id,
            room_id=room_id,
            business_context=business_context.model_dump(mode="json"),
            include_confirmed=False,
            statuses=["candidate", "confirmed", "active", "disputed", "superseded"],
            limit=100,
        )
        existing_summaries = {str(item.content_summary or "").strip() for item in existing}
        existing_source_span_keys = self._existing_source_span_keys(existing)
        existing_dedupe: dict[str, str] = {}
        existing_terms: list[tuple[str, str, str]] = []
        for existing_item in existing:
            content_json = existing_item.content_json or {}
            dedupe_key = str(content_json.get("dedupe_key") or "").strip()
            if dedupe_key:
                existing_dedupe.setdefault(dedupe_key, str(existing_item.memory_id))
            text = f"{content_json.get('title') or ''}\n{content_json.get('content') or existing_item.content_summary or ''}".strip()
            terms = self._memory_signature_terms(text)
            if terms:
                existing_terms.append((str(existing_item.memory_id), dedupe_key, terms))
        for index, entry in enumerate(candidate_entries, 1):
            summary = str(entry.get("summary") or "").strip()
            if not summary or summary in existing_summaries:
                continue
            source_spans = list(entry.get("source_spans") or [])
            if source_spans and self._source_spans_seen(source_spans, existing_source_span_keys):
                continue
            memory_id = f"mem_meeting_{uuid.uuid4().hex[:12]}"
            content = self._candidate_detail_text(str(entry.get("content") or summary))
            if not self._candidate_has_memory_value(summary, content):
                continue
            title = self._memory_title_from_candidate(summary, content, index)
            source_message_id = str(entry.get("source_message_id") or "") or None
            memory_type = self._infer_candidate_memory_type(summary, content, intent=intent)
            structured_payload = self._candidate_structured_payload(
                memory_type,
                business_context,
                content,
                room_id=room_id,
                source_message_id=source_message_id,
                source_spans=source_spans,
            )
            object_resolution_status = str(structured_payload.get("object_resolution_status") or _OBJECT_RESOLUTION_UNRESOLVED)
            if object_resolution_status != _OBJECT_RESOLUTION_RESOLVED and memory_type in {_MEMORY_TYPE_RISK_INSIGHT, _MEMORY_TYPE_QUALITY_PATTERN}:
                structured_payload["object_resolution_status"] = _OBJECT_RESOLUTION_AMBIGUOUS if structured_payload.get("object_candidates") else _OBJECT_RESOLUTION_UNRESOLVED
            affected_context = self._business_context_from_affected_objects(
                structured_payload.get("affected_objects") if isinstance(structured_payload.get("affected_objects"), dict) else {}
            )
            effective_context = self._merge_business_context(business_context, affected_context)
            memory_category = self._classify_candidate_memory(summary, content, effective_context, memory_type=memory_type)
            recommended_scope, recommended_scope_id = self._recommend_memory_scope(
                memory_category,
                content,
                effective_context,
                memory_type=memory_type,
                affected_objects=structured_payload.get("affected_objects") if isinstance(structured_payload.get("affected_objects"), dict) else None,
                object_resolution_status=str(structured_payload.get("object_resolution_status") or _OBJECT_RESOLUTION_UNRESOLVED),
            )
            dedupe_key = self._candidate_dedupe_key(
                memory_type,
                content,
                structured_payload.get("affected_objects") if isinstance(structured_payload.get("affected_objects"), dict) else {},
            )
            related_memory_ids = self._related_memory_ids_for_candidate(
                dedupe_key,
                content,
                existing_dedupe,
                existing_terms,
            )
            if dedupe_key in existing_dedupe and not related_memory_ids:
                related_memory_ids = [existing_dedupe[dedupe_key]]
            value_score = self._candidate_value_score(content, memory_type, structured_payload)
            if value_score < 0.42:
                continue
            source_refs = self._candidate_source_refs(room_id, source_message_id)
            for ref in structured_payload.get("evidence_refs") or []:
                if ref not in source_refs:
                    source_refs.append(ref)
            shareability = self._memory_shareability(
                memory_category,
                effective_context,
                memory_type=memory_type,
                object_resolution_status=str(structured_payload.get("object_resolution_status") or _OBJECT_RESOLUTION_UNRESOLVED),
            )
            if related_memory_ids:
                shareability["possible_duplicate"] = bool(dedupe_key in existing_dedupe)
                shareability["related_memory_ids"] = related_memory_ids
            warnings = self._candidate_warnings(
                memory_category,
                content,
                memory_type=memory_type,
                business_context=effective_context,
                object_resolution_status=str(structured_payload.get("object_resolution_status") or _OBJECT_RESOLUTION_UNRESOLVED),
                related_memory_ids=related_memory_ids,
            )
            if memory_type == _MEMORY_TYPE_RISK_INSIGHT:
                shareability["risk_forecast_requires_confirmation"] = True
            qdl_json = self._memory_qdl_json(memory_type, title, content, structured_payload)
            item = MemoryItem(
                id=str(uuid7()),
                memory_id=memory_id,
                org_id=self._org_id,
                user_id=None,
                memory_type="task_episode",
                scope_json={
                    "meeting_room_id": room_id,
                    "room_id": room_id,
                    "scope_type": "meeting_room",
                    "scope_id": room_id,
                    "business_context": business_context.model_dump(mode="json"),
                    "task_ids": business_context.task_ids,
                    "product_ids": business_context.product_ids,
                    "batch_nos": business_context.batch_nos,
                    "standard_ids": business_context.standard_ids,
                },
                content_summary=summary,
                content_json={
                    "title": title,
                    "content": content,
                    "memory_type": memory_type,
                    "memory_category": memory_category,
                    "recommended_scope": recommended_scope,
                    "recommended_scope_id": recommended_scope_id,
                    "shareability": shareability,
                    "warnings": warnings,
                    "source_refs": source_refs,
                    "source_type": "meeting",
                    "source_id": room_id,
                    "source_message_id": source_message_id,
                    "business_context": business_context.model_dump(mode="json"),
                    "source_spans": source_spans,
                    "object_resolution_status": structured_payload.get("object_resolution_status"),
                    "object_candidates": structured_payload.get("object_candidates") or [],
                    "value_score": value_score,
                    "dedupe_key": dedupe_key,
                    "related_memory_ids": related_memory_ids,
                    "extraction_reason": self._candidate_extraction_reason(memory_type, content, structured_payload, value_score),
                    "qdl_json": qdl_json,
                    **structured_payload,
                },
                source_event_ids=[source_message_id] if source_message_id else None,
                evidence_pointers={
                    "meeting_room_id": room_id,
                    "source_message_id": source_message_id,
                    "source_refs": source_refs,
                },
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
                to_scope_type="meeting_room",
                to_scope_id=room_id,
                transfer_reason="会议Agent从会议上下文提取候选记忆",
                status="candidate",
                operator_id=self._user_id,
            )
            results.append(
                MeetingCandidateMemoryResponse(
                    memory_id=memory_id,
                    title=title,
                    content=content,
                    summary=summary,
                    memory_type=memory_type,
                    status="candidate",
                    memory_category=memory_category,
                    recommended_scope=recommended_scope,
                    recommended_scope_id=recommended_scope_id,
                    source_refs=source_refs,
                    business_context=business_context.model_dump(mode="json"),
                    shareability=shareability,
                    warnings=warnings,
                    affected_objects=structured_payload.get("affected_objects"),
                    evidence_refs=list(structured_payload.get("evidence_refs") or []),
                    forecast_window=structured_payload.get("forecast_window"),
                    risk_level=structured_payload.get("risk_level"),
                    recommended_actions=[str(item) for item in list(structured_payload.get("recommended_actions") or [])],
                    source_room_id=room_id,
                    source_spans=source_spans,
                    object_resolution_status=str(structured_payload.get("object_resolution_status") or _OBJECT_RESOLUTION_UNRESOLVED),
                    object_candidates=list(structured_payload.get("object_candidates") or []),
                    value_score=value_score,
                    dedupe_key=dedupe_key,
                    related_memory_ids=related_memory_ids,
                    extraction_reason=self._candidate_extraction_reason(memory_type, content, structured_payload, value_score),
                    confidence=max(0.35, min(0.92, value_score)),
                    source_message_id=source_message_id,
                    qdl_json=qdl_json,
                    created_at=item.created_at,
                )
            )
            await self._record_meeting_memory_event(
                event_type=EventType.MEMORY_CANDIDATE_CREATED,
                memory_id=memory_id,
                room_id=room_id,
                payload={
                    "action": "candidate_created",
                    "memory_category": memory_category,
                    "recommended_scope": recommended_scope,
                    "recommended_scope_id": recommended_scope_id,
                    "source_refs": source_refs,
                    "business_context": business_context.model_dump(mode="json"),
                    "shareability": shareability,
                    "warnings": warnings,
                    "source_spans": source_spans,
                    "dedupe_key": dedupe_key,
                    "related_memory_ids": related_memory_ids,
                    "value_score": value_score,
                },
            )
        return results

    @staticmethod
    def _candidate_entries_from_messages(messages: list[Any], *, topic: str, max_items: int) -> list[dict[str, Any]]:
        keywords = (
            "确认",
            "结论",
            "决定",
            "风险",
            "需要",
            "建议",
            "复核",
            "行动",
            "待办",
            "标准",
            "检测",
            "质检",
            "产品",
            "批次",
            "不合格",
            "问题模式",
        )
        entries: list[dict[str, Any]] = []
        message_order = {str(getattr(msg, "id", "") or ""): index for index, msg in enumerate(messages)}
        for msg in reversed(messages):
            message_type = str(getattr(msg, "message_type", "user"))
            if message_type not in {"user", "agent", "summary", "action_item"}:
                continue
            raw_content = str(getattr(msg, "content", "") or "").strip()
            detail_text = MeetingService._candidate_detail_text(raw_content)
            if message_type == "agent":
                detail_text = MeetingService._agent_quality_candidate_text(detail_text, msg)
            if not detail_text or MeetingService._is_low_value_memory_text(detail_text):
                continue
            if message_type == "user" and raw_content.startswith("@"):
                continue
            if message_type == "agent" and not MeetingService._is_agent_quality_memory_text(detail_text, msg):
                continue
            message_id = str(getattr(msg, "id", "") or "") or None
            if message_type in {"summary", "agent"}:
                spans = [
                    {
                        "type": "meeting_message_span",
                        "message_id": message_id,
                        "span_index": 1,
                        "start": 0,
                        "end": len(detail_text),
                        "text": detail_text[:600],
                    }
                ]
            else:
                spans = MeetingService._split_candidate_spans(detail_text, message_id=message_id)
            for span in spans:
                content = re.sub(r"\s+", " ", str(span.get("text") or ""))
                if not content or MeetingService._is_low_value_memory_text(content):
                    continue
                if not (any(keyword in content for keyword in keywords) or (topic and topic[:12] in content) or MeetingService._candidate_has_memory_value(content, content)):
                    continue
                entry_content = detail_text if message_type == "summary" else content
                entries.append(
                    {
                        "summary": content[:260],
                        "content": entry_content,
                        "source_message_id": str(getattr(msg, "id", "") or "") or None,
                        "source_spans": [span],
                        "_order": message_order.get(str(getattr(msg, "id", "") or ""), 0),
                        "_span_index": int(span.get("span_index") or 0),
                    }
                )
                if len(entries) >= max_items:
                    break
            if len(entries) >= max_items:
                break
        if not entries:
            fallback_blocks: list[tuple[str, str | None]] = []
            for msg in messages[-5:]:
                cleaned = MeetingService._candidate_detail_text(str(getattr(msg, "content", "") or "").strip())
                if not cleaned or MeetingService._is_low_value_memory_text(cleaned):
                    continue
                fallback_blocks.append((cleaned, str(getattr(msg, "id", "") or "") or None))
            compact = "；".join(
                re.sub(r"\s+", " ", block).strip()[:120]
                for block, _ in fallback_blocks
                if block
            )
            if compact and fallback_blocks:
                entries.append(
                    {
                        "summary": f"会议待确认结论：{compact[:260]}",
                        "content": "\n\n".join(block for block, _ in fallback_blocks),
                        "source_message_id": next((message_id for _, message_id in reversed(fallback_blocks) if message_id), None)
                        or MeetingService._latest_user_message_id(messages),
                    }
                )
                return entries[:max_items]
        return entries[:max_items]

    @staticmethod
    def _candidate_detail_text(content: str, limit: int = 4000) -> str:
        normalized = str(content or "").replace("\r\n", "\n").strip()
        if not normalized:
            return ""
        noise_patterns = (
            r"^\s*一条候选记忆已被拒绝.*$",
            r"^\s*候选记忆已被拒绝.*$",
            r"^\s*用户拒绝候选记忆.*$",
            r"^\s*拒绝理由[：:].*$",
            r"^\s*待人工审核\s*$",
            r"^\s*建议范围[：:].*$",
            r"^\s*当前会议室作用范围[：:].*$",
            r"^\s*当前会议室的作用范围.*$",
            r"^\s*参与角色[：:].*$",
        )
        cleaned_lines = [
            line.strip()
            for line in normalized.split("\n")
            if line.strip() and not any(re.match(pattern, line.strip(), flags=re.IGNORECASE) for pattern in noise_patterns)
        ]
        normalized = "\n".join(cleaned_lines).strip()
        if not normalized:
            return ""
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        if len(normalized) <= limit:
            return normalized
        return f"{normalized[: max(limit - 3, 0)].rstrip()}..."

    @staticmethod
    def _is_low_value_memory_text(content: str) -> bool:
        text = re.sub(r"\s+", "", str(content or "")).lower()
        if not text:
            return True
        low_value_terms = {
            "收到",
            "好的",
            "可以",
            "谢谢",
            "辛苦",
            "哈哈",
            "测试",
            "先这样",
            "没问题",
            "ok",
            "hello",
            "hi",
        }
        if text in low_value_terms:
            return True
        if len(text) <= 8 and not any(term in text for term in ("质检", "检测", "产品", "批次", "任务", "风险", "标准")):
            return True
        if text.endswith(("吗", "么", "？", "?")) and not any(term in text for term in ("需要", "建议", "风险", "不合格", "结论")):
            return True
        if any(term in text for term in ("候选记忆已拒绝", "一条候选记忆已被拒绝", "会议agent正在")):
            return True
        return False

    @staticmethod
    def _is_agent_quality_memory_text(content: str, message: Any | None = None) -> bool:
        text = str(content or "")
        compact = re.sub(r"\s+", "", text).lower()
        if not any(term in compact for term in ("质检", "检测", "不合格", "人工复核", "manual_required", "评分", "失败", "风险", "产品", "批次", "规格")):
            return False
        objects = MeetingService._extract_object_refs_from_text(text)
        has_object = any(objects.get(key) for key in ("inspection_task_ids", "product_ids", "batch_nos", "standard_ids"))
        quality_route = MeetingService._is_agent_quality_route_message(message)
        has_context_task = bool(MeetingService._quality_context_task_from_message(message))
        has_quality_fact = any(
            term in compact
            for term in (
                "manual_required",
                "需人工复核",
                "不合格",
                "未通过",
                "失败原因",
                "复核原因",
                "缺陷",
                "surface_scratch",
                "评分",
                "得分",
                "风险",
                "模型",
                "prompt",
                "耗时",
            )
        )
        if quality_route:
            return (has_object or has_context_task) and has_quality_fact
        return has_object and MeetingService._candidate_has_memory_value(text[:260], text)

    @staticmethod
    def _message_metadata(message: Any | None) -> dict[str, Any]:
        metadata = getattr(message, "metadata_json", None) if message is not None else None
        return metadata if isinstance(metadata, dict) else {}

    @staticmethod
    def _is_agent_quality_route_message(message: Any | None) -> bool:
        metadata = MeetingService._message_metadata(message)
        selected_subgraph = str(metadata.get("selected_subgraph") or metadata.get("intent") or "")
        message_type = str(metadata.get("message_type") or "")
        return selected_subgraph in {"quality_task_status", "evidence_query", "image_understanding", "risk_forecast"} or message_type in {
            "task_status",
            "report_answer",
            "image_analysis",
        }

    @staticmethod
    def _quality_context_task_from_message(message: Any | None) -> dict[str, Any]:
        metadata = MeetingService._message_metadata(message)
        snapshot = metadata.get("inspection_context_snapshot")
        if not isinstance(snapshot, dict):
            snapshot = metadata.get("inspection_context")
        if not isinstance(snapshot, dict):
            return {}
        latest_task = snapshot.get("latest_task")
        if isinstance(latest_task, dict) and latest_task:
            return latest_task
        selected_tasks = snapshot.get("selected_tasks")
        if isinstance(selected_tasks, list):
            for item in selected_tasks:
                if isinstance(item, dict) and item:
                    return item
        recent_failures = snapshot.get("recent_failures")
        if isinstance(recent_failures, list):
            for item in recent_failures:
                if isinstance(item, dict) and item:
                    return item
        return {}

    @staticmethod
    def _agent_quality_candidate_text(content: str, message: Any | None) -> str:
        text = str(content or "").strip()
        if not MeetingService._is_agent_quality_route_message(message):
            return text
        task = MeetingService._quality_context_task_from_message(message)
        if not task:
            return text
        context_text = MeetingService._inspection_task_context_text(task)
        if not context_text:
            return text
        compact_text = re.sub(r"\s+", "", text).lower()
        task_id = str(task.get("task_id") or "").strip()
        if task_id and task_id.lower() in compact_text and str(task.get("defect_summary") or "").strip() in text:
            return text
        return f"{text}\n质检结果上下文：{context_text}".strip()

    @staticmethod
    def _inspection_task_context_text(task: dict[str, Any]) -> str:
        parts: list[str] = []
        task_id = str(task.get("task_id") or "").strip()
        product_id = str(task.get("product_id") or "").strip()
        spec_code = str(task.get("spec_code") or "").strip()
        if task_id:
            parts.append(f"质检任务 {task_id}")
        if product_id:
            parts.append(f"产品 {product_id}")
        if spec_code:
            parts.append(f"规格 {spec_code}")
        status = str(task.get("status") or "").strip()
        verdict = str(task.get("verdict") or "").strip()
        if status or verdict:
            parts.append(f"状态/判定 {status or '-'} / {verdict or '-'}")
        score = task.get("overall_score")
        if score is not None:
            parts.append(f"得分 {score}")
        defect_summary = str(task.get("defect_summary") or "").strip()
        if defect_summary:
            parts.append(f"缺陷明细 {defect_summary}")
        failure_reasons = [str(item).strip() for item in list(task.get("failure_reasons") or []) if str(item).strip()]
        if failure_reasons:
            parts.append("失败/复核原因 " + "；".join(failure_reasons[:3]))
        failed_rules = [str(item).strip() for item in list(task.get("failed_rules") or []) if str(item).strip()]
        if failed_rules:
            parts.append("规则/阈值 " + "、".join(failed_rules[:4]))
        model_key = str(task.get("model_key") or "").strip()
        prompt_version = str(task.get("prompt_version") or "").strip()
        if model_key or prompt_version:
            parts.append(f"模型 {model_key or '-'}，Prompt {prompt_version or '-'}")
        latency_ms = task.get("latency_ms")
        if latency_ms is not None:
            parts.append(f"耗时 {latency_ms}ms")
        return "；".join(parts)[:1800]

    @staticmethod
    def _split_candidate_spans(content: str, *, message_id: str | None = None) -> list[dict[str, Any]]:
        text = str(content or "").replace("\r\n", "\n").strip()
        if not text:
            return []
        raw_parts = [
            item.strip()
            for item in re.split(
                r"\n+|(?<=[。！？；;?])",
                text,
            )
            if item and item.strip()
        ]
        spans: list[dict[str, Any]] = []
        cursor = 0
        for idx, part in enumerate(raw_parts, 1):
            clean = part.strip(" ；。")
            if not clean or MeetingService._is_low_value_memory_text(clean):
                cursor += len(part)
                continue
            start = text.find(part, cursor)
            if start < 0:
                start = cursor
            end = start + len(part)
            cursor = end
            spans.append(
                {
                    "type": "meeting_message_span",
                    "message_id": message_id,
                    "span_index": idx,
                    "start": start,
                    "end": end,
                    "text": clean[:600],
                }
            )
        return spans

    @staticmethod
    def _memory_title_from_line(line: str, index: int) -> str:
        compact = re.sub(r"[。！？；;,.，\s]+", " ", line).strip()
        return (compact[:36] or f"会议候选记忆 {index}").strip()

    @staticmethod
    def _memory_title_from_candidate(summary: str, content: str, index: int) -> str:
        source = MeetingService._candidate_title_source(content or summary)
        rule_title = MeetingService._domain_memory_title(source)
        if rule_title:
            return rule_title[:36].strip()

        fallback = MeetingService._candidate_title_source(summary or content)
        compact_content = MeetingService._candidate_title_source(content or summary)
        title = MeetingService._memory_title_from_line(fallback, index)
        if title and _normalize_name(title) != _normalize_name(compact_content):
            return title

        clauses = [
            clause.strip()
            for clause in re.split(r"[。！？；;?\n]+", compact_content)
            if clause.strip()
        ]
        for clause in clauses:
            cleaned = MeetingService._clean_candidate_title_clause(clause)
            if 4 <= len(cleaned) <= 28 and _normalize_name(cleaned) != _normalize_name(compact_content):
                return cleaned
        return title or f"会议候选记忆 {index}"

    @staticmethod
    def _candidate_title_source(value: str) -> str:
        text = str(value or "").replace("\r\n", "\n").strip()
        text = re.sub(r"^@\S+\s*", "", text)
        text = re.sub(
            r"^\s*(会议形成待确认结论|会议待确认结论|会议结论|候选记忆|风险洞察候选|行动项|建议)\s*[：:]\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"\s+", " ", text).strip()
        return text[:500]

    @staticmethod
    def _domain_memory_title(text: str) -> str:
        normalized = re.sub(r"\s+", "", str(text or "")).lower()
        object_label = MeetingService._candidate_title_object_label(text)
        if "边缘识别" in normalized and any(term in normalized for term in ("光照", "照明", "亮度")):
            return f"{object_label}边缘识别需加强光照条件".strip()
        if ("质检" in normalized or "检测" in normalized) and ("不合格" in normalized or "fail" in normalized):
            return f"{object_label}质检不合格".strip()
        if "抽检" in normalized and any(term in normalized for term in ("风险上升", "风险升高", "风险增加")):
            return f"{object_label}抽检风险上升".strip()
        if "复测" in normalized and any(term in normalized for term in ("不稳定", "失败", "异常")):
            return f"{object_label}复测稳定性风险".strip()
        if "复核" in normalized and ("任务" in normalized or "质检" in normalized or "检测" in normalized):
            return f"{object_label}质检任务需复核".strip()
        if "标准" in normalized and any(term in normalized for term in ("复核", "调整", "阈值", "口径")):
            return f"{object_label}质检标准需复核".strip()
        if "风险" in normalized and any(term in normalized for term in ("预测", "预警", "未来", "后续")):
            return f"{object_label}质检风险需关注".strip()
        return ""

    @staticmethod
    def _candidate_title_object_label(text: str) -> str:
        text_value = str(text or "")
        patterns = (
            r"产品\s*([A-Za-z0-9][A-Za-z0-9_-]{1,31})",
            r"\b([A-Z][A-Z0-9_-]{2,31})\s*产品",
            r"批次\s*([A-Za-z0-9][A-Za-z0-9_-]{1,31})",
            r"\b([A-Z][A-Z0-9_-]{2,31})\s*批次",
            r"质检任务\s*([A-Za-z0-9][A-Za-z0-9_-]{1,36})",
            r"任务\s*([A-Za-z0-9][A-Za-z0-9_-]{1,36})",
        )
        for pattern in patterns:
            match = re.search(pattern, text_value, flags=re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                if value.lower() not in {"fail", "pass", "true", "false"}:
                    return f"{value} "
        return ""

    @staticmethod
    def _clean_candidate_title_clause(clause: str) -> str:
        cleaned = str(clause or "").strip()
        cleaned = re.sub(
            r"^\s*(该产品|这个产品|本产品|当前产品|该批次|这个批次|本批次)\s*",
            "",
            cleaned,
        )
        cleaned = re.sub(r"^\s*(需要|应该|建议|请|后续)\s*", "", cleaned)
        cleaned = cleaned.replace("注意", "关注", 1)
        return re.sub(r"\s+", " ", cleaned).strip()[:36]

    @staticmethod
    def _latest_user_message_id(messages: list[Any]) -> str | None:
        for msg in reversed(messages):
            if str(getattr(msg, "message_type", "")) == "user":
                return str(getattr(msg, "id", "") or "") or None
        return None

    @staticmethod
    def _candidate_source_refs(room_id: str, source_message_id: str | None) -> list[dict]:
        refs = [{"type": "meeting_room", "id": room_id}]
        if source_message_id:
            refs.append({"type": "meeting_message", "id": source_message_id})
        return refs

    @staticmethod
    def _candidate_has_memory_value(summary: str, content: str) -> bool:
        text = f"{summary}\n{content}".strip()
        if MeetingService._is_low_value_memory_text(text):
            return False
        compact = re.sub(r"\s+", "", text).lower()
        value_terms = (
            "结论",
            "决定",
            "需要",
            "建议",
            "应该",
            "风险",
            "不合格",
            "合格",
            "复核",
            "缺陷",
            "问题模式",
            "反复",
            "批次",
            "产品",
            "质检",
            "检测",
            "标准",
            "阈值",
            "行动项",
            "待办",
            "fail",
            "risk",
            "quality",
            "batch",
            "product",
        )
        return any(term in compact for term in value_terms)

    @staticmethod
    def _extract_object_refs_from_text(text: str) -> dict[str, list[str]]:
        raw = str(text or "")
        product_ids: list[str] = []
        batch_nos: list[str] = []
        task_ids: list[str] = []
        standard_ids: list[str] = []

        uuid_re = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
        patterns = [
            ("task_ids", rf"(?:质检任务|任务|task)\s*[:：-]?\s*({uuid_re}|[A-Za-z][A-Za-z0-9_-]{{2,40}})"),
            ("product_ids", r"(?:产品|product|SKU|sku)\s*[:：-]?\s*([A-Za-z][A-Za-z0-9_-]{1,40})"),
            ("batch_nos", r"(?:批次|batch|批号)\s*[:：-]?\s*([A-Za-z][A-Za-z0-9_-]{1,40})"),
            ("standard_ids", r"(?:标准|规则|规格|standard|spec|spec_code)\s*[:：-]?\s*([A-Za-z][A-Za-z0-9_.-]{1,40})"),
        ]
        for target, pattern in patterns:
            for match in re.finditer(pattern, raw, flags=re.IGNORECASE):
                value = match.group(1).strip(" ：。；;")
                if value.lower() in {"fail", "pass", "true", "false", "risk", "quality", "product", "batch", "task"}:
                    continue
                if target == "task_ids":
                    task_ids.append(value)
                elif target == "product_ids":
                    product_ids.append(value)
                elif target == "batch_nos":
                    batch_nos.append(value)
                elif target == "standard_ids":
                    standard_ids.append(value)

        product_code_re = r"\b(P(?:[-_][A-Za-z0-9][A-Za-z0-9_-]{1,39}|[0-9][A-Za-z0-9_-]{1,39}|[A-Z0-9]{2,40}))\b"
        batch_code_re = r"\b(B(?:[-_][A-Za-z0-9][A-Za-z0-9_-]{1,39}|[0-9][A-Za-z0-9_-]{1,39}|[A-Z0-9]{2,40}))\b"
        for match in re.finditer(product_code_re, raw):
            product_ids.append(match.group(1))
        for match in re.finditer(batch_code_re, raw):
            value = match.group(1)
            tail = raw[match.end(): match.end() + 4]
            if tail.startswith("产品"):
                continue
            batch_nos.append(value)
        for match in re.finditer(uuid_re, raw):
            task_ids.append(match.group(0))

        return {
            "inspection_task_ids": MeetingService._dedupe_text_values(task_ids, limit=10),
            "product_ids": MeetingService._dedupe_text_values(product_ids, limit=10),
            "batch_nos": MeetingService._dedupe_text_values(batch_nos, limit=10),
            "standard_ids": MeetingService._dedupe_text_values(standard_ids, limit=10),
        }

    @staticmethod
    def _risk_forecast_candidate_entries(
        messages: list[Any],
        business_context: MeetingBusinessContext,
        *,
        topic: str,
        max_items: int,
    ) -> list[dict[str, Any]]:
        source_message_id = MeetingService._latest_user_message_id(messages)
        recent_blocks: list[str] = []
        for msg in messages[-12:]:
            if str(getattr(msg, "message_type", "user")) not in {"user", "summary", "action_item"}:
                continue
            cleaned = MeetingService._candidate_detail_text(str(getattr(msg, "content", "") or "").strip(), limit=600)
            if not cleaned or cleaned.startswith("@"):
                continue
            recent_blocks.append(re.sub(r"\s+", " ", cleaned).strip())
        context_bits: list[str] = []
        if business_context.product_ids:
            context_bits.append(f"产品 {', '.join(business_context.product_ids[:3])}")
        if business_context.batch_nos:
            context_bits.append(f"批次 {', '.join(business_context.batch_nos[:3])}")
        if business_context.task_ids:
            context_bits.append(f"质检任务 {', '.join(business_context.task_ids[:3])}")
        if business_context.standard_ids:
            context_bits.append(f"标准 {', '.join(business_context.standard_ids[:3])}")
        target_text = "、".join(context_bits) or "当前会议室讨论对象"
        evidence_text = "；".join(recent_blocks[-5:]) or str(topic or "暂无足够会议上下文").strip()
        if business_context.product_ids or business_context.batch_nos or business_context.task_ids:
            summary = f"风险洞察候选：{target_text} 近期存在需关注的质检风险"
            content = (
                f"风险洞察候选：基于当前会议讨论和业务标签线索，{target_text} 近期存在需关注的质检风险。\n"
                f"数据来源：当前会议上下文、已确认记忆和业务标签线索。\n"
                f"问题模式：会议中反复出现的质检失败、复核、批次、产品或缺陷线索需要合并观察。\n"
                f"触发条件：多次检测异常、复测不稳定、同批次/同产品问题集中出现，或会议成员持续提示风险。\n"
                f"建议关注窗口：未来 7-14 天。\n"
                f"建议动作：优先复核相关质检任务，跟踪失败率、复测结论和同类问题是否继续出现。\n"
                f"证据摘要：{evidence_text[:900]}"
            )
        else:
            summary = "风险洞察候选：当前会议讨论存在待核验风险线索"
            content = (
                "风险洞察候选：当前会议讨论存在待核验风险线索，但尚未识别稳定的任务、产品或批次标签。\n"
                "数据来源：当前会议上下文。\n"
                "问题模式：需要先补充业务标签线索后，才能提高后续检索和复用准确性。\n"
                "建议关注窗口：未来 7-14 天。\n"
                "建议动作：可先沉淀到当前会议室；需要协同时再共享给成员、其他会议室、Agent 或组织共享空间。\n"
                f"证据摘要：{evidence_text[:900]}"
            )
        return [
            {
                "summary": summary[:260],
                "content": content,
                "source_message_id": source_message_id,
            }
        ][:max_items]

    @staticmethod
    def _infer_candidate_memory_type(summary: str, content: str, *, intent: str = "") -> str:
        text = f"{summary}\n{content}".lower()
        if intent == "risk_forecast" or any(term in text for term in ("风险洞察", "预测", "预警", "未来", "risk forecast")):
            return _MEMORY_TYPE_RISK_INSIGHT
        if any(term in text for term in ("问题模式", "反复出现", "集中出现", "常见失败", "quality pattern")):
            return _MEMORY_TYPE_QUALITY_PATTERN
        if any(term in text for term in ("行动项", "待办", "责任人", "建议动作", "action")):
            return _MEMORY_TYPE_ACTION_SUGGESTION
        if any(term in text for term in ("质检", "检测", "评分", "不合格", "合格", "耗时", "模型", "inspection", "quality")):
            return _MEMORY_TYPE_QUALITY_FACT
        return "decision"

    @staticmethod
    def _candidate_structured_payload(
        memory_type: str,
        business_context: MeetingBusinessContext,
        content: str,
        *,
        room_id: str,
        source_message_id: str | None,
        source_spans: list[dict] | None = None,
    ) -> dict[str, Any]:
        text_objects = MeetingService._extract_object_refs_from_text(content)
        affected_objects = {key: list(values) for key, values in text_objects.items()}
        explicit_count = sum(1 for values in text_objects.values() if values)
        has_context_pool = bool(
            business_context.task_ids
            or business_context.product_ids
            or business_context.batch_nos
            or business_context.standard_ids
        )
        object_candidates = MeetingService._object_candidates_from_context(business_context, text_objects)
        if explicit_count:
            object_resolution_status = _OBJECT_RESOLUTION_RESOLVED
        else:
            pronoun_targets = MeetingService._context_object_keys_from_deictic_text(content)
            if pronoun_targets:
                for key in pronoun_targets:
                    context_values = {
                        "inspection_task_ids": business_context.task_ids,
                        "product_ids": business_context.product_ids,
                        "batch_nos": business_context.batch_nos,
                        "standard_ids": business_context.standard_ids,
                    }.get(key, [])
                    if len(context_values) == 1:
                        affected_objects[key] = MeetingService._dedupe_text_values(context_values, limit=20)
                if any(affected_objects.values()):
                    object_resolution_status = _OBJECT_RESOLUTION_RESOLVED
                elif has_context_pool:
                    object_resolution_status = _OBJECT_RESOLUTION_AMBIGUOUS
                else:
                    object_resolution_status = _OBJECT_RESOLUTION_UNRESOLVED
            elif has_context_pool:
                object_resolution_status = _OBJECT_RESOLUTION_AMBIGUOUS
            else:
                object_resolution_status = _OBJECT_RESOLUTION_UNRESOLVED
        clean_spans = list(source_spans or [])
        payload: dict[str, Any] = {
            "affected_objects": affected_objects,
            "evidence_refs": [
                item
                for item in [
                    {"type": "meeting_room", "id": room_id},
                    {"type": "meeting_message", "id": source_message_id} if source_message_id else None,
                ]
                if item
            ],
            "source_room_id": room_id,
            "source_spans": clean_spans,
            "object_resolution_status": object_resolution_status,
            "object_candidates": object_candidates,
        }
        if memory_type == _MEMORY_TYPE_RISK_INSIGHT:
            payload.update(
                {
                    "forecast_window": {"label": "未来 7-14 天", "days_min": 7, "days_max": 14},
                    "risk_level": MeetingService._risk_level_from_text(content),
                    "recommended_actions": [
                        "复核相关质检任务和失败样本",
                        "跟踪同产品或同批次复测结果",
                        "必要时通过协作消息分派后续处理",
                    ],
                }
            )
        return payload

    @staticmethod
    def _memory_qdl_json(
        memory_type: str,
        title: str,
        content: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = payload or {}
        evidence_refs = list(payload.get("evidence_refs") or payload.get("source_refs") or [])
        affected_objects = payload.get("affected_objects") if isinstance(payload.get("affected_objects"), dict) else {}
        risk = {
            "level": payload.get("risk_level"),
            "forecast_window": payload.get("forecast_window"),
            "recommended_actions": list(payload.get("recommended_actions") or []),
        }
        if not any(risk.values()):
            risk = {}
        return {
            "version": "qdl-json-v1",
            "claim": {
                "title": str(title or "会议记忆"),
                "text": str(content or ""),
                "type": str(memory_type or "decision"),
            },
            "evidence": evidence_refs,
            "risk": risk,
            "rule": {
                "scope_policy": "memory_scope_only",
                "business_objects": "tags_only",
            },
            "conflict": {
                "status": "open" if payload.get("conflicting_memory_id") else "none",
                "related_memory_ids": list(payload.get("related_memory_ids") or []),
                "conflicting_memory_id": payload.get("conflicting_memory_id"),
            },
            "consensus": {
                "status": "candidate" if not payload.get("confirmed_at") else "confirmed",
                "confirmed_by": payload.get("confirmed_by"),
                "confirmed_at": payload.get("confirmed_at"),
            },
            "concept": {
                "name": str(title or "会议概念"),
                "kind": str(memory_type or "decision"),
                "tags": affected_objects,
            },
        }

    @staticmethod
    def _risk_level_from_text(content: str) -> str:
        text = str(content or "").lower()
        if any(term in text for term in ("严重", "critical", "高风险", "连续不合格", "集中失败")):
            return "high"
        if any(term in text for term in ("待核验", "缺少", "未绑定", "不足")):
            return "medium"
        return "medium"

    @staticmethod
    def _object_candidates_from_context(
        business_context: MeetingBusinessContext,
        text_objects: dict[str, list[str]],
    ) -> list[dict[str, str]]:
        candidates: list[dict[str, str]] = []
        mapping = [
            ("inspection_task", "inspection_task_ids", business_context.task_ids),
            ("product", "product_ids", business_context.product_ids),
            ("batch", "batch_nos", business_context.batch_nos),
            ("standard", "standard_ids", business_context.standard_ids),
        ]
        for object_type, key, context_values in mapping:
            values = MeetingService._dedupe_text_values([*(text_objects.get(key) or []), *list(context_values or [])], limit=10)
            for value in values:
                candidates.append({"type": object_type, "id": value})
        return candidates

    @staticmethod
    def _context_object_keys_from_deictic_text(content: str) -> set[str]:
        text = re.sub(r"\s+", "", str(content or "")).lower()
        keys: set[str] = set()
        if any(term in text for term in ("这个产品", "该产品", "当前产品", "同一产品", "这个sku", "该sku")):
            keys.add("product_ids")
        if any(term in text for term in ("这个批次", "该批次", "当前批次", "同一批次", "这批", "该批")):
            keys.add("batch_nos")
        if any(term in text for term in ("这个任务", "该任务", "当前任务", "最近一次质检", "这次质检", "本次质检", "该质检任务")):
            keys.add("inspection_task_ids")
        if any(term in text for term in ("这个标准", "该标准", "当前标准", "这条规则", "该规则", "这个规则")):
            keys.add("standard_ids")
        return keys

    @staticmethod
    def _candidate_dedupe_key(memory_type: str, content: str, affected_objects: dict) -> str:
        object_parts: list[str] = []
        for key, label in (
            ("inspection_task_ids", "task"),
            ("product_ids", "product"),
            ("batch_nos", "batch"),
            ("standard_ids", "standard"),
        ):
            values = [str(item) for item in list((affected_objects or {}).get(key) or []) if str(item).strip()]
            if values:
                object_parts.append(f"{label}:{','.join(sorted(values)[:3])}")
        terms = MeetingService._memory_signature_terms(content)
        pattern = ",".join(terms[:5]) or _normalize_name(content)[:36]
        return "|".join([str(memory_type or "decision"), *object_parts, f"pattern:{pattern}"])[:240]

    @staticmethod
    def _memory_signature_terms(content: str) -> str:
        text = re.sub(r"\s+", "", str(content or "")).lower()
        term_candidates = [
            "边缘识别",
            "光照",
            "照明",
            "亮度",
            "复测",
            "稳定性",
            "不合格",
            "失败",
            "风险",
            "抽检",
            "标准",
            "阈值",
            "复核",
            "缺陷",
            "评分",
            "耗时",
            "模型",
            "弱光",
            "强光",
            "漏检",
            "误检",
        ]
        terms = [term for term in term_candidates if term.lower() in text]
        for value in MeetingService._extract_object_refs_from_text(content).values():
            terms.extend(value[:3])
        return "|".join(MeetingService._dedupe_text_values(terms, limit=8))

    @staticmethod
    def _related_memory_ids_for_candidate(
        dedupe_key: str,
        content: str,
        existing_dedupe: dict[str, str],
        existing_terms: list[tuple[str, str, str]],
    ) -> list[str]:
        related: list[str] = []
        if dedupe_key and dedupe_key in existing_dedupe:
            related.append(existing_dedupe[dedupe_key])
        current_terms = set((MeetingService._memory_signature_terms(content) or "").split("|")) - {""}
        if current_terms:
            for memory_id, existing_key, terms_text in existing_terms:
                if memory_id in related:
                    continue
                terms = set((terms_text or "").split("|")) - {""}
                if not terms:
                    continue
                overlap = len(current_terms & terms)
                if overlap >= 2 or (existing_key and dedupe_key and existing_key.split("|")[0:2] == dedupe_key.split("|")[0:2] and overlap >= 1):
                    related.append(memory_id)
                if len(related) >= 5:
                    break
        return related

    @staticmethod
    def _candidate_value_score(content: str, memory_type: str, structured_payload: dict) -> float:
        text = str(content or "")
        score = 0.2
        if len(text.strip()) >= 18:
            score += 0.1
        if memory_type in {_MEMORY_TYPE_QUALITY_FACT, _MEMORY_TYPE_RISK_INSIGHT, _MEMORY_TYPE_QUALITY_PATTERN}:
            score += 0.18
        if memory_type == _MEMORY_TYPE_ACTION_SUGGESTION:
            score += 0.12
        if any(term in text for term in ("结论", "需要", "建议", "风险", "不合格", "复核", "问题模式", "反复", "稳定性")):
            score += 0.18
        if any((structured_payload.get("affected_objects") or {}).get(key) for key in ("inspection_task_ids", "product_ids", "batch_nos", "standard_ids")):
            score += 0.16
        if structured_payload.get("source_spans"):
            score += 0.1
        if structured_payload.get("object_resolution_status") == _OBJECT_RESOLUTION_AMBIGUOUS:
            score -= 0.05
        if structured_payload.get("object_resolution_status") == _OBJECT_RESOLUTION_UNRESOLVED and memory_type not in {"decision", _MEMORY_TYPE_ACTION_SUGGESTION}:
            score -= 0.08
        return max(0.0, min(0.95, score))

    @staticmethod
    def _candidate_extraction_reason(memory_type: str, content: str, structured_payload: dict, value_score: float) -> str:
        reasons: list[str] = []
        if memory_type == _MEMORY_TYPE_QUALITY_FACT:
            reasons.append("包含可追溯的质检事实")
        elif memory_type == _MEMORY_TYPE_RISK_INSIGHT:
            reasons.append("包含未来风险或预警线索")
        elif memory_type == _MEMORY_TYPE_QUALITY_PATTERN:
            reasons.append("包含可复用的问题模式")
        elif memory_type == _MEMORY_TYPE_ACTION_SUGGESTION:
            reasons.append("包含行动建议")
        else:
            reasons.append("包含会议明确结论")
        if any((structured_payload.get("affected_objects") or {}).get(key) for key in ("inspection_task_ids", "product_ids", "batch_nos", "standard_ids")):
            reasons.append("已识别业务标签")
        else:
            reasons.append("尚未识别业务标签")
        if structured_payload.get("source_spans"):
            reasons.append("带有来源消息片段")
        reasons.append(f"价值评分 {round(value_score * 100)}%")
        return "；".join(reasons)

    @staticmethod
    def _existing_source_span_keys(items: list[MemoryItem]) -> set[str]:
        keys: set[str] = set()
        for item in items:
            content_json = item.content_json or {}
            for span in list(content_json.get("source_spans") or []):
                key = MeetingService._source_span_key(span)
                if key:
                    keys.add(key)
        return keys

    @staticmethod
    def _source_span_key(span: dict) -> str:
        message_id = str((span or {}).get("message_id") or "").strip()
        text = str((span or {}).get("text") or "").strip()
        span_index = str((span or {}).get("span_index") or "").strip()
        if not message_id and not text:
            return ""
        normalized_text = re.sub(r"[。！？；;,.，\s]+", "", text).lower()
        return f"{message_id}:{span_index}:{normalized_text[:80]}"

    @staticmethod
    def _source_spans_seen(source_spans: list[dict], existing_keys: set[str]) -> bool:
        keys = [MeetingService._source_span_key(span) for span in source_spans]
        keys = [key for key in keys if key]
        return bool(keys) and all(key in existing_keys for key in keys)

    @staticmethod
    def _classify_candidate_memory(
        summary: str,
        content: str,
        business_context: MeetingBusinessContext,
        *,
        memory_type: str = "decision",
    ) -> str:
        text = f"{summary}\n{content}".lower()
        if not text.strip():
            return _REJECTED_MEMORY_CATEGORY
        noise_terms = ("哈哈", "收到", "辛苦", "谢谢", "闲聊", "测试一下", "早上好", "晚上好")
        if any(term in text for term in noise_terms) and not any(
            token in text for token in ("质检", "检测", "任务", "产品", "批次", "标准", "复核", "风险")
        ):
            return _REJECTED_MEMORY_CATEGORY
        business_terms = (
            "质检",
            "检测",
            "任务",
            "产品",
            "批次",
            "标准",
            "复核",
            "抽检",
            "缺陷",
            "风险",
            "判定",
            "审核",
            "inspection",
            "quality",
            "standard",
            "batch",
            "product",
        )
        has_bound_business_context = bool(
            business_context.task_ids
            or business_context.product_ids
            or business_context.batch_nos
            or business_context.standard_ids
        )
        if memory_type in {_MEMORY_TYPE_RISK_INSIGHT, _MEMORY_TYPE_QUALITY_PATTERN}:
            return _BUSINESS_MEMORY_CATEGORY if has_bound_business_context else _MEETING_MEMORY_CATEGORY
        if memory_type == _MEMORY_TYPE_QUALITY_FACT:
            return _BUSINESS_MEMORY_CATEGORY
        if has_bound_business_context and any(term in text for term in business_terms):
            return _BUSINESS_MEMORY_CATEGORY
        meeting_terms = ("会议", "纪要", "待办", "行动项", "角色", "安排", "结论", "决定", "建议")
        if any(term in text for term in meeting_terms):
            return _MEETING_MEMORY_CATEGORY
        return _MEETING_MEMORY_CATEGORY

    @staticmethod
    def _recommend_memory_scope(
        memory_category: str,
        content: str,
        business_context: MeetingBusinessContext,
        *,
        memory_type: str = "decision",
        affected_objects: dict | None = None,
        object_resolution_status: str = _OBJECT_RESOLUTION_UNRESOLVED,
    ) -> tuple[str, str | None]:
        normalized = content.lower()
        if memory_category != _BUSINESS_MEMORY_CATEGORY:
            return _MEMORY_SCOPE_MEETING_ROOM, None
        if memory_type == _MEMORY_TYPE_QUALITY_PATTERN:
            return _MEMORY_SCOPE_ORG_SPACE, "current"
        if memory_type == _MEMORY_TYPE_RISK_INSIGHT:
            return _MEMORY_SCOPE_ORG_SPACE, "current"
        if any(term in normalized for term in ("组织共享", "共享记忆", "org_space")):
            return _MEMORY_SCOPE_ORG_SPACE, "current"
        return _MEMORY_SCOPE_MEETING_ROOM, None

    @staticmethod
    def _memory_shareability(
        memory_category: str,
        business_context: MeetingBusinessContext,
        *,
        memory_type: str = "decision",
        object_resolution_status: str = _OBJECT_RESOLUTION_RESOLVED,
    ) -> dict:
        allowed_scopes = [
            _MEMORY_SCOPE_MEETING_ROOM,
            _MEMORY_SCOPE_ORG_SPACE,
            _MEMORY_SCOPE_USER,
            _MEMORY_SCOPE_AGENT,
            _MEMORY_SCOPE_COLLAB_THREAD,
        ]
        missing_bindings: list[str] = []
        return {
            "allowed_scopes": allowed_scopes,
            "missing_bindings": sorted(set(missing_bindings)),
            "requires_host_confirmation": True,
            "requires_approval": True,
            "approval_role": "host",
            "source_scope": _MEMORY_SCOPE_MEETING_ROOM,
            "target_scope": {
                "scope_type": _MEMORY_SCOPE_MEETING_ROOM,
                "scope_id": "current",
            },
            "cross_room_allowed": True,
            "organization_scope_enabled": _MEMORY_SCOPE_ORG_SPACE in allowed_scopes,
            "stable_object_visibility": False,
            "related_meeting_delivery": False,
            "business_tags_optional": True,
            "object_resolution_status": object_resolution_status,
        }

    @staticmethod
    def _candidate_warnings(
        memory_category: str,
        content: str,
        *,
        memory_type: str = "decision",
        business_context: MeetingBusinessContext | None = None,
        object_resolution_status: str = _OBJECT_RESOLUTION_UNRESOLVED,
        related_memory_ids: list[str] | None = None,
    ) -> list[str]:
        warnings: list[str] = []
        if memory_category == _REJECTED_MEMORY_CATEGORY:
            warnings.append("候选内容缺少可沉淀信息，不建议确认。")
        if memory_category == _MEETING_MEMORY_CATEGORY:
            warnings.append("该记忆默认沉淀到当前会议室；也可以直接共享给成员、其他会议室、Agent 或组织共享空间。")
        if memory_category == _BUSINESS_MEMORY_CATEGORY and business_context is not None:
            has_any_binding = bool(
                business_context.task_ids
                or business_context.product_ids
                or business_context.batch_nos
                or business_context.standard_ids
            )
            if not has_any_binding:
                warnings.append("未识别到业务标签不影响共享；任务、产品、批次、标准只作为可选标签和检索线索。")
            if memory_type == _MEMORY_TYPE_QUALITY_FACT and not business_context.task_ids:
                warnings.append("单次质检事实可补充任务标签便于回溯，但不会把质检任务作为共享目标。")
        if object_resolution_status == _OBJECT_RESOLUTION_AMBIGUOUS:
            warnings.append("该候选记忆可能关联多个业务标签，确认前可人工校准标签。")
        if object_resolution_status == _OBJECT_RESOLUTION_UNRESOLVED and memory_category == _BUSINESS_MEMORY_CATEGORY:
            warnings.append("该候选记忆尚未识别业务标签，但仍可沉淀为共享记忆。")
        if related_memory_ids:
            warnings.append("该候选记忆可能与既有记忆重复或形成补充，确认前请检查关联记忆。")
        if memory_type == _MEMORY_TYPE_RISK_INSIGHT:
            warnings.append("风险洞察是预测候选，需人工确认后才能沉淀或共享；任务、产品、批次、标准只作为标签线索。")
        if any(term in content for term in ("人工审核不对", "人工审核错误", "审核错了")):
            warnings.append("该内容涉及审核争议，只能作为上下文，不会修改人工审核结论。")
        return warnings

    async def _ensure_memory_publish_allowed(
        self,
        item: MemoryItem,
        scope: str | None,
        scope_id: str | None,
        content_json: dict,
        *,
        transfer: bool = False,
    ) -> None:
        normalized_scope = self._normalize_memory_scope(scope or _MEMORY_SCOPE_MEETING_ROOM)
        room_id = self._memory_room_id(item)
        if not room_id:
            raise ForbiddenError("memory is not sourced from a meeting room")
        category = str(content_json.get("memory_category") or _MEETING_MEMORY_CATEGORY)
        if category == _REJECTED_MEMORY_CATEGORY:
            raise ValidationError("rejected_noise memory cannot be confirmed")
        if normalized_scope == _MEMORY_SCOPE_MEETING_ROOM:
            clean_scope_id = str(scope_id or "").strip()
            if clean_scope_id and clean_scope_id not in {"current", room_id}:
                target_room = await self._repo.get_room(self._org_id, clean_scope_id)
                if target_room is None:
                    raise ValidationError(f"meeting_room scope {clean_scope_id} not found")
                target_member = await self._repo.get_member(self._org_id, clean_scope_id, self._user_id)
                if target_member is None:
                    raise ForbiddenError("current user is not a member of the target meeting room")
            return
        if normalized_scope not in _MEMORY_PUBLISH_SCOPES:
            raise ValidationError("unsupported memory publish scope")
        if normalized_scope in _LEGACY_BUSINESS_SCOPES:
            raise ValidationError("business objects are memory tags, not publish scopes")
        clean_scope_id = str(scope_id or "").strip()
        if not clean_scope_id:
            raise ValidationError(f"{normalized_scope} scope requires scope_id")
        if normalized_scope == _MEMORY_SCOPE_USER:
            user = await self._users.get_by_id(self._org_id, clean_scope_id)
            if user is None:
                raise ValidationError(f"user scope {clean_scope_id} not found")
            return
        if normalized_scope == _MEMORY_SCOPE_COLLAB_THREAD:
            if not clean_scope_id:
                raise ValidationError("collab_thread scope requires scope_id")
            return
        if normalized_scope == _MEMORY_SCOPE_AGENT:
            if not clean_scope_id:
                raise ValidationError("agent scope requires scope_id")
            return
        if normalized_scope == _MEMORY_SCOPE_ORG_SPACE:
            if clean_scope_id != self._org_id and clean_scope_id not in {"current", "org", "organization"}:
                raise ValidationError("org_space scope must target the current organization")
            return
        if transfer:
            raise ValidationError("unsupported transfer scope")
        raise ValidationError("unsupported memory publish scope")

    @staticmethod
    def _has_memory_revision(
        original_content: dict,
        next_content: dict,
        requested_scope: str,
        scope_id: str | None,
    ) -> bool:
        return any(
            [
                str(original_content.get("title") or "") != str(next_content.get("title") or ""),
                str(original_content.get("content") or "") != str(next_content.get("content") or ""),
                str(original_content.get("target_scope_type") or original_content.get("published_scope") or "") != str(requested_scope or ""),
                str(original_content.get("target_scope_id") or "") != str(scope_id or ""),
            ]
        )

    async def _create_memory_revision(
        self,
        *,
        item: MemoryItem,
        room_id: str,
        target_scope_type: str,
        target_scope_id: str,
        requested_scope: str,
        content_json: dict,
        content: str,
    ) -> MemoryItem:
        revision_memory_id = f"mem_meeting_{uuid.uuid4().hex[:12]}"
        revision_content = {
            **content_json,
            "version_parent_id": str(item.memory_id),
            "revision_of": str(item.memory_id),
            "published_scope": requested_scope,
            "target_scope_type": target_scope_type,
            "target_scope_id": target_scope_id,
        }
        revision = MemoryItem(
            id=str(uuid7()),
            memory_id=revision_memory_id,
            org_id=self._org_id,
            user_id=getattr(item, "user_id", None),
            memory_type=str(getattr(item, "memory_type", "") or "task_episode"),
            scope_json=self._memory_scope_json(target_scope_type, target_scope_id, source_room_id=room_id),
            content_summary=content[:1000],
            content_json=revision_content,
            source_event_ids=getattr(item, "source_event_ids", None),
            evidence_pointers={
                **dict(getattr(item, "evidence_pointers", None) or {}),
                "revision_parent_id": str(item.memory_id),
            },
            version_parent_id=str(item.memory_id),
            trust_score=getattr(item, "trust_score", None),
            confidence=getattr(item, "confidence", None),
            visibility_scope=getattr(item, "visibility_scope", None),
            usage_policy=str(getattr(item, "usage_policy", "") or "context_only"),
            ttl_policy=str(getattr(item, "ttl_policy", "") or "never"),
            privacy_level=str(getattr(item, "privacy_level", "") or "tenant_private"),
            status="confirmed",
            created_by=self._user_id,
            created_by_type="user",
            trace_id=f"meeting:{room_id}:{revision_memory_id}",
            expires_at=getattr(item, "expires_at", None),
        )
        await self._repo.create_memory_item(revision)
        await self._repo.create_memory_scope_binding(
            org_id=self._org_id,
            memory_id=revision_memory_id,
            scope_type=target_scope_type,
            scope_id=target_scope_id,
            permission="read",
            created_by=self._user_id,
        )
        return revision

    def _resolve_memory_publish_scope(
        self,
        *,
        room_id: str,
        scope: str | None,
        scope_id: str | None,
        business_context: MeetingBusinessContext | None = None,
    ) -> tuple[str, str]:
        normalized = self._normalize_memory_scope(scope or _MEMORY_SCOPE_MEETING_ROOM)
        if normalized == _MEMORY_SCOPE_MEETING_ROOM:
            clean_scope_id = str(scope_id or "").strip()
            if clean_scope_id in {"", "current"}:
                clean_scope_id = room_id
            return _MEMORY_SCOPE_MEETING_ROOM, clean_scope_id
        if normalized in _LEGACY_BUSINESS_SCOPES:
            raise ValidationError("business objects are memory tags, not publish scopes")
        if normalized == _MEMORY_SCOPE_ORG_SPACE:
            clean_scope_id = str(scope_id or "").strip()
            if clean_scope_id in {"", "current", "org", "organization"}:
                clean_scope_id = self._org_id
            return normalized, clean_scope_id
        if normalized in {_MEMORY_SCOPE_COLLAB_THREAD, _MEMORY_SCOPE_USER, _MEMORY_SCOPE_AGENT}:
            clean_scope_id = str(scope_id or "").strip()
            if not clean_scope_id:
                raise ValidationError(f"{normalized} scope requires scope_id")
            return normalized, clean_scope_id
        raise ValidationError("unsupported memory publish scope")

    async def _memory_transfer_requires_approval(
        self,
        item: MemoryItem,
        *,
        source_room_id: str | None,
        target_scope_type: str,
        target_scope_id: str,
    ) -> bool:
        if target_scope_type == _MEMORY_SCOPE_MEETING_ROOM:
            return bool(source_room_id and target_scope_id not in {"", "current", source_room_id})
        if target_scope_type == _MEMORY_SCOPE_ORG_SPACE:
            return True
        if target_scope_type == _MEMORY_SCOPE_USER:
            return target_scope_id != self._user_id
        if target_scope_type == _MEMORY_SCOPE_AGENT:
            return target_scope_id != _MEETING_GENERAL_AGENT_ID
        if target_scope_type == _MEMORY_SCOPE_COLLAB_THREAD:
            return True
        return True

    @staticmethod
    def _approval_role_for_scope(scope_type: str) -> str:
        if scope_type == _MEMORY_SCOPE_MEETING_ROOM:
            return "target_room_host"
        if scope_type == _MEMORY_SCOPE_ORG_SPACE:
            return "admin"
        if scope_type == _MEMORY_SCOPE_USER:
            return "target_user"
        return "host"

    @staticmethod
    def _shareability_with_target(
        base: Any,
        target_scope_type: str,
        target_scope_id: str,
        *,
        requires_approval: bool,
        approval_role: str,
    ) -> dict[str, Any]:
        shareability = dict(base or {}) if isinstance(base, dict) else {}
        allowed_scopes = list(shareability.get("allowed_scopes") or [])
        if target_scope_type not in allowed_scopes:
            allowed_scopes.append(target_scope_type)
        shareability.update(
            {
                "allowed_scopes": allowed_scopes,
                "requires_approval": requires_approval,
                "approval_role": approval_role,
                "source_scope": _MEMORY_SCOPE_MEETING_ROOM,
                "target_scope": {
                    "scope_type": target_scope_type,
                    "scope_id": target_scope_id,
                },
            }
        )
        return shareability

    @staticmethod
    def _memory_current_scope(item: MemoryItem) -> str:
        content_json = getattr(item, "content_json", None) or {}
        scope_json = getattr(item, "scope_json", None) or {}
        return str(content_json.get("published_scope") or scope_json.get("scope_type") or "")

    @staticmethod
    def _normalize_memory_scope(scope: str | None) -> str:
        raw = str(scope or _MEMORY_SCOPE_MEETING_ROOM).strip() or _MEMORY_SCOPE_MEETING_ROOM
        normalized = _MEMORY_SCOPE_ALIASES.get(raw, raw)
        if normalized not in _MEMORY_PUBLISH_SCOPES and normalized not in _LEGACY_BUSINESS_SCOPES:
            raise ValidationError("unsupported memory publish scope")
        return normalized

    @staticmethod
    def _memory_tags_from_content(content_json: dict) -> list[dict[str, str]]:
        affected = content_json.get("affected_objects") if isinstance(content_json.get("affected_objects"), dict) else {}
        context = content_json.get("business_context") if isinstance(content_json.get("business_context"), dict) else {}
        sources = {
            "task": list(affected.get("inspection_task_ids") or []) + list(context.get("task_ids") or []),
            "product": list(affected.get("product_ids") or []) + list(context.get("product_ids") or []),
            "batch": list(affected.get("batch_nos") or []) + list(context.get("batch_nos") or []),
            "standard": list(affected.get("standard_ids") or []) + list(context.get("standard_ids") or []),
        }
        tags: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for tag_type, values in sources.items():
            for value in values:
                tag_value = str(value or "").strip()
                if not tag_value:
                    continue
                key = (tag_type, tag_value)
                if key in seen:
                    continue
                seen.add(key)
                tags.append({"tag_type": tag_type, "tag_value": tag_value})
        return tags

    @staticmethod
    def _memory_scope_json(
        scope_type: str,
        scope_id: str,
        *,
        source_room_id: str | None = None,
    ) -> dict:
        scope_json = {
            "scope_type": scope_type,
            "scope_id": scope_id,
        }
        if source_room_id:
            scope_json["source_room_id"] = source_room_id
        field_by_type = {
            "meeting_room": "room_id",
            "collab_thread": "thread_id",
            "user": "user_id",
            "agent": "agent_id",
            "org_space": "organization_id",
        }
        direct_field = field_by_type.get(scope_type)
        if direct_field:
            scope_json[direct_field] = scope_id
        if scope_type == "meeting_room":
            scope_json["meeting_room_id"] = scope_id
        return scope_json

    @staticmethod
    def _memory_scope_label(scope_type: str) -> str:
        return {
            "meeting_room": "本会议室",
            "collab_thread": "协作通道",
            "user": "个人记忆",
            "agent": "Agent 记忆",
            "org_space": "组织共享记忆",
        }.get(scope_type, scope_type)

    def _serialize_memory_item(self, item: MemoryItem, *, room_id: str) -> MeetingMemoryResponse:
        content_json = item.content_json or {}
        scope_json = item.scope_json or {}
        business_context = content_json.get("business_context")
        shareability = content_json.get("shareability")
        scope_type = str(
            content_json.get("target_scope_type")
            or scope_json.get("scope_type")
            or ""
        ) or None
        scope_id = str(
            content_json.get("target_scope_id")
            or scope_json.get("scope_id")
            or ""
        ) or None
        return MeetingMemoryResponse(
            memory_id=str(item.memory_id),
            title=str(content_json.get("title") or item.content_summary or item.memory_id),
            content=str(content_json.get("content") or item.content_summary or ""),
            summary=str(item.content_summary or ""),
            memory_type=str(content_json.get("memory_type") or item.memory_type),
            status=str(item.status),
            scope=str(content_json.get("published_scope") or content_json.get("recommended_scope") or _MEMORY_SCOPE_MEETING_ROOM),
            scope_type=scope_type,
            scope_id=scope_id,
            memory_category=str(content_json.get("memory_category") or _MEETING_MEMORY_CATEGORY),
            recommended_scope=str(content_json.get("recommended_scope") or _MEMORY_SCOPE_MEETING_ROOM),
            recommended_scope_id=(
                str(content_json.get("recommended_scope_id"))
                if content_json.get("recommended_scope_id") is not None
                else None
            ),
            source_refs=list(content_json.get("source_refs") or []),
            business_context=business_context if isinstance(business_context, dict) else None,
            shareability=shareability if isinstance(shareability, dict) else None,
            warnings=[str(item) for item in list(content_json.get("warnings") or [])],
            affected_objects=content_json.get("affected_objects") if isinstance(content_json.get("affected_objects"), dict) else None,
            evidence_refs=list(content_json.get("evidence_refs") or []),
            forecast_window=content_json.get("forecast_window") if isinstance(content_json.get("forecast_window"), dict) else None,
            risk_level=str(content_json.get("risk_level")) if content_json.get("risk_level") is not None else None,
            recommended_actions=[str(item) for item in list(content_json.get("recommended_actions") or [])],
            source_room_id=str(content_json.get("source_room_id") or room_id or "") or None,
            source_spans=list(content_json.get("source_spans") or []),
            object_resolution_status=(
                str(content_json.get("object_resolution_status"))
                if content_json.get("object_resolution_status") is not None
                else None
            ),
            object_candidates=list(content_json.get("object_candidates") or []),
            value_score=float(content_json.get("value_score")) if content_json.get("value_score") is not None else None,
            dedupe_key=str(content_json.get("dedupe_key")) if content_json.get("dedupe_key") is not None else None,
            related_memory_ids=[str(item) for item in list(content_json.get("related_memory_ids") or [])],
            extraction_reason=str(content_json.get("extraction_reason")) if content_json.get("extraction_reason") is not None else None,
            publish_reason=content_json.get("publish_reason"),
            version_parent_id=(
                str(content_json.get("version_parent_id") or getattr(item, "version_parent_id", "") or "") or None
            ),
            confidence=float(item.confidence) if item.confidence is not None else None,
            source_message_id=content_json.get("source_message_id"),
            qdl_json=content_json.get("qdl_json") if isinstance(content_json.get("qdl_json"), dict) else None,
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

    async def _record_meeting_memory_event(
        self,
        *,
        event_type: EventType,
        memory_id: str,
        room_id: str,
        payload: dict | None = None,
    ) -> None:
        try:
            service = MemoryService(self._session, self._org_id)
            await service.record_event(
                MemoryEventPayload(
                    event_id=f"evt_{uuid.uuid4().hex[:12]}",
                    org_id=self._org_id,
                    user_id=self._user_id,
                    workspace=Workspace.APP,
                    event_type=event_type,
                    source_kind="meeting",
                    agent_id=_MEETING_GENERAL_AGENT_ID,
                    role=self._role,
                    trace_id=f"meeting:{room_id}:{memory_id}",
                    memory_id=memory_id,
                    payload_json={"room_id": room_id, **(payload or {})},
                )
            )
        except Exception:
            logger.debug("meeting memory event recording skipped", exc_info=True)

    @staticmethod
    def _memory_room_id(item: MemoryItem) -> str | None:
        scope_json = item.scope_json or {}
        content_json = item.content_json or {}
        return str(
            scope_json.get("meeting_room_id")
            or scope_json.get("room_id")
            or scope_json.get("source_room_id")
            or content_json.get("source_id")
            or ""
        ) or None

    @staticmethod
    def _normalize_message_attachments(values: list[dict] | None) -> list[dict]:
        if not values:
            return []
        result: list[dict] = []
        for item in values[:10]:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            name = str(item.get("name") or "").strip()
            if not url or not name:
                continue
            content_type = item.get("content_type")
            kind = str(item.get("kind") or "")
            if kind not in {"image", "file"}:
                kind = "image" if str(content_type or "").startswith("image/") else "file"
            size_bytes = item.get("size_bytes")
            try:
                size = int(size_bytes or 0)
            except (TypeError, ValueError):
                size = 0
            result.append(
                {
                    "id": str(item.get("id") or uuid.uuid4().hex),
                    "name": name[:240],
                    "url": url,
                    "content_type": str(content_type or "") or None,
                    "size_bytes": max(size, 0),
                    "kind": kind,
                    **({"bucket": str(item.get("bucket"))} if item.get("bucket") else {}),
                    **({"object_key": str(item.get("object_key"))} if item.get("object_key") else {}),
                }
            )
        return result

    @staticmethod
    def _normalize_affected_objects(value: dict | None) -> dict[str, list[str]]:
        raw = value or {}
        return {
            "inspection_task_ids": MeetingService._dedupe_text_values(
                raw.get("inspection_task_ids") or raw.get("task_ids"),
                limit=20,
            ),
            "product_ids": MeetingService._dedupe_text_values(raw.get("product_ids"), limit=20),
            "batch_nos": MeetingService._dedupe_text_values(raw.get("batch_nos"), limit=20),
            "standard_ids": MeetingService._dedupe_text_values(raw.get("standard_ids"), limit=20),
        }

    @staticmethod
    def _normalize_quote_snapshot(value: dict | None) -> dict | None:
        if not isinstance(value, dict):
            return None
        content = str(value.get("content") or "").strip()
        if not content:
            return None
        author = str(value.get("author") or "会议Agent").strip()[:80] or "会议Agent"
        source = str(value.get("source") or "agent").strip()[:40] or "agent"
        created_at = str(value.get("created_at") or "").strip()
        return {
            "source": source,
            "author": author,
            "content": content[:600],
            **({"created_at": created_at[:64]} if created_at else {}),
        }

    @staticmethod
    def _dedupe_text_values(values: Any, *, limit: int = 20, max_length: int = 128) -> list[str]:
        if values is None:
            return []
        raw_values = values if isinstance(values, (list, tuple, set)) else re.split(r"[\s,，；;]+", str(values))
        seen: set[str] = set()
        result: list[str] = []
        for value in raw_values:
            text = str(value or "").strip()
            if not text:
                continue
            text = text[:max_length]
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(text)
            if len(result) >= limit:
                break
        return result

    async def _normalize_business_context(self, raw_context: dict | None) -> MeetingBusinessContext:
        context = raw_context or {}
        task_ids = self._dedupe_text_values(context.get("task_ids"), limit=20)
        product_ids = self._dedupe_text_values(context.get("product_ids"), limit=20)
        batch_nos = self._dedupe_text_values(context.get("batch_nos"), limit=20)
        standard_ids = self._dedupe_text_values(context.get("standard_ids"), limit=20)
        task_rows: list[MeetingBusinessContextTask] = []
        if task_ids:
            repo = TaskRepository(self._session)
            valid_task_ids: list[str] = []
            for task_id in task_ids:
                owner_user_id = self._user_id if self._role == ROLE_USER else None
                task = await repo.get_for_user(self._org_id, task_id, owner_user_id=owner_user_id)
                if task is None:
                    raise ValidationError(f"inspection task {task_id} not found")
                valid_task_ids.append(str(task.id))
                product_id = str(getattr(task, "product_id", "") or "").strip()
                spec_code = str(getattr(task, "spec_code", "") or "").strip()
                if product_id and product_id.lower() not in {item.lower() for item in product_ids}:
                    product_ids.append(product_id)
                if spec_code and spec_code.lower() not in {item.lower() for item in standard_ids}:
                    standard_ids.append(spec_code)
                task_rows.append(
                    MeetingBusinessContextTask(
                        id=str(task.id),
                        product_id=product_id,
                        spec_code=spec_code,
                        status=str(getattr(task, "status", "") or ""),
                        priority=int(getattr(task, "priority", 0) or 0),
                        has_result=bool(getattr(task, "has_result", False)),
                        has_stability=bool(getattr(task, "has_stability", False)),
                        created_at=getattr(task, "created_at", None),
                        updated_at=getattr(task, "updated_at", None),
                    )
                )
            task_ids = valid_task_ids
        return MeetingBusinessContext(
            task_ids=task_ids,
            product_ids=self._dedupe_text_values(product_ids, limit=20),
            batch_nos=batch_nos,
            standard_ids=self._dedupe_text_values(standard_ids, limit=20),
            tasks=task_rows,
        )

    def _business_context_from_room(self, room: Any | None) -> MeetingBusinessContext:
        if room is None:
            return MeetingBusinessContext()
        policy = getattr(room, "memory_policy", None) or {}
        if not isinstance(policy, dict):
            return MeetingBusinessContext()
        context = policy.get("business_context") or {}
        if not isinstance(context, dict):
            return MeetingBusinessContext()
        return MeetingBusinessContext.model_validate(context)

    @staticmethod
    def _business_context_from_affected_objects(affected_objects: dict | None) -> MeetingBusinessContext:
        affected = affected_objects if isinstance(affected_objects, dict) else {}
        return MeetingBusinessContext(
            task_ids=MeetingService._dedupe_text_values(affected.get("inspection_task_ids") or affected.get("task_ids") or [], limit=20),
            product_ids=MeetingService._dedupe_text_values(affected.get("product_ids") or affected.get("products") or [], limit=20),
            batch_nos=MeetingService._dedupe_text_values(affected.get("batch_nos") or affected.get("batches") or [], limit=20),
            standard_ids=MeetingService._dedupe_text_values(affected.get("standard_ids") or affected.get("standards") or [], limit=20),
            tasks=[],
        )

    @staticmethod
    def _business_context_from_inspection_context(context: dict | None) -> MeetingBusinessContext:
        if not isinstance(context, dict):
            return MeetingBusinessContext()
        task_ids: list[str] = []
        product_ids: list[str] = []
        standard_ids: list[str] = []
        candidates: list[dict[str, Any]] = []
        latest_task = context.get("latest_task")
        if isinstance(latest_task, dict):
            candidates.append(latest_task)
        for key in ("selected_tasks", "recent_failures", "recent_tasks"):
            for item in list(context.get(key) or []):
                if isinstance(item, dict):
                    candidates.append(item)
        for item in candidates:
            task_id = str(item.get("task_id") or item.get("id") or "").strip()
            product_id = str(item.get("product_id") or "").strip()
            spec_code = str(item.get("spec_code") or item.get("standard_id") or "").strip()
            if task_id:
                task_ids.append(task_id)
            if product_id:
                product_ids.append(product_id)
            if spec_code:
                standard_ids.append(spec_code)
        return MeetingBusinessContext(
            task_ids=MeetingService._dedupe_text_values(task_ids, limit=20),
            product_ids=MeetingService._dedupe_text_values(product_ids, limit=20),
            batch_nos=[],
            standard_ids=MeetingService._dedupe_text_values(standard_ids, limit=20),
            tasks=[],
        )

    @staticmethod
    def _merge_business_context(*contexts: MeetingBusinessContext | None) -> MeetingBusinessContext:
        task_ids: list[str] = []
        product_ids: list[str] = []
        batch_nos: list[str] = []
        standard_ids: list[str] = []
        tasks_by_id: dict[str, MeetingBusinessContextTask] = {}
        for context in contexts:
            if not context:
                continue
            task_ids.extend(context.task_ids or [])
            product_ids.extend(context.product_ids or [])
            batch_nos.extend(context.batch_nos or [])
            standard_ids.extend(context.standard_ids or [])
            for task in context.tasks or []:
                tasks_by_id.setdefault(task.id, task)
        return MeetingBusinessContext(
            task_ids=MeetingService._dedupe_text_values(task_ids, limit=20),
            product_ids=MeetingService._dedupe_text_values(product_ids, limit=20),
            batch_nos=MeetingService._dedupe_text_values(batch_nos, limit=20),
            standard_ids=MeetingService._dedupe_text_values(standard_ids, limit=20),
            tasks=list(tasks_by_id.values()),
        )

    @staticmethod
    def _with_business_context(policy: dict | None, context: MeetingBusinessContext) -> dict:
        next_policy = dict(policy or {})
        next_policy["business_context"] = context.model_dump(mode="json")
        return next_policy

    @staticmethod
    def _ordered_domains(domains: set[str] | list[str] | tuple[str, ...]) -> list[str]:
        return ordered_domains(domains)

    @staticmethod
    def _normalize_domain_list(values: Any) -> list[str]:
        return normalize_domains(values)

    def _role_allowed_domains(self) -> set[str]:
        return role_allowed_domains(self._role)

    def _default_meeting_domains(self) -> set[str]:
        return set(DEFAULT_ROOM_DOMAINS)

    def _effective_domains_for_create(self, requested: list[str] | None) -> list[str]:
        return authorize_room_domains(self._role, requested)

    def _effective_domains_for_room(self, room: Any) -> list[str]:
        stored_domains = self._normalize_domain_list(getattr(room, "allowed_data_domains", None))
        return authorize_room_domains(self._role, stored_domains or None)

    def _agent_allowed_domains(self, room: Any, requested: list[str] | None) -> list[str]:
        return authorize_agent_domains(
            role=self._role,
            room_domains=self._effective_domains_for_room(room),
            requested_domains=requested,
        )

    @staticmethod
    def _normalize_tool_list(tools: Any) -> list[str]:
        if tools is None:
            return []
        if isinstance(tools, str):
            raw_tools = re.split(r"[\s,，；;]+", tools)
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
        return infer_requested_domains_for_query(intent, question)

    def _authorize_general_agent_request(
        self,
        *,
        room: Any,
        question: str,
        intent: str | None,
        agent_domains: list[str] | None = None,
    ):
        return authorize_meeting_query(
            role=self._role,
            requested_domains=self._requested_domains_for_intent(intent, question),
            room_domains=self._effective_domains_for_room(room),
            agent_domains=agent_domains,
            question=question,
        )

    @staticmethod
    def _redacted_fields_for_question(question: str) -> list[str]:
        return redacted_fields_for_question(question)

    @staticmethod
    def _meeting_share_policy() -> dict[str, Any]:
        return {
            "default_boundary": "meeting_room_private",
            "cross_room_requires_approval": True,
            "org_space_requires_approval": True,
            "explicit_binding_required": True,
            "allowed_scopes": [
                _MEMORY_SCOPE_MEETING_ROOM,
                _MEMORY_SCOPE_COLLAB_THREAD,
                _MEMORY_SCOPE_USER,
                _MEMORY_SCOPE_AGENT,
                _MEMORY_SCOPE_ORG_SPACE,
            ],
        }

    @staticmethod
    def _meeting_conflict_rules() -> dict[str, Any]:
        return {
            "read_parallel_limit": 2,
            "write_requires_resource_lock": True,
            "high_risk_conflicts_escalate": True,
            "host_resolves_room_conflicts": True,
            "conflict_types": ["preference", "task", "resource", "knowledge"],
        }

    @staticmethod
    def _meeting_visibility_rules() -> dict[str, Any]:
        return {
            "default": _RESPONSE_VISIBILITY_ROOM,
            "sensitive_queries": _RESPONSE_VISIBILITY_PRIVATE,
            "public_modes": ["meeting_summary", "memory_transfer", "action_items", "risk_forecast", "evidence_query", "standard_explain"],
        }

    def _response_visibility_for_request(self, request: MeetingAgentRunRequest) -> str:
        query = str(request.query or "").lower()
        compact = _normalize_name(query)
        if any(term in query or term in compact for term in _SENSITIVE_QUERY_TERMS):
            return _RESPONSE_VISIBILITY_PRIVATE
        if any(term in query or term in compact for term in _PRIVATE_CONTEXT_QUERY_TERMS):
            return _RESPONSE_VISIBILITY_PRIVATE
        scope = request.memory_scope
        if scope.include_personal_authorized or scope.include_user:
            return _RESPONSE_VISIBILITY_PRIVATE
        return _RESPONSE_VISIBILITY_ROOM

    def _response_visibility_metadata(self, visibility: str, *, room_id: str) -> dict[str, Any]:
        if visibility == _RESPONSE_VISIBILITY_PRIVATE:
            return {
                "visibility": _RESPONSE_VISIBILITY_PRIVATE,
                "audience_scope_type": _MEMORY_SCOPE_USER,
                "audience_scope_id": self._user_id,
                "private_recipient_user_id": self._user_id,
            }
        return {
            "visibility": _RESPONSE_VISIBILITY_ROOM,
            "audience_scope_type": _MEMORY_SCOPE_MEETING_ROOM,
            "audience_scope_id": room_id,
        }

    def _private_user_ids_for_visibility(self, visibility: str) -> list[str]:
        return [self._user_id] if visibility == _RESPONSE_VISIBILITY_PRIVATE else []

    @staticmethod
    def _source_scope_refs(memory_sources: list[MeetingMemorySourceResponse]) -> list[dict[str, str]]:
        refs: list[dict[str, str]] = []
        for item in memory_sources:
            refs.append({"type": "memory", "id": item.memory_id, "scope": item.scope})
        return refs

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
        source_refs = list(getattr(row, "source_refs", None) or [])
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
            source_refs=source_refs,
            memory_reads=[ref for ref in source_refs if isinstance(ref, dict) and str(ref.get("type") or "") == "memory"],
            redacted_fields=[str(item) for item in (getattr(row, "redacted_fields", None) or [])],
            decision=str(getattr(row, "decision", "allowed") or "allowed"),
            response_visibility=str(getattr(row, "response_visibility", "") or _RESPONSE_VISIBILITY_ROOM),
            redaction_level=str(getattr(row, "redaction_level", "") or "none"),
            denied_reasons=dict(getattr(row, "denied_reasons", None) or {}),
            conflict_ref_id=str(getattr(row, "conflict_ref_id", "") or "") or None,
            created_at=getattr(row, "created_at", None),
        )

    async def _can_view_or_approve_share(self, row: Any) -> bool:
        try:
            await self._ensure_memory_share_approver(row)
            return True
        except ForbiddenError:
            pass
        if str(getattr(row, "from_scope_type", "") or "") == _MEMORY_SCOPE_MEETING_ROOM:
            member = await self._repo.get_member(self._org_id, str(row.from_scope_id), self._user_id)
            if member:
                return True
        return False

    async def _ensure_memory_share_approver(self, row: Any) -> None:
        to_scope_type = str(getattr(row, "to_scope_type", "") or "")
        to_scope_id = str(getattr(row, "to_scope_id", "") or "")
        if to_scope_type == _MEMORY_SCOPE_MEETING_ROOM:
            await self._ensure_host(to_scope_id)
            return
        if to_scope_type == _MEMORY_SCOPE_ORG_SPACE:
            if self._role != ROLE_ADMIN:
                raise ForbiddenError("only admin can approve org memory shares")
            return
        if to_scope_type == _MEMORY_SCOPE_USER:
            if to_scope_id != self._user_id and self._role != ROLE_ADMIN:
                raise ForbiddenError("only target user can approve personal memory shares")
            return
        from_room_id = str(getattr(row, "from_scope_id", "") or "")
        if from_room_id:
            await self._ensure_host(from_room_id)
            return
        raise ForbiddenError("not allowed to approve this memory share")

    async def _serialize_memory_share_approval(self, row: Any) -> MeetingMemoryShareApprovalResponse:
        memory_title = ""
        item = await self._repo.get_memory_item(self._org_id, str(row.memory_id))
        if item is not None:
            content_json = dict(getattr(item, "content_json", None) or {})
            memory_title = str(content_json.get("title") or getattr(item, "content_summary", "") or item.memory_id)
        can_approve = False
        try:
            await self._ensure_memory_share_approver(row)
            can_approve = True
        except Exception:
            can_approve = False
        return MeetingMemoryShareApprovalResponse(
            id=str(row.id),
            memory_id=str(row.memory_id),
            from_scope_type=str(row.from_scope_type),
            from_scope_id=str(row.from_scope_id),
            to_scope_type=str(row.to_scope_type),
            to_scope_id=str(row.to_scope_id),
            transfer_reason=getattr(row, "transfer_reason", None),
            status=str(row.status),
            operator_id=str(row.operator_id) if getattr(row, "operator_id", None) else None,
            memory_title=memory_title,
            can_approve=can_approve,
            created_at=getattr(row, "created_at", None),
            updated_at=getattr(row, "updated_at", None),
        )

    @staticmethod
    def _serialize_conflict_event(row: Any) -> MeetingConflictEventResponse:
        return MeetingConflictEventResponse(
            id=str(row.id),
            room_id=str(row.room_id),
            conflict_type=str(row.conflict_type),
            resource_key=str(row.resource_key),
            status=str(row.status),
            initiator_user_id=str(row.initiator_user_id),
            workflow_run_id=str(row.workflow_run_id) if getattr(row, "workflow_run_id", None) else None,
            related_message_ids=[str(item) for item in list(getattr(row, "related_message_ids", None) or [])],
            candidate_actions=list(getattr(row, "candidate_actions", None) or []),
            selected_action=str(row.selected_action) if getattr(row, "selected_action", None) else None,
            resolved_by=str(row.resolved_by) if getattr(row, "resolved_by", None) else None,
            resolved_at=getattr(row, "resolved_at", None),
            metadata_json=getattr(row, "metadata_json", None) or {},
            created_at=getattr(row, "created_at", None),
            updated_at=getattr(row, "updated_at", None),
        )

    async def _record_agent_query_audit(
        self,
        *,
        room: Any,
        question: str,
        intent: str | None,
        source_refs: list[dict] | None = None,
        tool_calls: list[dict] | None = None,
        response_visibility: str = _RESPONSE_VISIBILITY_ROOM,
        conflict_ref_id: str | None = None,
    ) -> None:
        create_audit = getattr(self._repo, "create_agent_query_audit", None)
        if create_audit is None:
            return

        requested_domains = self._requested_domains_for_intent(intent, question)
        authorization = authorize_meeting_query(
            role=self._role,
            requested_domains=requested_domains,
            room_domains=self._effective_domains_for_room(room),
            question=question,
        )
        await create_audit(
            org_id=self._org_id,
            room_id=str(getattr(room, "id", "") or ""),
            user_id=self._user_id,
            agent_id=_MEETING_GENERAL_AGENT_ID,
            question=str(question or "").strip()[:4000],
            intent=intent,
            requested_domains=authorization.requested_domains,
            allowed_domains=authorization.allowed_domains,
            denied_domains=authorization.denied_domains,
            tool_calls=tool_calls or [],
            source_refs=source_refs or [],
            redacted_fields=authorization.redacted_fields,
            decision=authorization.decision,
            response_visibility=response_visibility,
            redaction_level=authorization.redaction_level,
            denied_reasons=authorization.denied_reasons,
            conflict_ref_id=conflict_ref_id,
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
                visibility=str(getattr(room, "visibility", "private") or "private"),
                allowed_data_domains=self._effective_domains_for_room(room),
                memory_policy=getattr(room, "memory_policy", None) or {},
                audit_policy=getattr(room, "audit_policy", None) or {},
                business_context=self._business_context_from_room(room),
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
            "总 AI",
            "总AI",
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
                    metadata_json={
                        "selected_subgraph": "failure",
                        "private_recipient_user_id": self._user_id,
                    },
                )
                response = MeetingMessageResponse.model_validate(message)
                await session.commit()
                await meeting_stream_broker.publish(
                    room_id,
                    {
                        "event": "message_created",
                        "room_id": room_id,
                        "message": response.model_dump(),
                        "private_user_ids": [self._user_id],
                    },
                )
        except Exception:
            logger.exception("meeting general agent failure message publish failed room_id=%s", room_id)
