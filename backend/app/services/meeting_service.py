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
from app.core.security import hash_password, verify_password
from app.models.memory import MemoryItem
from app.repositories.alert_repo import AlertRepository
from app.repositories.meeting_repo import MeetingRepository
from app.repositories.task_repo import TaskRepository
from app.repositories.user_repo import UserRepository
from app.schemas.meeting import (
    MeetingActionItemCreateRequest,
    MeetingActionItemResponse,
    MeetingActionItemUpdateRequest,
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
from app.schemas.memory import EventType, MemoryEventPayload, Workspace
from app.services.agent_manager_service import AgentManagerService
from app.services.chat_context_service import ChatContextService
from app.services.meeting_agent_cancel_registry import meeting_agent_cancel_registry
from app.services.meeting_agent_service import MeetingAgentService
from app.services.memory_service import MemoryService
from app.services.rag_space_service import RagSpaceService
from app.services.stream_service import meeting_stream_broker
from infra.database.session import get_session

_MENTION_DELIMITER_RE = re.compile(r"(?=$|[\s,.;:!?，。；：！？])")
_MEETING_AI_AGENT_NAME = "AI助手"
_MEETING_GENERAL_AGENT_ID = "general_agent"
_MEETING_GENERAL_AGENT_NAME = "会议Agent"
logger = logging.getLogger(__name__)

_MESSAGE_RECALL_WINDOW = timedelta(minutes=2)
_AGENT_RUN_CANCELLED_MESSAGE = "会议Agent回复已停止"

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
_ROLE_DOMAIN_ALLOW = {
    ROLE_USER: {"quality", "standard", "meeting", "memory", "ai_conversation"},
    ROLE_EXPERT: {"quality", "standard", "meeting", "memory", "ai_conversation"},
    ROLE_PLATFORM_OPERATOR: {"platform_ops", "model_billing", "data_access", "meeting", "memory", "security_audit"},
    ROLE_APP_DEVELOPER: {"platform_ops", "model_billing", "data_access", "meeting", "memory", "security_audit"},
    ROLE_ALGORITHM_ENGINEER: {"platform_ops", "model_billing", "data_access", "meeting", "memory"},
    ROLE_ADMIN: set(_ALL_DATA_DOMAINS),
}
_ROOM_QUERY_EXAMPLES = ["总结当前会议。", "提取会议待办。", "把刚才讨论整理成候选记忆。"]
_ROOM_GUARDRAILS = [
    "Agent 只能代用户查询其本来有权限的数据。",
    "具体事实查业务库，经验规律查记忆库。",
    "AI 会话内容是原始事件，不自动成为已确认记忆。",
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
_BUSINESS_MEMORY_CATEGORY = "business_memory"
_MEETING_MEMORY_CATEGORY = "meeting_memory"
_REJECTED_MEMORY_CATEGORY = "rejected_noise"
_MEMORY_TYPE_QUALITY_FACT = "quality_fact"
_MEMORY_TYPE_RISK_INSIGHT = "risk_insight"
_MEMORY_TYPE_QUALITY_PATTERN = "quality_pattern"
_MEMORY_TYPE_ACTION_SUGGESTION = "action_suggestion"
_WORKSPACE_RISK_LIBRARY_SCOPE_ID = "quality_risk_library"
_BUSINESS_PUBLISH_SCOPES = {"inspection_task", "product", "standard", "batch", "workspace"}
_MEETING_ONLY_SCOPES = {"meeting"}


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
        await self._publish_system_message(room_id, "会议业务对象绑定已更新。")
        await self._session.commit()
        return context

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
            visible_user_id=self._user_id,
        )
        return [MeetingMessageResponse.model_validate(item) for item in messages]

    async def update_message(self, room_id: str, message_id: str, content: str) -> MeetingMessageResponse:
        await self._ensure_active_member(room_id)
        message = await self._repo.get_message(self._org_id, room_id, message_id)
        if not message:
            raise NotFoundError("meeting message not found")
        self._ensure_message_mutable(message)
        if self._message_recipient_user_id(message):
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
            raise ForbiddenError("meeting creator cannot leave the room; archive or delete it instead")
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

        business_context = self._business_context_from_room(room)
        return MeetingContextPreviewResponse(
            room_id=room_id,
            user_role=self._role,
            room_role=str(getattr(member, "role", "member") or "member"),
            allowed_domains=allowed_domains,
            denied_domains=denied_domains,
            agent_permissions=agent_permissions,
            query_examples=list(_ROOM_QUERY_EXAMPLES),
            guardrails=list(_ROOM_GUARDRAILS),
            business_context=business_context,
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
        workflow_run_id = str(request.workflow_run_id or uuid7())
        agent_message_id = str(uuid7())
        attachment_echo = self._normalize_message_attachments(request.attachments)
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
                "private_user_ids": [self._user_id],
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
            recent_messages = await self._repo.list_recent_messages(
                org_id=self._org_id,
                room_id=room_id,
                limit=80,
            )
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

            message = await self._repo.create_message(
                org_id=self._org_id,
                room_id=room_id,
                user_id=self._user_id,
                username=_MEETING_GENERAL_AGENT_NAME,
                content=answer,
                message_type="agent",
                agent_id=_MEETING_GENERAL_AGENT_ID,
                metadata_json={
                    "query": request.query,
                    "selected_subgraph": selected_subgraph,
                    "memory_sources": [item.model_dump(mode="json") for item in memory_sources],
                    "candidate_memories": [item.model_dump(mode="json") for item in candidate_memories],
                    "business_context": business_context.model_dump(mode="json"),
                    "private_recipient_user_id": self._user_id,
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
            )
            await self._session.commit()
            await meeting_stream_broker.publish(
                room_id,
                {"event": "message_created", "room_id": room_id, "message": response_message.model_dump(), "private_user_ids": [self._user_id]},
            )
            return MeetingAgentRunResponse(
                selected_subgraph=selected_subgraph,
                answer=answer,
                message=response_message,
                memory_sources=memory_sources,
                candidate_memories=candidate_memories,
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
                    "private_user_ids": [self._user_id],
                },
            )
            raise
        finally:
            meeting_agent_cancel_registry.clear(room_id, workflow_run_id)

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

    @staticmethod
    def _cancelled_general_agent_response(
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
        )
        return MeetingAgentRunResponse(
            selected_subgraph=selected_subgraph,
            answer=_AGENT_RUN_CANCELLED_MESSAGE,
            message=message,
            memory_sources=memory_sources,
            candidate_memories=candidate_memories,
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
            statuses=["candidate", "active", "disputed", "superseded"],
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
        content_json["confirmed_by"] = self._user_id
        content_json["confirmed_at"] = datetime.utcnow().isoformat()
        requested_scope = (request.scope if request else None) or "meeting"
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
        inferred_category = self._classify_candidate_memory(
            str(content_json.get("title") or ""),
            str(content_json.get("content") or item.content_summary or ""),
            business_context,
            memory_type=str(content_json.get("memory_type") or "decision"),
        )
        if original_category != _REJECTED_MEMORY_CATEGORY:
            content_json["memory_category"] = inferred_category
        if request and request.is_business_memory is not None and original_category != _REJECTED_MEMORY_CATEGORY:
            content_json["memory_category"] = (
                _BUSINESS_MEMORY_CATEGORY if request.is_business_memory else _MEETING_MEMORY_CATEGORY
            )
        content_json["shareability"] = self._memory_shareability(
            str(content_json.get("memory_category") or _MEETING_MEMORY_CATEGORY),
            business_context,
            memory_type=str(content_json.get("memory_type") or "decision"),
        )
        content_json["warnings"] = self._candidate_warnings(
            str(content_json.get("memory_category") or _MEETING_MEMORY_CATEGORY),
            str(content_json.get("content") or item.content_summary or ""),
            memory_type=str(content_json.get("memory_type") or "decision"),
            business_context=business_context,
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
        has_confirmed_before = status in {"active", "disputed", "superseded"} or bool(original_content_json.get("confirmed_at"))
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
                status="active",
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
            transfer_reason=publish_reason or ("会议记忆修订后发布新版本" if is_revision else "会议候选记忆经用户确认后进入已确认记忆"),
            status="confirmed",
            operator_id=self._user_id,
        )
        if not is_revision:
            await self._create_risk_forecast_alert_if_needed(
                memory_id=str(getattr(updated, "memory_id", memory_id)),
                room_id=room_id,
                content_json=content_json,
                target_scope_type=target_scope_type,
                target_scope_id=target_scope_id,
            )
        await self._publish_system_message(
            room_id,
            f"记忆「{content_json.get('title') or '会议记忆'}」已发布到{self._memory_scope_label(target_scope_type)}。"
            if not is_revision
            else f"记忆「{content_json.get('title') or '会议记忆'}」已生成修订版本并发布到{self._memory_scope_label(target_scope_type)}。",
        )
        return self._serialize_memory_item(updated or item, room_id=room_id)

    async def _create_risk_forecast_alert_if_needed(
        self,
        *,
        memory_id: str,
        room_id: str,
        content_json: dict,
        target_scope_type: str,
        target_scope_id: str,
    ) -> None:
        if str(content_json.get("memory_type") or "") != _MEMORY_TYPE_RISK_INSIGHT:
            return
        if target_scope_type == "meeting_room":
            return
        affected_objects = content_json.get("affected_objects")
        if not isinstance(affected_objects, dict):
            affected_objects = {}
        if not any(affected_objects.get(key) for key in ("inspection_task_ids", "product_ids", "batch_nos")):
            return
        risk_level = str(content_json.get("risk_level") or "medium")
        severity = "error" if risk_level in {"high", "critical"} else "warning"
        alert_id = str(uuid7())
        title = str(content_json.get("title") or "风险洞察预警")[:256]
        detail = {
            "memory_id": memory_id,
            "source_room_id": room_id,
            "target_scope_type": target_scope_type,
            "target_scope_id": target_scope_id,
            "risk_level": risk_level,
            "forecast_window": content_json.get("forecast_window"),
            "affected_objects": affected_objects,
            "evidence_refs": list(content_json.get("evidence_refs") or content_json.get("source_refs") or []),
            "recommended_actions": list(content_json.get("recommended_actions") or []),
            "content": str(content_json.get("content") or "")[:1200],
        }
        create_alert = getattr(AlertRepository(self._session), "create_once")
        try:
            await create_alert(
                {
                    "id": alert_id,
                    "org_id": self._org_id,
                    "stability_id": None,
                    "rule_id": None,
                    "alert_type": "risk_forecast",
                    "severity": severity,
                    "title": title,
                    "detail": detail,
                    "status": "open",
                    "channels": {
                        "source": "meeting_memory",
                        "visibility": "alert_center",
                        "target_roles": ["admin", "platform_operator"],
                    },
                    "idempotency_key": f"risk_forecast:{self._org_id}:{memory_id}:{target_scope_type}:{target_scope_id}",
                }
            )
        except Exception:
            logger.debug("risk forecast alert creation skipped", exc_info=True)

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
        target_scope_type = request.to_scope_type
        target_scope_id = request.to_scope_id
        if target_scope_type == "meeting_room":
            if room_id and target_scope_id in {"current", room_id}:
                target_scope_id = room_id
            else:
                raise ValidationError("meeting_room transfer can only target the source meeting room")
        await self._ensure_memory_publish_allowed(item, target_scope_type, target_scope_id, dict(item.content_json or {}), transfer=True)
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
            status="confirmed",
            operator_id=self._user_id,
        )
        content_json = dict(item.content_json or {})
        content_json["target_scope_type"] = target_scope_type
        content_json["target_scope_id"] = target_scope_id
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
        if self._is_general_agent_cancelled(room_id, workflow_run_id):
            raise asyncio.CancelledError()
        recent_messages = await self._repo.list_recent_messages(
            org_id=self._org_id,
            room_id=room_id,
            limit=24,
        )
        allowed_domains = self._effective_domains_for_room(room)
        query = self._clean_general_agent_query(request.query)
        attachment_echo = self._normalize_message_attachments(request.attachments)
        payload = {
            "request_id": str(uuid7()),
            "workflow_run_id": workflow_run_id,
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
                "meeting_agent_name": _MEETING_GENERAL_AGENT_NAME,
                "allowed_data_domains": allowed_domains,
                "query": request.query,
                "attachments_count": len(attachment_echo),
            },
            "ext": {
                "surface": "chat",
                "allowed_modes": ["answer", "report"],
                "forbidden_modes": ["action"],
                "history_messages": self._meeting_history_messages(recent_messages),
                "inspection_context": await self._call_build_meeting_inspection_context(room),
                "meeting_context": {
                    "room_id": room_id,
                    "allowed_data_domains": allowed_domains,
                    "denied_data_domains": [domain for domain in _ALL_DATA_DOMAINS if domain not in allowed_domains],
                    "recent_messages": self._meeting_context_messages(recent_messages),
                    "business_binding": self._business_context_from_room(room).model_dump(mode="json"),
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
        message = await self._repo.create_message(
            org_id=self._org_id,
            room_id=room_id,
            user_id=self._user_id,
            username=_MEETING_GENERAL_AGENT_NAME,
            content=answer,
            message_type="agent",
            agent_id=_MEETING_GENERAL_AGENT_ID,
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
                "private_recipient_user_id": self._user_id,
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
            {"event": "message_created", "room_id": room_id, "message": response_message.model_dump(), "private_user_ids": [self._user_id]},
        )
        return MeetingAgentRunResponse(
            selected_subgraph=selected_subgraph,
            answer=answer,
            message=response_message,
            memory_sources=[],
            candidate_memories=[],
        )

    async def _build_meeting_inspection_context(self, room: Any | None = None) -> dict[str, Any]:
        try:
            user = await self._users.get_by_id(self._org_id, self._user_id)
            role = str(getattr(user, "role", "") or ROLE_USER)
            context = await ChatContextService(
                self._session,
                org_id=self._org_id,
                user_id=self._user_id,
                role=role,
            ).build_inspection_context(recent_limit=6, summary_window=12)
            if room is not None:
                context["meeting_business_context"] = self._business_context_from_room(room).model_dump(mode="json")
            return context
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
        *,
        business_context: MeetingBusinessContext | None = None,
    ) -> list[MeetingMemorySourceResponse]:
        if not scope.include_confirmed:
            return []
        items = await self._list_memory_items_for_room(
            org_id=self._org_id,
            room_id=room_id,
            business_context=(business_context or MeetingBusinessContext()).model_dump(mode="json"),
            include_confirmed=True,
            statuses=["active"],
            limit=5,
        )
        items = [item for item in items if self._memory_is_retrievable(item)]
        sources: list[MeetingMemorySourceResponse] = []
        for item in items:
            content_json = item.content_json or {}
            title = str(content_json.get("title") or item.content_summary or item.memory_id)
            sources.append(
                MeetingMemorySourceResponse(
                    memory_id=str(item.memory_id),
                    scope=str(content_json.get("published_scope") or content_json.get("recommended_scope") or "meeting"),
                    title=title,
                    summary=str(item.content_summary or ""),
                )
            )
        return sources

    async def _call_build_meeting_inspection_context(self, room: Any | None = None) -> dict[str, Any]:
        try:
            return await self._build_meeting_inspection_context(room)
        except TypeError as exc:
            if "positional" not in str(exc) and "argument" not in str(exc):
                raise
            return await self._build_meeting_inspection_context()

    async def _list_memory_items_for_room(self, **kwargs) -> list[MemoryItem]:
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
        if status == "active" and content_json.get("superseded_by"):
            return False
        return True

    @staticmethod
    def _memory_is_retrievable(item: MemoryItem) -> bool:
        status = str(getattr(item, "status", "") or "")
        return status == "active" and not (getattr(item, "content_json", None) or {}).get("superseded_by")

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
                "3. 从讨论中提取候选记忆，等你确认后进入已确认记忆。\n"
                "4. 整理会议待办线索，辅助分配责任人和后续跟进。\n"
                "5. 根据会议上下文做检测风险、检测证据、标准解释的讨论型整理。\n\n"
                "如果当前会议已绑定任务、产品、批次或标准，我会优先把这些业务对象作为本次讨论和记忆召回的上下文。"
            )
        if selected_subgraph == "risk_forecast":
            return (
                "我先基于会议上下文和已确认记忆给出讨论型预测建议：\n"
                "1. 优先关注会议中被反复提及的产品、批次和缺陷类型。\n"
                "2. 对缺少检测任务或结果来源的结论标记为待核验。\n"
                "3. 后续接入 inspection_tasks / inspection_results 后，可补充分数化风险排序。\n\n"
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
                "我已根据会议内容生成候选记忆，等待用户确认后才会进入已确认记忆；原始会议聊天不会自动发布到其他会议室。\n\n"
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
        messages = await self._repo.list_recent_messages(
            org_id=self._org_id,
            room_id=room_id,
            limit=80,
        )
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
            statuses=["candidate"],
            limit=100,
        )
        existing_summaries = {str(item.content_summary or "").strip() for item in existing}
        for index, entry in enumerate(candidate_entries, 1):
            summary = str(entry.get("summary") or "").strip()
            if not summary or summary in existing_summaries:
                continue
            memory_id = f"mem_meeting_{uuid.uuid4().hex[:12]}"
            title = self._memory_title_from_line(summary, index)
            content = self._candidate_detail_text(str(entry.get("content") or summary))
            source_message_id = str(entry.get("source_message_id") or "") or None
            memory_type = self._infer_candidate_memory_type(summary, content, intent=intent)
            structured_payload = self._candidate_structured_payload(
                memory_type,
                business_context,
                content,
                room_id=room_id,
                source_message_id=source_message_id,
            )
            memory_category = self._classify_candidate_memory(summary, content, business_context, memory_type=memory_type)
            recommended_scope, recommended_scope_id = self._recommend_memory_scope(
                memory_category,
                content,
                business_context,
                memory_type=memory_type,
            )
            source_refs = self._candidate_source_refs(room_id, source_message_id)
            for ref in structured_payload.get("evidence_refs") or []:
                if ref not in source_refs:
                    source_refs.append(ref)
            shareability = self._memory_shareability(memory_category, business_context, memory_type=memory_type)
            warnings = self._candidate_warnings(
                memory_category,
                content,
                memory_type=memory_type,
                business_context=business_context,
            )
            if memory_type == _MEMORY_TYPE_RISK_INSIGHT:
                shareability["risk_forecast_requires_confirmation"] = True
                shareability["alert_on_confirmed_publish"] = True
            item = MemoryItem(
                id=str(uuid7()),
                memory_id=memory_id,
                org_id=self._org_id,
                user_id=None,
                workspace="app",
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
                    confidence=0.65,
                    source_message_id=source_message_id,
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
                },
            )
        return results

    @staticmethod
    def _candidate_entries_from_messages(messages: list[Any], *, topic: str, max_items: int) -> list[dict[str, Any]]:
        keywords = ("确认", "结论", "决定", "风险", "需要", "建议", "复核", "行动", "待办", "标准", "检测")
        entries: list[dict[str, Any]] = []
        for msg in reversed(messages):
            if str(getattr(msg, "message_type", "user")) not in {"user", "summary", "action_item"}:
                continue
            raw_content = str(getattr(msg, "content", "") or "").strip()
            detail_text = MeetingService._candidate_detail_text(raw_content)
            content = re.sub(r"\s+", " ", detail_text)
            if not content or raw_content.startswith("@"):
                continue
            if any(keyword in content for keyword in keywords) or (topic and topic[:12] in content):
                entries.append(
                    {
                        "summary": content[:260],
                        "content": detail_text,
                        "source_message_id": str(getattr(msg, "id", "") or "") or None,
                    }
                )
            if len(entries) >= max_items:
                break
        if not entries:
            fallback_blocks: list[tuple[str, str | None]] = []
            for msg in messages[-5:]:
                cleaned = MeetingService._candidate_detail_text(str(getattr(msg, "content", "") or "").strip())
                if not cleaned:
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
                return list(reversed(entries[:max_items]))
        return list(reversed(entries[:max_items]))

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
    def _memory_title_from_line(line: str, index: int) -> str:
        compact = re.sub(r"[。！？；;,.，\s]+", " ", line).strip()
        return (compact[:36] or f"会议候选记忆 {index}").strip()

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
                f"风险洞察候选：基于当前会议讨论和已绑定业务对象，{target_text} 近期存在需关注的质检风险。\n"
                f"数据来源：当前会议上下文、已确认记忆和绑定的业务对象。\n"
                f"问题模式：会议中反复出现的质检失败、复核、批次、产品或缺陷线索需要合并观察。\n"
                f"触发条件：多次检测异常、复测不稳定、同批次/同产品问题集中出现，或会议成员持续提示风险。\n"
                f"建议关注窗口：未来 7-14 天。\n"
                f"建议动作：优先复核相关质检任务，跟踪失败率、复测结论和同类问题是否继续出现。\n"
                f"证据摘要：{evidence_text[:900]}"
            )
        else:
            summary = "风险洞察候选：当前会议讨论存在待核验风险线索"
            content = (
                "风险洞察候选：当前会议讨论存在待核验风险线索，但尚未绑定质检任务、产品或批次。\n"
                "数据来源：当前会议上下文。\n"
                "问题模式：需要先补充业务对象绑定后，才能判断是否适合发布到产品、批次、质检风险库或预警中心。\n"
                "建议关注窗口：未来 7-14 天。\n"
                "建议动作：先绑定质检任务、产品或批次，再由主持人确认是否跨范围发布。\n"
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
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "affected_objects": {
                "inspection_task_ids": list(business_context.task_ids),
                "product_ids": list(business_context.product_ids),
                "batch_nos": list(business_context.batch_nos),
                "standard_ids": list(business_context.standard_ids),
            },
            "evidence_refs": [
                item
                for item in [
                    {"type": "meeting_room", "id": room_id},
                    {"type": "meeting_message", "id": source_message_id} if source_message_id else None,
                ]
                if item
            ],
            "source_room_id": room_id,
        }
        if memory_type == _MEMORY_TYPE_RISK_INSIGHT:
            payload.update(
                {
                    "forecast_window": {"label": "未来 7-14 天", "days_min": 7, "days_max": 14},
                    "risk_level": MeetingService._risk_level_from_text(content),
                    "recommended_actions": [
                        "复核相关质检任务和失败样本",
                        "跟踪同产品或同批次复测结果",
                        "必要时在告警中心确认并分派后续处理",
                    ],
                }
            )
        return payload

    @staticmethod
    def _risk_level_from_text(content: str) -> str:
        text = str(content or "").lower()
        if any(term in text for term in ("严重", "critical", "高风险", "连续不合格", "集中失败")):
            return "high"
        if any(term in text for term in ("待核验", "缺少", "未绑定", "不足")):
            return "medium"
        return "medium"

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
    ) -> tuple[str, str | None]:
        if memory_category != _BUSINESS_MEMORY_CATEGORY:
            return "meeting", None
        normalized = content.lower()
        if memory_type == _MEMORY_TYPE_QUALITY_PATTERN:
            return "workspace", _WORKSPACE_RISK_LIBRARY_SCOPE_ID
        if memory_type == _MEMORY_TYPE_RISK_INSIGHT:
            if business_context.batch_nos:
                return "batch", business_context.batch_nos[0]
            if business_context.product_ids:
                return "product", business_context.product_ids[0]
            if business_context.task_ids:
                return "inspection_task", business_context.task_ids[0]
            return "meeting", None
        if memory_type == _MEMORY_TYPE_QUALITY_FACT and business_context.task_ids:
            return "inspection_task", business_context.task_ids[0]
        if business_context.task_ids and any(term in normalized for term in ("任务", "复核", "审核", "判定", "inspection")):
            return "inspection_task", business_context.task_ids[0]
        if business_context.batch_nos and any(term in normalized for term in ("批次", "batch")):
            return "batch", business_context.batch_nos[0]
        if business_context.standard_ids and any(term in normalized for term in ("标准", "standard")):
            return "standard", business_context.standard_ids[0]
        if business_context.product_ids:
            return "product", business_context.product_ids[0]
        return "meeting", None

    @staticmethod
    def _memory_shareability(
        memory_category: str,
        business_context: MeetingBusinessContext,
        *,
        memory_type: str = "decision",
    ) -> dict:
        allowed_scopes = ["meeting"]
        missing_bindings: list[str] = []
        if memory_category == _BUSINESS_MEMORY_CATEGORY:
            if business_context.task_ids:
                allowed_scopes.append("inspection_task")
            elif memory_type == _MEMORY_TYPE_QUALITY_FACT:
                missing_bindings.append("inspection_task")
            if business_context.product_ids:
                allowed_scopes.append("product")
            else:
                missing_bindings.append("product")
            if business_context.batch_nos:
                allowed_scopes.append("batch")
            else:
                missing_bindings.append("batch")
            if business_context.standard_ids:
                allowed_scopes.append("standard")
            else:
                missing_bindings.append("standard")
            if business_context.task_ids or business_context.product_ids or business_context.batch_nos:
                allowed_scopes.append("workspace")
        return {
            "allowed_scopes": allowed_scopes,
            "missing_bindings": sorted(set(missing_bindings)),
            "requires_host_confirmation": True,
            "cross_room_allowed": len(allowed_scopes) > 1,
            "organization_scope_enabled": False,
            "stable_object_visibility": True,
            "related_meeting_delivery": False,
        }

    @staticmethod
    def _candidate_warnings(
        memory_category: str,
        content: str,
        *,
        memory_type: str = "decision",
        business_context: MeetingBusinessContext | None = None,
    ) -> list[str]:
        warnings: list[str] = []
        if memory_category == _REJECTED_MEMORY_CATEGORY:
            warnings.append("候选内容缺少可沉淀信息，不建议确认。")
        if memory_category == _MEETING_MEMORY_CATEGORY:
            warnings.append("该记忆仅适合保存在本会议室，不允许跨业务范围共享。")
        if memory_category == _BUSINESS_MEMORY_CATEGORY and business_context is not None:
            has_any_binding = bool(
                business_context.task_ids
                or business_context.product_ids
                or business_context.batch_nos
                or business_context.standard_ids
            )
            if not has_any_binding:
                warnings.append("该记忆属于质检相关信息，但当前会议室没有绑定质检任务、产品、批次或标准，只能先保存到本会议室。")
            if memory_type == _MEMORY_TYPE_QUALITY_FACT and not business_context.task_ids:
                warnings.append("单次质检事实默认发布到质检任务；当前缺少质检任务绑定，不能发布到产品、批次或预警中心。")
        if memory_type == _MEMORY_TYPE_RISK_INSIGHT:
            warnings.append("风险洞察是预测候选，需人工确认后才可发布；没有绑定业务对象时不能进入预警中心。")
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
        normalized_scope = str(scope or "meeting").strip() or "meeting"
        room_id = self._memory_room_id(item)
        if not room_id:
            raise ForbiddenError("memory is not sourced from a meeting room")
        room = await self._repo.get_room(self._org_id, room_id)
        business_context = self._business_context_from_room(room)
        category = str(content_json.get("memory_category") or _MEETING_MEMORY_CATEGORY)
        if category == _REJECTED_MEMORY_CATEGORY:
            raise ValidationError("rejected_noise memory cannot be confirmed")
        if normalized_scope in {"meeting_room"}:
            normalized_scope = "meeting"
        if normalized_scope == "organization":
            raise ForbiddenError("organization-wide memory publishing is not enabled")
        if normalized_scope not in _MEETING_ONLY_SCOPES and category != _BUSINESS_MEMORY_CATEGORY:
            raise ValidationError("only business_memory can be published outside the meeting room")
        if normalized_scope == "meeting":
            return
        clean_scope_id = str(scope_id or "").strip()
        if not clean_scope_id:
            raise ValidationError(f"{normalized_scope} scope requires scope_id")
        if normalized_scope == "inspection_task":
            owner_user_id = self._user_id if self._role == ROLE_USER else None
            task = await TaskRepository(self._session).get_for_user(
                self._org_id,
                clean_scope_id,
                owner_user_id=owner_user_id,
            )
            if task is None:
                raise ValidationError(f"inspection task {clean_scope_id} not found")
            if clean_scope_id not in set(business_context.task_ids):
                raise ValidationError("inspection_task scope must be bound to this meeting room")
            return
        allowed_by_scope = {
            "product": set(business_context.product_ids),
            "batch": set(business_context.batch_nos),
            "standard": set(business_context.standard_ids),
        }
        if normalized_scope in allowed_by_scope:
            if clean_scope_id not in allowed_by_scope[normalized_scope]:
                raise ValidationError(f"{normalized_scope} scope must be bound to this meeting room")
            return
        if normalized_scope == "workspace":
            memory_type = str(content_json.get("memory_type") or "")
            if clean_scope_id != _WORKSPACE_RISK_LIBRARY_SCOPE_ID:
                raise ValidationError("workspace scope is only available for the quality risk library")
            if memory_type not in {_MEMORY_TYPE_RISK_INSIGHT, _MEMORY_TYPE_QUALITY_PATTERN}:
                raise ValidationError("only risk_insight or quality_pattern can be published to the quality risk library")
            if not (business_context.task_ids or business_context.product_ids or business_context.batch_nos):
                raise ValidationError("quality risk library publishing requires a bound task, product, or batch")
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
            workspace=str(getattr(item, "workspace", "") or "app"),
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
            status="active",
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
        normalized = str(scope or "meeting").strip() or "meeting"
        if normalized == "meeting":
            return "meeting_room", room_id
        if normalized in {"organization", "user", "role", "rag_space"}:
            raise ValidationError(f"{normalized} scope is not available for meeting memory publishing")
        if normalized == "workspace":
            clean_scope_id = str(scope_id or "").strip() or _WORKSPACE_RISK_LIBRARY_SCOPE_ID
            if clean_scope_id != _WORKSPACE_RISK_LIBRARY_SCOPE_ID:
                raise ValidationError("workspace scope is only available for the quality risk library")
            return normalized, clean_scope_id
        if normalized in {
            "inspection_task",
            "product",
            "standard",
            "batch",
        }:
            clean_scope_id = str(scope_id or "").strip()
            if not clean_scope_id:
                raise ValidationError(f"{normalized} scope requires scope_id")
            return normalized, clean_scope_id
        raise ValidationError("unsupported memory publish scope")

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
            "inspection_task": "task_id",
            "product": "product_id",
            "standard": "standard_id",
            "rag_space": "rag_space_id",
            "user": "user_id",
            "role": "role",
            "workspace": "workspace",
            "organization": "organization_id",
            "batch": "batch_no",
        }
        direct_field = field_by_type.get(scope_type)
        if direct_field:
            scope_json[direct_field] = scope_id
        if scope_type == "meeting_room":
            scope_json["meeting_room_id"] = scope_id
        if scope_type == "standard":
            scope_json["spec_code"] = scope_id
        return scope_json

    @staticmethod
    def _memory_scope_label(scope_type: str) -> str:
        return {
            "meeting_room": "本会议室",
            "inspection_task": "质检任务",
            "product": "产品范围",
            "batch": "批次范围",
            "standard": "标准范围",
            "workspace": "质检风险库",
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
            scope=str(content_json.get("published_scope") or content_json.get("recommended_scope") or "meeting"),
            scope_type=scope_type,
            scope_id=scope_id,
            memory_category=str(content_json.get("memory_category") or _MEETING_MEMORY_CATEGORY),
            recommended_scope=str(content_json.get("recommended_scope") or "meeting"),
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
            publish_reason=content_json.get("publish_reason"),
            version_parent_id=(
                str(content_json.get("version_parent_id") or getattr(item, "version_parent_id", "") or "") or None
            ),
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
        raw_values = values if isinstance(values, (list, tuple, set)) else re.split(r"[\s,，;；]+", str(values))
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
    def _with_business_context(policy: dict | None, context: MeetingBusinessContext) -> dict:
        next_policy = dict(policy or {})
        next_policy["business_context"] = context.model_dump(mode="json")
        return next_policy

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

    def _default_meeting_domains(self) -> set[str]:
        return {"meeting", "memory"}

    def _effective_domains_for_create(self, requested: list[str] | None) -> list[str]:
        role_allowed = self._role_allowed_domains()
        requested_domains = self._normalize_domain_list(requested)
        base_domains = set(requested_domains or self._default_meeting_domains())
        effective = base_domains & role_allowed
        if "meeting" in role_allowed:
            effective.add("meeting")
        if not effective and "memory" in role_allowed:
            effective.add("memory")
        return self._ordered_domains(effective)

    def _effective_domains_for_room(self, room: Any) -> list[str]:
        stored_domains = self._normalize_domain_list(getattr(room, "allowed_data_domains", None))
        role_allowed = self._role_allowed_domains()
        effective = set(stored_domains or self._default_meeting_domains()) & role_allowed
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

        cleaned_question = self._clean_general_agent_query(question)
        normalized = str(cleaned_question or "").lower()
        compact = _normalize_name(cleaned_question)
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
