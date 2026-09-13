from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any

from agent.adapters.factory import AgentAdapterFactory
from fastapi import UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.ids import uuid7
from app.core.permissions import (
    ROLE_ADMIN,
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
from app.models.memory import MemoryCandidateSupport, MemoryEvidence, MemoryItem, MemoryOrigin
from app.repositories.meeting_repo import MeetingRepository
from app.repositories.inspection_spec_repo import InspectionSpecRepository
from app.repositories.inspection_standard_library_repo import InspectionStandardLibraryRepository
from app.repositories.product_master_repo import ProductMasterRepository
from app.repositories.task_repo import TaskRepository
from app.repositories.user_repo import UserRepository
from app.repositories.memory_repo import MemorySyncOutboxRepository
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
    MeetingBusinessObjectCandidateResponse,
    MeetingBusinessObjectCorrectionRequest,
    MeetingBusinessContextTask,
    MeetingBusinessContextUpdateRequest,
    MeetingCandidateMemoryResponse,
    MeetingContextPreviewResponse,
    MeetingMemoryExtractRequest,
    MeetingMemoryDisputeRequest,
    MeetingMemoryResponse,
    MeetingMemoryShareApprovalResponse,
    MeetingMemoryShareCreateRequest,
    MeetingMemoryShareCreateResponse,
    MeetingMemoryShareDecisionRequest,
    MeetingMemoryShareRejectRequest,
    MeetingAgentShareRequest,
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
from app.schemas.qdl import (
    QDLApplicability,
    QDLClaim,
    QDLConsensus,
    QDLDocument,
    QDLEntity,
    QDLEvidence,
    QDLGovernance,
    QDLKnowledgeProperties,
    QDLLifecycle,
    QDLProvenance,
    QDLRelation,
    knowledge_level_for_memory_type,
    parse_qdl,
)
from app.services.agent_manager_service import AgentManagerService
from app.services.chat_context_service import ChatContextService
from agent.response.trust_protocol import build_trust_answer_protocol
from app.services.meeting_agent_cancel_registry import meeting_agent_cancel_registry
from app.services.meeting_agent_service import MeetingAgentService
from app.services.meeting_qdl_extraction_service import MeetingQDLExtractionService
from app.services.knowledge_tunnel_service import KnowledgeTunnelService
from app.services.memory_service import MemoryService
from app.services.memory_vector_service import CANDIDATE_MEMORY_COLLECTION, MEMORY_COLLECTION
from app.services.rag_space_service import RagSpaceService
from app.services.stream_service import collab_stream_broker, meeting_stream_broker
from infra.database.session import get_session

_MENTION_DELIMITER_RE = re.compile(r"(?=$|[\s,.;:!?，。；：！？、）)])")
_MEETING_AI_AGENT_NAME = "AI助手"
_MEETING_GENERAL_AGENT_ID = "general_agent"
_MEETING_GENERAL_AGENT_NAME = "会议Agent"
logger = logging.getLogger(__name__)

_MESSAGE_RECALL_WINDOW = timedelta(minutes=2)
_AGENT_RUN_CANCELLED_MESSAGE = "会议Agent回复已停止"
_PUBLIC_AGENT_WORKFLOWS: dict[tuple[str, str], str] = {}

_ALL_DATA_DOMAINS = list(ALL_DATA_DOMAINS)
_ROOM_QUERY_EXAMPLES = ["总结当前会议。", "提取会议待办。", "把刚才讨论整理成待确认知识。"]
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
_INTERACTION_PRIVATE_CHAT = "private_chat"
_INTERACTION_PUBLIC_MENTION = "public_mention"
_INTERACTION_AUTO_PARTICIPATION = "auto_participation"
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

    async def _update_memory_item_compat(self, **kwargs):
        """Write unified governance fields while tolerating one-release legacy repository adapters."""
        governance_keys = {
            "applicability_json",
            "review_status",
            "readiness_status",
            "readiness_blockers",
            "governance_target_scope_type",
            "governance_target_scope_id",
            "migration_review_required",
            "migration_review_reason",
        }
        try:
            return await self._repo.update_memory_item(**kwargs)
        except TypeError as exc:
            if "unexpected keyword argument" not in str(exc):
                raise
            legacy_kwargs = {key: value for key, value in kwargs.items() if key not in governance_keys}
            item = await self._repo.update_memory_item(**legacy_kwargs)
            if item is not None:
                for key in governance_keys:
                    if key in kwargs:
                        setattr(item, key, kwargs[key])
                flush = getattr(self._session, "flush", None)
                if callable(flush):
                    await flush()
            return item

    @staticmethod
    def _normalize_auto_participation_mode(value: str | None) -> str:
        mode = str(value or "off").strip().lower()
        if mode == "shadow":
            return "off"
        if mode not in {"off", "live"}:
            raise ValidationError("auto participation mode must be off or live")
        return mode

    @classmethod
    def _auto_participation_mode(cls, room: Any | None) -> str:
        policy = getattr(room, "audit_policy", None) if room is not None else None
        if not isinstance(policy, dict):
            return "off"
        try:
            return cls._normalize_auto_participation_mode(policy.get("auto_participation_mode"))
        except ValidationError:
            return "off"

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
        auto_participation_mode: str = "off",
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
                "auto_participation_mode": self._normalize_auto_participation_mode(auto_participation_mode),
            },
        )
        response = (await self._serialize_rooms([room]))[0]
        await self._session.commit()
        return response

    async def join_room(self, access_code: str, password: str | None = None) -> MeetingRoomResponse:
        room = await self._repo.get_room_by_code(self._org_id, access_code.strip().upper())
        if not room:
            raise NotFoundError("meeting room not found")
        if str(room.status) != "active":
            raise ForbiddenError("meeting room is not active")
        if room.password_hash and not verify_password(password or "", room.password_hash):
            raise ForbiddenError("meeting password is invalid")
        await self._repo.add_member(org_id=self._org_id, room_id=str(room.id), user_id=self._user_id)
        response = (await self._serialize_rooms([room]))[0]
        await self._session.commit()
        return response

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
        auto_participation_mode: str | None = None,
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
        audit_policy = None
        if auto_participation_mode is not None:
            audit_policy = dict(getattr(room, "audit_policy", None) or {})
            audit_policy["auto_participation_mode"] = self._normalize_auto_participation_mode(
                auto_participation_mode
            )
        updated = await self._repo.update_room(
            self._org_id,
            room_id,
            title=title.strip()[:120] if title else None,
            visibility=visibility,
            allowed_data_domains=effective_domains,
            memory_policy=memory_policy,
            audit_policy=audit_policy,
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
        should_extract_knowledge = False
        if hasattr(self._repo, "upsert_context_summary"):
            rows = await self._list_recent_public_messages(room_id=room_id, limit=120)
            previous = await self._context_summary_json(
                room_id=room_id,
                context_scope="room",
                user_key="public",
            )
            if rows:
                await self._repo.upsert_context_summary(
                    org_id=self._org_id,
                    room_id=room_id,
                    context_scope="room",
                    user_key="public",
                    through_seq=max(int(getattr(row, "seq_no", 0) or 0) for row in rows),
                    summary_json=self._build_rolling_summary(rows, previous),
                )
                should_extract_knowledge = True
        await self._publish_system_message(room_id, "会议已结束，后续消息发送与新成员加入已暂停。")
        if should_extract_knowledge:
            self._schedule_public_knowledge_extraction(
                room_id,
                max_items=5,
                topic="会议结束自动整理公共知识",
            )
        return (await self._serialize_rooms([room]))[0]

    async def list_messages(
        self,
        room_id: str,
        *,
        after_seq: int | None = None,
        before_seq: int | None = None,
        limit: int = 200,
    ) -> list[MeetingMessageResponse]:
        await self._ensure_member(room_id)
        if after_seq is not None and before_seq is not None:
            raise ValidationError("after_seq and before_seq cannot be used together")
        try:
            messages = await self._repo.list_messages(
                org_id=self._org_id,
                room_id=room_id,
                after_seq=after_seq,
                before_seq=before_seq,
                limit=limit,
                visible_user_id=self._user_id,
            )
        except TypeError:
            messages = await self._repo.list_messages(
                org_id=self._org_id,
                room_id=room_id,
                after_seq=int(after_seq or 0),
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
        await self._invalidate_agent_replies_for_source(room_id, message_id)
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
        await self._invalidate_agent_replies_for_source(room_id, message_id, recalled=True)
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

    async def share_agent_answer(
        self,
        room_id: str,
        request: MeetingAgentShareRequest,
    ) -> MeetingMessageResponse:
        await self._ensure_active_member(room_id)
        answer = await self._repo.get_message(self._org_id, room_id, request.answer_message_id)
        if not answer or str(getattr(answer, "agent_id", "")) != _MEETING_GENERAL_AGENT_ID:
            raise NotFoundError("meeting Agent answer not found")
        if str(getattr(answer, "user_id", "")) != self._user_id:
            raise ForbiddenError("only your own private Agent answer can be shared")
        answer_metadata = getattr(answer, "metadata_json", None) or {}
        answer_recipient = self._message_recipient_user_id(answer)
        answer_audience = str(answer_metadata.get("audience_scope_id") or "")
        answer_visibility = str(
            answer_metadata.get("visibility")
            or answer_metadata.get("response_visibility")
            or ("private" if answer_recipient else "room")
        )
        if answer_visibility != _RESPONSE_VISIBILITY_PRIVATE or self._user_id not in {
            answer_recipient,
            answer_audience,
        }:
            raise ForbiddenError("meeting Agent answer is not visible to current user")
        clean_content = request.content.strip()
        if not clean_content:
            raise ValidationError("shared content required")
        user = await self._users.get_by_id(self._org_id, self._user_id)
        username = user.username if user else self._user_id[-8:]
        source_ids = list(dict.fromkeys(
            item.strip() for item in request.source_message_ids if item and item.strip()
        ))[:20]
        for source_id in source_ids:
            source = await self._repo.get_message(self._org_id, room_id, source_id)
            if source is None:
                raise ValidationError("shared source message not found")
            source_metadata = getattr(source, "metadata_json", None) or {}
            source_visibility = str(
                source_metadata.get("visibility")
                or ("private" if self._message_recipient_user_id(source) else "room")
            )
            if self._message_recipient_user_id(source) or source_visibility == _RESPONSE_VISIBILITY_PRIVATE:
                raise ForbiddenError("private messages cannot be shared as public sources")
        message = await self._repo.create_message(
            org_id=self._org_id,
            room_id=room_id,
            user_id=self._user_id,
            username=username,
            content=clean_content,
            message_type="user",
            metadata_json={
                "shared_agent_answer": True,
                "shared_by_user_id": self._user_id,
                "answer_message_id": str(answer.id),
                "source_message_ids": source_ids,
                "quote_snapshot": {
                    "source": "agent",
                    "author": _MEETING_GENERAL_AGENT_NAME,
                    "content": clean_content,
                    "created_at": (
                        getattr(answer, "created_at", None).isoformat()
                        if getattr(answer, "created_at", None)
                        else None
                    ),
                },
                "visibility": _RESPONSE_VISIBILITY_ROOM,
                "confirmation_status": "unconfirmed_ai_suggestion",
            },
        )
        response = MeetingMessageResponse.model_validate(message)
        await self._session.commit()
        await self._publish_message_event(room_id, response)
        return response

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
                self._invoke_general_agent_reply(
                    room_id=room_id,
                    query=clean_content,
                    question_message_id=str(message.id),
                    question_revision=str(getattr(message, "updated_at", None) or message.id),
                )
            )
        room = await self._repo.get_room(self._org_id, room_id)
        auto_participation_mode = self._auto_participation_mode(room)
        should_evaluate_auto_participation = bool(
            auto_participation_mode == "live"
            and clean_content
            and not private_recipient_user_id
            and not skip_agent_trigger
            and not agent_alias_mentioned
        )
        if should_evaluate_auto_participation:
            asyncio.create_task(
                self._evaluate_auto_participation(
                    room_id=room_id,
                    message_id=str(message.id),
                    mode=auto_participation_mode,
                )
            )
        if (
            clean_content
            and not private_recipient_user_id
            and not agent_sidecar_private
            and hasattr(self._repo, "upsert_context_summary")
        ):
            asyncio.create_task(
                self._refresh_public_context(
                    room_id=room_id,
                    message_id=str(message.id),
                )
            )
        return response

    async def _evaluate_auto_participation(self, *, room_id: str, message_id: str, mode: str) -> None:
        from app.services.meeting_auto_participation_service import MeetingAutoParticipationService

        await MeetingAutoParticipationService.evaluate_trigger(
            room_id=room_id,
            message_id=message_id,
            org_id=self._org_id,
            user_id=self._user_id,
            user_role=self._role,
            expected_mode=mode,
        )

    async def list_business_objects(
        self,
        room_id: str,
    ) -> list[MeetingBusinessObjectCandidateResponse]:
        await self._ensure_member(room_id)
        rows = await self._repo.list_business_object_candidates(
            org_id=self._org_id,
            room_id=room_id,
        )
        return [MeetingBusinessObjectCandidateResponse.model_validate(row) for row in rows]

    async def correct_business_object(
        self,
        room_id: str,
        request: MeetingBusinessObjectCorrectionRequest,
    ) -> MeetingBusinessObjectCandidateResponse:
        await self._ensure_member(room_id)
        rows = await self._repo.list_business_object_candidates(
            org_id=self._org_id,
            room_id=room_id,
        )
        correction = request.correction.strip()
        parsed = re.search(
            r"(?:不是|并非)\s*([A-Za-z0-9_.-]{2,128})\s*[，,、;；]?\s*(?:是|应为|改为)\s*([A-Za-z0-9_.-]{2,128})",
            correction,
            flags=re.IGNORECASE,
        )
        old_value = parsed.group(1) if parsed else ""
        corrected_value = str(request.corrected_value or (parsed.group(2) if parsed else "")).strip()
        if not old_value:
            removal = re.search(
                r"(?:删除|移除|忽略|不是讨论对象)\s*([A-Za-z0-9_.-]{2,128})",
                correction,
                flags=re.IGNORECASE,
            )
            old_value = removal.group(1) if removal else ""
        candidate = next(
            (
                row for row in rows
                if request.candidate_id and str(row.id) == request.candidate_id
            ),
            None,
        ) or next(
            (
                row for row in rows
                if old_value and str(row.object_value).lower() == old_value.lower()
            ),
            None,
        )
        if candidate is None:
            raise NotFoundError("discussion object candidate not found")
        if request.action == "reject":
            updated = await self._repo.update_business_object_candidate(
                org_id=self._org_id,
                room_id=room_id,
                candidate_id=str(candidate.id),
                resolved_value=None,
                status="rejected",
                resolved_by=self._user_id,
                evidence_json={
                    "correction": correction,
                    "previous_value": str(candidate.object_value),
                    "action": "reject",
                },
            )
            if updated is None:
                raise NotFoundError("discussion object candidate not found")
            await self._session.commit()
            return MeetingBusinessObjectCandidateResponse.model_validate(updated)
        if not corrected_value:
            raise ValidationError("corrected object value required")
        verified = await self._verify_business_object(
            str(request.object_type or candidate.object_type or "unknown"),
            corrected_value,
        )
        next_status = "verified" if verified else "corrected"
        resolved_type = verified[0] if verified else str(candidate.object_type or "unknown")
        resolved_value = verified[1] if verified else corrected_value
        updated = await self._repo.update_business_object_candidate(
            org_id=self._org_id,
            room_id=room_id,
            candidate_id=str(candidate.id),
            resolved_value=resolved_value,
            status=next_status,
            resolved_by=self._user_id,
            evidence_json={
                "correction": correction,
                "previous_value": str(candidate.object_value),
                "corrected_value": resolved_value,
                "resolved_type": resolved_type,
                "system_verified": bool(verified),
            },
        )
        if updated is None:
            raise NotFoundError("discussion object candidate not found")
        if verified:
            await self._adopt_verified_business_object(room_id, *verified)
        await self._session.commit()
        return MeetingBusinessObjectCandidateResponse.model_validate(updated)

    async def _verify_business_object(
        self,
        object_type: str,
        value: str,
    ) -> tuple[str, str, MeetingBusinessContext] | None:
        clean_value = str(value or "").strip()
        if not clean_value:
            return None
        matches: list[tuple[str, str, MeetingBusinessContext]] = []
        if object_type in {"task", "unknown"}:
            try:
                task_id = str(uuid.UUID(clean_value))
            except (TypeError, ValueError):
                task_id = ""
            owner_user_id = self._user_id if self._role == ROLE_USER else None
            task = (
                await TaskRepository(self._session).get_for_user(
                    self._org_id,
                    task_id,
                    owner_user_id=owner_user_id,
                )
                if task_id
                else None
            )
            if task is not None:
                matches.append((
                    "task",
                    str(task.id),
                    MeetingBusinessContext(
                        task_ids=[str(task.id)],
                        product_ids=[str(getattr(task, "product_id", "") or "")],
                        batch_nos=[],
                        standard_ids=[str(getattr(task, "spec_code", "") or "")],
                        tasks=[],
                    ),
                ))
        product_repo = ProductMasterRepository(self._session)
        if object_type in {"product", "unknown"}:
            product_rows = [
                row
                for row in (
                    await product_repo.get_line_by_code(self._org_id, clean_value),
                    await product_repo.get_sku_by_code(self._org_id, clean_value),
                )
                if row is not None
            ]
            if len(product_rows) == 1:
                matches.append((
                    "product",
                    str(getattr(product_rows[0], "code", clean_value) or clean_value),
                    MeetingBusinessContext(product_ids=[clean_value]),
                ))
        if object_type in {"batch", "unknown"}:
            batch_rows = [
                row for row in await product_repo.list_batches(self._org_id, include_inactive=False)
                if str(getattr(row, "batch_no", "") or "").lower() == clean_value.lower()
            ]
            if len(batch_rows) == 1:
                matches.append((
                    "batch",
                    str(batch_rows[0].batch_no),
                    MeetingBusinessContext(batch_nos=[str(batch_rows[0].batch_no)]),
                ))
        if object_type in {"standard", "unknown"}:
            spec = await InspectionSpecRepository(self._session).get_active_spec(self._org_id, clean_value)
            library = await InspectionStandardLibraryRepository(self._session).get_active_by_spec_code(
                self._org_id,
                clean_value,
            )
            if spec is not None or library is not None:
                matches.append((
                    "standard",
                    clean_value,
                    MeetingBusinessContext(standard_ids=[clean_value]),
                ))
        unique: dict[tuple[str, str], tuple[str, str, MeetingBusinessContext]] = {
            (item[0], item[1].lower()): item for item in matches
        }
        return next(iter(unique.values())) if len(unique) == 1 else None

    async def _adopt_verified_business_object(
        self,
        room_id: str,
        object_type: str,
        resolved_value: str,
        detected_context: MeetingBusinessContext,
    ) -> None:
        room = await self._repo.get_room(self._org_id, room_id)
        if room is None:
            return
        context = self._merge_business_context(
            self._business_context_from_room(room),
            detected_context,
        )
        await self._repo.update_room(
            self._org_id,
            room_id,
            memory_policy=self._with_business_context(getattr(room, "memory_policy", None), context),
        )

    async def _refresh_public_context(self, *, room_id: str, message_id: str) -> None:
        try:
            async with get_session() as session:
                service = MeetingService(session, self._org_id, self._user_id, role=self._role)
                message = await service._repo.get_message(self._org_id, room_id, message_id)
                if not message or service._message_recipient_user_id(message):
                    return
                metadata = getattr(message, "metadata_json", None) or {}
                if metadata.get("visibility") == _RESPONSE_VISIBILITY_PRIVATE or metadata.get("recalled_at"):
                    return
                for mention in service._extract_business_object_mentions(str(message.content or "")):
                    verified = (
                        await service._verify_business_object(
                            mention["object_type"],
                            mention["object_value"],
                        )
                        if float(mention["confidence"]) >= 0.75
                        else None
                    )
                    candidate = await service._repo.upsert_business_object_candidate(
                        org_id=self._org_id,
                        room_id=room_id,
                        object_type=verified[0] if verified else mention["object_type"],
                        object_value=mention["object_value"],
                        confidence=1.0 if verified else mention["confidence"],
                        source_message_id=message_id,
                        status="verified" if verified else "candidate",
                        created_by=self._user_id,
                        evidence_json={
                            "source": "automatic_mention_detection",
                            "system_verified": bool(verified),
                            **({"resolved_type": verified[0], "resolved_value": verified[1]} if verified else {}),
                        },
                    )
                    if verified:
                        await service._repo.update_business_object_candidate(
                            org_id=self._org_id,
                            room_id=room_id,
                            candidate_id=str(candidate.id),
                            resolved_value=verified[1],
                            status="verified",
                            resolved_by=self._user_id,
                            evidence_json={"auto_adopted": True},
                        )
                        await service._adopt_verified_business_object(room_id, *verified)
                rows = await service._list_recent_public_messages(room_id=room_id, limit=80)
                public_rows = [
                    row for row in rows
                    if str(getattr(row, "content", "") or "").strip()
                    and not (getattr(row, "metadata_json", None) or {}).get("recalled_at")
                ]
                through_seq = max((int(getattr(row, "seq_no", 0) or 0) for row in public_rows), default=0)
                summary_row = await service._repo.get_context_summary(
                    org_id=self._org_id,
                    room_id=room_id,
                    context_scope="room",
                    user_key="public",
                )
                since_seq = int(getattr(summary_row, "through_seq", 0) or 0)
                new_rows = [row for row in public_rows if int(getattr(row, "seq_no", 0) or 0) > since_seq]
                new_chars = sum(len(str(getattr(row, "content", "") or "")) for row in new_rows)
                conclusion_changed = bool(re.search(
                    r"(?:明确结论|最终结论|确认(?:为|：|:)|决定(?:为|：|:)|改为|纠正为|不再采用)",
                    str(message.content or ""),
                ))
                should_refresh = len(new_rows) >= 8 or new_chars >= 6000 or conclusion_changed
                if should_refresh:
                    await service._repo.upsert_context_summary(
                        org_id=self._org_id,
                        room_id=room_id,
                        context_scope="room",
                        user_key="public",
                        through_seq=through_seq,
                        summary_json=service._build_rolling_summary(
                            public_rows,
                            getattr(summary_row, "summary_json", None),
                        ),
                    )
                    await service._extract_candidate_memories_from_messages(
                        room_id,
                        max_items=3,
                        topic="自动整理公共会议知识",
                    )
                await session.commit()
        except Exception:
            logger.exception("meeting public context refresh failed room_id=%s", room_id)

    def _schedule_public_knowledge_extraction(
        self,
        room_id: str,
        *,
        max_items: int,
        topic: str,
    ) -> None:
        asyncio.create_task(
            self._extract_public_knowledge_background(
                room_id,
                max_items=max_items,
                topic=topic,
            )
        )

    async def _extract_public_knowledge_background(
        self,
        room_id: str,
        *,
        max_items: int,
        topic: str,
    ) -> None:
        try:
            async with get_session() as session:
                service = MeetingService(
                    session,
                    self._org_id,
                    self._user_id,
                    role=self._role,
                )
                await service._extract_candidate_memories_from_messages(
                    room_id,
                    max_items=max_items,
                    topic=topic,
                )
                await session.commit()
        except Exception:
            logger.exception("meeting background QDL extraction failed room_id=%s", room_id)

    @staticmethod
    def _extract_business_object_mentions(content: str) -> list[dict[str, Any]]:
        patterns = {
            "task": r"(?:任务|task)\s*[#：:]?\s*([A-Za-z0-9_.-]{2,128})",
            "product": r"(?:产品|product)\s*[#：:]?\s*([A-Za-z0-9_.-]{2,128})",
            "batch": r"(?:批次|batch)\s*[#：:]?\s*([A-Za-z0-9_.-]{2,128})",
            "standard": r"(?:标准|standard)\s*[#：:]?\s*([A-Za-z0-9_.-]{2,128})",
        }
        found: list[dict[str, Any]] = []
        for object_type, pattern in patterns.items():
            for match in re.finditer(pattern, content, flags=re.IGNORECASE):
                value = match.group(1).strip().rstrip(".,，。;；")
                if value:
                    found.append({
                        "object_type": object_type,
                        "object_value": value,
                        "confidence": 0.82,
                    })
        if not found and any(term in content for term in ("放行", "复核", "质检", "判定")):
            for value in re.findall(r"\b([A-Za-z]+\d{1,8})\b", content):
                found.append({
                    "object_type": "unknown",
                    "object_value": value,
                    "confidence": 0.58,
                })
        unique: dict[tuple[str, str], dict[str, Any]] = {}
        for item in found:
            unique[(item["object_type"], item["object_value"].lower())] = item
        return list(unique.values())[:20]

    @staticmethod
    def _build_rolling_summary(
        messages: list[Any],
        previous_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        previous = previous_summary if isinstance(previous_summary, dict) else {}
        current_snippets = [
            {
                "message_id": str(getattr(message, "id", "") or ""),
                "seq_no": int(getattr(message, "seq_no", 0) or 0),
                "author": str(getattr(message, "username", "") or ""),
                "content": str(getattr(message, "content", "") or "")[:500],
                "is_ai_suggestion": str(getattr(message, "message_type", "")) in {"agent", "agent_streaming"},
            }
            for message in messages[-24:]
        ]
        snippets_by_id: dict[str, dict[str, Any]] = {}
        for item in [*list(previous.get("discussion_summary") or []), *current_snippets]:
            if not isinstance(item, dict):
                continue
            message_id = str(item.get("message_id") or "").strip()
            if message_id:
                snippets_by_id[message_id] = item
        snippets = sorted(
            snippets_by_id.values(),
            key=lambda item: int(item.get("seq_no") or 0),
        )[-80:]
        return {
            "discussion_summary": snippets,
            "confirmed_conclusions": list(previous.get("confirmed_conclusions") or [])[-20:],
            "action_items": list(previous.get("action_items") or [])[-20:],
            "disputes_and_risks": list(previous.get("disputes_and_risks") or [])[-20:],
            "next_suggestions": list(previous.get("next_suggestions") or [])[-20:],
            "source_message_ids": [item["message_id"] for item in snippets],
        }

    @staticmethod
    def _merge_discussion_relations(
        existing: list[dict] | None,
        target_memory_ids: list[str],
        *,
        relation_type: str,
        status: str,
        created_by: str | None = None,
        note: str | None = None,
    ) -> list[dict[str, Any]]:
        allowed = {"support", "supplement", "oppose", "revise", "confirm"}
        normalized_type = relation_type if relation_type in allowed else "supplement"
        relations = [dict(item) for item in list(existing or []) if isinstance(item, dict)]
        for target_memory_id in MeetingService._dedupe_text_values(target_memory_ids, limit=20, max_length=64):
            next_relation = {
                "target_memory_id": target_memory_id,
                "relation_type": normalized_type,
                "status": status,
                "updated_at": datetime.utcnow().isoformat(),
                **({"created_by": created_by} if created_by else {}),
                **({"note": note[:500]} if note else {}),
            }
            existing_index = next((
                index for index, item in enumerate(relations)
                if str(item.get("target_memory_id") or "") == target_memory_id
                and str(item.get("relation_type") or "") == normalized_type
            ), None)
            if existing_index is None:
                relations.append(next_relation)
            else:
                relations[existing_index] = {**relations[existing_index], **next_relation}
        return relations[-50:]

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

        if _is_valid_uuid(agent_id):
            agent_def = await self._repo.get_visible_agent_definition(self._org_id, agent_id)
            if agent_def:
                AgentAdapterFactory.ensure_supported(getattr(agent_def, "adapter_type", "llm"))

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
        response_visibility = self._response_visibility_for_request(request)
        public_request_restricted = bool(
            response_visibility == _RESPONSE_VISIBILITY_ROOM
            and (
                access.response_visibility == _RESPONSE_VISIBILITY_PRIVATE
                or request.memory_scope.include_personal_authorized
                or request.memory_scope.include_user
                or await self._public_request_uses_private_sources(room_id, request)
            )
        )
        private_user_ids = self._private_user_ids_for_visibility(response_visibility)
        if access.decision == "denied" or public_request_restricted:
            workflow_run_id = str(request.workflow_run_id or uuid7())
            agent_message_id = self._agent_message_id_for_request(room_id, request)
            denial_answer = (
                "该公开问题涉及私人内容或受限数据。会议Agent未读取这些内容；"
                "请在“我的对话”中私下询问，或只引用可公开来源。"
                if public_request_restricted
                else "当前请求超出你的会议室权限范围，无法回答该问题。"
            )
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
                    **self._interaction_message_metadata(request, workflow_run_id=workflow_run_id),
                    **self._auto_participation_message_metadata(request),
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
        agent_message_id = self._agent_message_id_for_request(room_id, request)
        attachment_echo = self._normalize_message_attachments(request.attachments)
        response_metadata = self._response_visibility_metadata(response_visibility, room_id=room_id)
        private_user_ids = self._private_user_ids_for_visibility(response_visibility)
        if response_visibility == _RESPONSE_VISIBILITY_ROOM and request.question_message_id:
            _PUBLIC_AGENT_WORKFLOWS[(room_id, request.question_message_id)] = workflow_run_id
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
                "response_visibility": response_visibility,
                "interaction_mode": request.interaction_mode,
                "question_message_id": request.question_message_id,
                "trigger_message_id": request.trigger_message_id,
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
            effective_memory_scope = (
                request.memory_scope
                if response_visibility == _RESPONSE_VISIBILITY_PRIVATE
                else MeetingMemoryScopeRequest(
                    include_meeting=True,
                    include_confirmed=True,
                    include_personal_authorized=False,
                    include_user=False,
                    include_agent=True,
                    include_org_space=True,
                )
            )
            memory_sources = await self._collect_memory_sources(
                room_id,
                effective_memory_scope,
                business_context=business_context,
            )
            recent_messages = (
                await self._list_private_agent_context_messages(room_id=room_id, limit=80)
                if response_visibility == _RESPONSE_VISIBILITY_PRIVATE
                else await self._list_recent_public_messages(room_id=room_id, limit=80)
            )
            rolling_summary = await self._context_summary_json(
                room_id=room_id,
                context_scope="private" if response_visibility == _RESPONSE_VISIBILITY_PRIVATE else "room",
                user_key=self._user_id if response_visibility == _RESPONSE_VISIBILITY_PRIVATE else "public",
            )
            if self._is_general_agent_cancelled(room_id, workflow_run_id):
                raise asyncio.CancelledError()
            answer = self._build_general_agent_answer(
                selected_subgraph=selected_subgraph,
                query=request.query,
                messages=recent_messages,
                memory_sources=memory_sources,
                rolling_summary=rolling_summary,
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

            direct_citations = [
                *[
                    {"type": "memory", "id": item.memory_id, "scope": item.scope}
                    for item in memory_sources
                ],
            ]
            trust_protocol = build_trust_answer_protocol(
                question=request.query,
                answer=answer,
                status="completed",
                citations=direct_citations,
                route_trace={
                    "reason": selected_subgraph,
                    "observations": [
                        {
                            "step_id": "meeting_context",
                            "capability_key": "meeting.context",
                            "status": "success",
                            "summary": "已读取当前会议上下文和可见记忆。",
                            "artifact_ids": [item.memory_id for item in memory_sources],
                        }
                    ],
                },
                trace_id=workflow_run_id,
                route_confidence=1.0,
            ).model_dump(mode="json")

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
                    "trust_protocol": trust_protocol,
                    **response_metadata,
                    **self._interaction_message_metadata(request, workflow_run_id=workflow_run_id),
                    **({"attachment_echo": attachment_echo} if attachment_echo else {}),
                    **self._auto_participation_message_metadata(request),
                },
            )
            response_message = MeetingMessageResponse.model_validate(message)
            if response_visibility == _RESPONSE_VISIBILITY_PRIVATE:
                await self._refresh_private_context_summary(
                    room_id=room_id,
                    messages=[*recent_messages, message],
                )
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
                trust_protocol=trust_protocol,
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
                    "response_visibility": response_visibility,
                    "interaction_mode": request.interaction_mode,
                    "question_message_id": request.question_message_id,
                    "trigger_message_id": request.trigger_message_id,
                    **({"private_user_ids": private_user_ids} if private_user_ids else {}),
                },
            )
            raise
        finally:
            meeting_agent_cancel_registry.clear(room_id, workflow_run_id)
            if request.question_message_id:
                _PUBLIC_AGENT_WORKFLOWS.pop((room_id, request.question_message_id), None)

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
        responses = [self._serialize_memory_item(item, room_id=room_id) for item in items]
        return await self._enrich_memory_share_state(responses)

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
        content_json["discussion_relations"] = self._merge_discussion_relations(
            list(content_json.get("discussion_relations") or []),
            [str(item) for item in list(content_json.get("related_memory_ids") or [])],
            relation_type="confirm",
            status="confirmed",
            created_by=self._user_id,
            note="人工确认该知识及其关联",
        )
        content_json["confirmed_by"] = self._user_id
        content_json["confirmed_at"] = datetime.utcnow().isoformat()
        requested_scope = self._normalize_memory_scope((request.scope if request else None) or "meeting_room")
        requested_scope_id = str((request.scope_id if request else None) or "").strip()
        confirms_current_room = (
            requested_scope == _MEMORY_SCOPE_MEETING_ROOM
            and requested_scope_id in {"", "current", room_id}
        )
        if not confirms_current_room:
            await self._ensure_memory_publish_allowed(
                item,
                requested_scope,
                requested_scope_id or "current",
                content_json,
                transfer=True,
            )
            local_request = (request or MeetingMemoryUpdateRequest()).model_copy(
                update={"scope": _MEMORY_SCOPE_MEETING_ROOM, "scope_id": room_id}
            )
            local_memory = await self.confirm_memory(memory_id, local_request)
            compat_key_source = "|".join(
                [
                    self._org_id,
                    self._user_id,
                    str(local_memory.memory_id),
                    requested_scope,
                    requested_scope_id or "current",
                    str((request.publish_reason if request else None) or ""),
                ]
            )
            share_result = await self.create_memory_share_request(
                local_memory.memory_id,
                MeetingMemoryShareCreateRequest(
                    target_scope_type=requested_scope,
                    target_scope_id=requested_scope_id or "current",
                    share_reason=(request.publish_reason if request else None),
                    idempotency_key=f"confirm-compat:{hashlib.sha256(compat_key_source.encode()).hexdigest()[:48]}",
                ),
            )
            return share_result.memory
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
        content_json["governance_status"] = "confirmed"
        content_json["qdl_json"] = self._memory_qdl_json(
            str(content_json.get("memory_type") or "decision"),
            str(content_json.get("title") or item.content_summary or ""),
            str(content_json.get("content") or item.content_summary or ""),
            content_json,
        )
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
            superseded_content = {
                **original_content_json,
                "superseded_by": str(updated.memory_id),
                "superseded_at": datetime.utcnow().isoformat(),
                "superseded_by_user": self._user_id,
                "governance_status": "superseded",
                "discussion_relations": self._merge_discussion_relations(
                    list(original_content_json.get("discussion_relations") or []),
                    [str(updated.memory_id)],
                    relation_type="revise",
                    status="confirmed",
                    created_by=self._user_id,
                    note="该版本已由新版本替代",
                ),
            }
            superseded_content["qdl_json"] = self._memory_qdl_json(
                str(superseded_content.get("memory_type") or "decision"),
                str(superseded_content.get("title") or item.content_summary or ""),
                str(superseded_content.get("content") or item.content_summary or ""),
                superseded_content,
            )
            await self._update_memory_item_compat(
                org_id=self._org_id,
                memory_id=memory_id,
                status="superseded",
                review_status="superseded",
                readiness_status="blocked",
                readiness_blockers=["review_status_superseded"],
                content_json=superseded_content,
            )
        else:
            updated = await self._update_memory_item_compat(
                org_id=self._org_id,
                memory_id=memory_id,
                status="confirmed",
                review_status="approved",
                readiness_status="ready",
                readiness_blockers=[],
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
                binding_kind="home",
                binding_status="active",
                approved_by=self._user_id,
                approved_at=datetime.utcnow(),
            )
        confirmed_memory_id = str(getattr(updated, "memory_id", memory_id))
        human_independence_key = hashlib.sha256(
            f"human_confirmation\x1f{self._user_id}".encode("utf-8")
        ).hexdigest()
        await self._repo.create_memory_evidence(
            MemoryEvidence(
                id=str(uuid7()),
                org_id=self._org_id,
                memory_id=confirmed_memory_id,
                evidence_role="human_confirmation",
                source_kind="human_review",
                source_type="user",
                source_id=self._user_id,
                independence_key=human_independence_key,
                trace_id=str(getattr(updated, "trace_id", "") or getattr(item, "trace_id", "") or "") or None,
                evidence_pointer={"scope_type": target_scope_type, "scope_id": target_scope_id},
                confidence=1.0,
                weight=1.0,
                occurred_at=datetime.utcnow(),
            )
        )
        if updated is not None:
            updated.review_status = "approved"
            updated.human_approved = True
            updated.human_confirmation_count = max(
                int(getattr(updated, "human_confirmation_count", 0) or 0),
                1,
            )
            updated.support_count = max(
                int(getattr(updated, "support_count", 0) or 0),
                int(getattr(updated, "origin_evidence_count", 0) or 0) + updated.human_confirmation_count,
            )
            updated.readiness_status = "ready"
            updated.readiness_blockers = []
            updated.last_evidence_at = datetime.utcnow()
            updated.last_supported_at = updated.last_evidence_at
        await self._enqueue_confirmed_memory_sync(updated or item)
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
        content_json["governance_status"] = "rejected"
        if reject_reason:
            content_json["reject_reason"] = reject_reason[:1000]
        content_json["qdl_json"] = self._memory_qdl_json(
            str(content_json.get("memory_type") or "decision"),
            str(content_json.get("title") or item.content_summary or ""),
            str(content_json.get("content") or item.content_summary or ""),
            content_json,
        )
        updated = await self._update_memory_item_compat(
            org_id=self._org_id,
            memory_id=memory_id,
            status="rejected",
            review_status="rejected",
            readiness_status="blocked",
            readiness_blockers=["review_status_rejected"],
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
        await self._publish_system_message(
            room_id,
            f"一条待确认知识已被拒绝，理由：{reject_reason[:120]}" if reject_reason else "一条待确认知识已被拒绝。",
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
        content_json["governance_status"] = "disputed"
        if request.conflicting_memory_id:
            content_json["discussion_relations"] = self._merge_discussion_relations(
                list(content_json.get("discussion_relations") or []),
                [request.conflicting_memory_id],
                relation_type="oppose",
                status="disputed",
                created_by=self._user_id,
                note=request.reason.strip(),
            )
        content_json["qdl_json"] = self._memory_qdl_json(
            str(content_json.get("memory_type") or "decision"),
            str(content_json.get("title") or item.content_summary or ""),
            str(content_json.get("content") or item.content_summary or ""),
            content_json,
        )
        updated = await self._update_memory_item_compat(
            org_id=self._org_id,
            memory_id=memory_id,
            status="disputed",
            review_status="disputed",
            readiness_status="blocked",
            readiness_blockers=["unresolved_conflict"],
            content_json=content_json,
        )
        conflict_key = hashlib.sha256(
            f"conflict\x1f{self._user_id}\x1f{request.reason.strip()}\x1f{request.conflicting_memory_id or ''}".encode("utf-8")
        ).hexdigest()
        await self._repo.create_memory_evidence(
            MemoryEvidence(
                id=str(uuid7()),
                org_id=self._org_id,
                memory_id=memory_id,
                evidence_role="conflict",
                source_kind="human_review",
                source_type="user",
                source_id=self._user_id,
                independence_key=conflict_key,
                evidence_pointer={
                    "reason": request.reason.strip(),
                    "conflicting_memory_id": request.conflicting_memory_id,
                },
                confidence=1.0,
                weight=1.0,
                occurred_at=datetime.utcnow(),
            )
        )
        if updated is not None:
            updated.conflict_count = int(getattr(updated, "conflict_count", 0) or 0) + 1
            updated.last_evidence_at = datetime.utcnow()
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
        result = await self.create_memory_share_request(
            memory_id,
            MeetingMemoryShareCreateRequest(
                target_scope_type=request.to_scope_type,
                target_scope_id=request.to_scope_id,
                share_reason=request.transfer_reason,
                idempotency_key=request.idempotency_key or f"legacy-transfer:{uuid.uuid4().hex}",
            ),
        )
        return result.memory

    async def create_memory_share_request(
        self,
        memory_id: str,
        request: MeetingMemoryShareCreateRequest,
    ) -> MeetingMemoryShareCreateResponse:
        lookup_by_key = getattr(self._repo, "get_memory_transfer_log_by_idempotency_key", None)
        existing = None
        if lookup_by_key is not None:
            existing = await lookup_by_key(
                org_id=self._org_id,
                idempotency_key=request.idempotency_key,
            )
        if existing is not None:
            existing_item = await self._repo.get_memory_item(self._org_id, str(existing.memory_id))
            if existing_item is None:
                raise NotFoundError("meeting memory not found")
            existing_plan = getattr(existing, "mapping_plan_json", None)
            if isinstance(existing_plan, dict) and existing_plan.get("target_memory_id"):
                await self._materialize_tunnel_projection(
                    source_item=existing_item,
                    transfer_log=existing,
                    mapping_plan=existing_plan,
                    source_qdl=existing_plan.get("source_qdl") or dict(getattr(existing_item, "content_json", None) or {}).get("qdl_json") or {},
                )
            existing_room_id = self._memory_room_id(existing_item) or str(existing.from_scope_id or "")
            return MeetingMemoryShareCreateResponse(
                memory=self._serialize_memory_item(existing_item, room_id=existing_room_id),
                share_request=await self._serialize_memory_share_approval(existing),
            )

        item = await self._repo.get_memory_item(self._org_id, memory_id)
        if item is None:
            raise NotFoundError("meeting memory not found")
        room_id = self._memory_room_id(item)
        if not room_id:
            raise ForbiddenError("memory is not sourced from a meeting room")
        await self._ensure_host(room_id)

        revision_requested = any(
            value is not None
            for value in (
                request.title,
                request.content,
                request.affected_objects,
                request.related_memory_ids,
            )
        )
        current_status = str(getattr(item, "status", "") or "")
        if current_status == "candidate" or revision_requested:
            confirmed = await self.confirm_memory(
                memory_id,
                MeetingMemoryUpdateRequest(
                    title=request.title,
                    content=request.content,
                    scope=_MEMORY_SCOPE_MEETING_ROOM,
                    scope_id=room_id,
                    publish_reason=request.share_reason,
                    affected_objects=request.affected_objects,
                    related_memory_ids=request.related_memory_ids,
                ),
            )
            memory_id = confirmed.memory_id
            item = await self._repo.get_memory_item(self._org_id, memory_id)
            if item is None:
                raise NotFoundError("confirmed meeting memory not found")
            room_id = self._memory_room_id(item) or room_id
            current_status = str(getattr(item, "status", "") or "")
        if current_status not in {"confirmed", "active"}:
            raise ValidationError("memory must be confirmed in its current scope before it can be shared")

        target_scope_type, target_scope_id = self._resolve_memory_publish_scope(
            room_id=room_id,
            scope=request.target_scope_type,
            scope_id=request.target_scope_id,
        )
        if target_scope_type == _MEMORY_SCOPE_MEETING_ROOM and target_scope_id == room_id:
            raise ValidationError("current meeting room memory is confirmed directly and does not need a share request")
        await self._ensure_memory_publish_allowed(item, target_scope_type, target_scope_id, dict(item.content_json or {}), transfer=True)
        # Build the cross-scope projection before creating the approval record.
        # Older memories may not have QDL persisted yet, so derive a deterministic
        # document from their governed content instead of bypassing the tunnel.
        content_json = dict(item.content_json or {})
        source_qdl = content_json.get("qdl_json")
        if parse_qdl(source_qdl).document is None:
            source_qdl = self._memory_qdl_json(
                str(content_json.get("memory_type") or getattr(item, "memory_type", "decision") or "decision"),
                str(content_json.get("title") or getattr(item, "content_summary", "") or memory_id),
                str(content_json.get("content") or getattr(item, "content_summary", "") or ""),
                content_json,
            )
        tunnel_result = KnowledgeTunnelService.transform_qdl(
            source_qdl,
            source_scope_type=_MEMORY_SCOPE_MEETING_ROOM,
            source_scope_id=room_id,
            target_scope_type=target_scope_type,
            target_scope_id=target_scope_id,
            mapping_rules=request.mapping_rules,
            mapping_version=request.mapping_version,
            interpolation_strategy=request.interpolation_strategy,
            transform_reason=request.share_reason or "会议记忆跨域共享",
            source_memory_id=memory_id,
        )
        if tunnel_result.status == "rejected":
            detail = "; ".join(tunnel_result.errors) or "knowledge tunnel rejected the projection"
            raise ValidationError(f"knowledge tunnel conversion failed: {detail}")
        mapping_plan = tunnel_result.as_dict()
        requires_approval = await self._memory_transfer_requires_approval(
            item,
            source_room_id=room_id,
            target_scope_type=target_scope_type,
            target_scope_id=target_scope_id,
        )
        # Every cross-scope QDL projection is a target-domain candidate. Legacy
        # direct-binding rules must still leave an approval/audit trail.
        if tunnel_result.source_scope != tunnel_result.target_scope:
            requires_approval = True
        transfer_status = "pending_approval" if requires_approval else "approved"

        create_kwargs = {
            "org_id": self._org_id,
            "memory_id": memory_id,
            "from_scope_type": _MEMORY_SCOPE_MEETING_ROOM,
            "from_scope_id": room_id,
            "to_scope_type": target_scope_type,
            "to_scope_id": target_scope_id,
            "transfer_reason": request.share_reason,
            "status": transfer_status,
            "operator_id": self._user_id,
            "requested_by": self._user_id,
            "idempotency_key": request.idempotency_key,
            "mapping_plan_json": mapping_plan,
            "mapping_version": tunnel_result.mapping_version,
            "interpolation_strategy": tunnel_result.interpolation_strategy,
        }
        try:
            if hasattr(self._session, "begin_nested"):
                async with self._session.begin_nested():
                    transfer_log = await self._repo.create_memory_transfer_log(**create_kwargs)
            else:
                transfer_log = await self._repo.create_memory_transfer_log(**create_kwargs)
        except IntegrityError:
            if lookup_by_key is None:
                raise
            transfer_log = await lookup_by_key(
                org_id=self._org_id,
                idempotency_key=request.idempotency_key,
            )
            if transfer_log is None:
                raise

        # A cross-scope transfer has its own target-domain identity.  Keep the
        # id in the deterministic mapping plan so retries, approval and later
        # revocation can all resolve the same projection without a new column.
        target_memory_id = self._tunnel_projection_memory_id(
            source_memory_id=memory_id,
            transfer_id=str(transfer_log.id),
            target_scope_type=target_scope_type,
            target_scope_id=target_scope_id,
            mapping_version=tunnel_result.mapping_version,
        )
        mapping_plan = {
            **mapping_plan,
            "target_memory_id": target_memory_id,
            "source_memory_id": str(memory_id),
            "transfer_id": str(transfer_log.id),
            "source_qdl": source_qdl,
        }
        transfer_log.mapping_plan_json = mapping_plan
        if callable(getattr(self._session, "flush", None)):
            await self._session.flush()

        await self._materialize_tunnel_projection(
            source_item=item,
            transfer_log=transfer_log,
            mapping_plan=mapping_plan,
            source_qdl=source_qdl,
        )

        content_json["share_reason"] = request.share_reason
        tunnel_plans = dict(content_json.get("knowledge_tunnel_plans") or {})
        tunnel_plans[str(transfer_log.id)] = mapping_plan
        content_json["knowledge_tunnel_plans"] = tunnel_plans
        content_json["shareability"] = self._shareability_with_target(
            content_json.get("shareability"),
            target_scope_type,
            target_scope_id,
            requires_approval=requires_approval,
            approval_role=(self._approval_role_for_scope(target_scope_type) if requires_approval else "none"),
        )
        if requires_approval:
            content_json["target_scope_type"] = target_scope_type
            content_json["target_scope_id"] = target_scope_id
            content_json["published_scope"] = str(content_json.get("published_scope") or self._memory_current_scope(item) or _MEMORY_SCOPE_MEETING_ROOM)
            content_json["pending_transfer_id"] = str(transfer_log.id)
            pending_requests = [
                dict(entry)
                for entry in list(content_json.get("pending_share_requests") or [])
                if isinstance(entry, dict) and str(entry.get("id") or "") != str(transfer_log.id)
            ]
            pending_requests.append(
                {
                    "id": str(transfer_log.id),
                    "target_scope_type": target_scope_type,
                    "target_scope_id": target_scope_id,
                    "status": "pending_approval",
                    "requested_by": self._user_id,
                    "share_reason": request.share_reason,
                    "mapping_version": tunnel_result.mapping_version,
                    "interpolation_strategy": tunnel_result.interpolation_strategy,
                    "mapping_status": tunnel_result.status,
                    "unmapped_fields": list(tunnel_result.unmapped_fields),
                }
            )
            content_json["pending_share_requests"] = pending_requests
            updated = await self._repo.update_memory_item(
                org_id=self._org_id,
                memory_id=memory_id,
                content_json=content_json,
            )
            if room_id:
                await self._publish_system_message(room_id, "记忆共享请求已提交，等待目标范围确认。")
        else:
            await self._repo.create_memory_scope_binding(
                org_id=self._org_id,
                memory_id=memory_id,
                scope_type=target_scope_type,
                scope_id=target_scope_id,
                permission="read",
                created_by=self._user_id,
                binding_kind="shared",
                binding_status="active",
                approved_by=self._user_id,
                approved_at=datetime.utcnow(),
                source_transfer_id=str(transfer_log.id),
            )
            shared_scopes = [
                dict(entry)
                for entry in list(content_json.get("shared_scopes") or [])
                if isinstance(entry, dict)
            ]
            target_key = (target_scope_type, target_scope_id)
            if not any(
                (str(entry.get("scope_type") or ""), str(entry.get("scope_id") or "")) == target_key
                for entry in shared_scopes
            ):
                shared_scopes.append(
                    {
                        "scope_type": target_scope_type,
                        "scope_id": target_scope_id,
                        "transfer_id": str(transfer_log.id),
                    }
                )
            content_json["shared_scopes"] = shared_scopes
            updated = await self._repo.update_memory_item(
                org_id=self._org_id,
                memory_id=memory_id,
                content_json=content_json,
            )

        await self._publish_memory_share_work_item_event(transfer_log, "work_item_created")
        return MeetingMemoryShareCreateResponse(
            memory=self._serialize_memory_item(updated or item, room_id=room_id),
            share_request=await self._serialize_memory_share_approval(transfer_log),
        )

    @staticmethod
    def _tunnel_projection_memory_id(
        *,
        source_memory_id: str,
        transfer_id: str,
        target_scope_type: str,
        target_scope_id: str,
        mapping_version: str,
    ) -> str:
        """Return a stable target identity for one Cs -> Ct transfer."""
        raw = "|".join(
            [
                str(source_memory_id),
                str(transfer_id),
                str(target_scope_type),
                str(target_scope_id),
                str(mapping_version),
            ]
        )
        return f"mem_tunnel_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:32]}"

    async def _materialize_tunnel_projection(
        self,
        *,
        source_item: MemoryItem,
        transfer_log: Any,
        mapping_plan: dict[str, Any],
        source_qdl: dict[str, Any],
    ) -> MemoryItem | None:
        """Persist the target-domain K' candidate and its provenance edge.

        The meeting test fakes intentionally expose only the legacy transfer
        methods.  In that case this helper records no side effects and the
        original share behavior remains testable; the production repository
        exposes ``create_memory_item`` and receives the complete projection.
        """
        create_item = getattr(self._repo, "create_memory_item", None)
        if not callable(create_item):
            return None
        target_memory_id = str(mapping_plan.get("target_memory_id") or "")
        transformed_qdl = mapping_plan.get("transformed_qdl")
        if not target_memory_id or not isinstance(transformed_qdl, dict):
            return None
        existing = await self._repo.get_memory_item(self._org_id, target_memory_id)
        if existing is not None:
            return existing

        source_content = dict(getattr(source_item, "content_json", None) or {})
        source_scope = dict(mapping_plan.get("source_scope") or {})
        target_scope = dict(mapping_plan.get("target_scope") or {})
        claim = transformed_qdl.get("claim") if isinstance(transformed_qdl.get("claim"), dict) else {}
        title = str(claim.get("title") or source_content.get("title") or "会议记忆")[:200]
        summary = str(claim.get("text") or source_item.content_summary or source_content.get("content") or "")[:1000]
        projection_trace = f"knowledge-tunnel:{transfer_log.id}:{target_memory_id}"
        projection_content = {
            **source_content,
            "title": title,
            "content": str(claim.get("text") or source_content.get("content") or source_item.content_summary or ""),
            "qdl_json": transformed_qdl,
            "source_qdl": source_qdl,
            "source_type": "knowledge_tunnel",
            "source_id": str(transfer_log.id),
            "source_memory_id": str(source_item.memory_id),
            "transfer_id": str(transfer_log.id),
            "source_scope": source_scope,
            "target_scope": target_scope,
            "mapping_version": str(mapping_plan.get("mapping_version") or ""),
            "interpolation_strategy": str(mapping_plan.get("interpolation_strategy") or ""),
            "source_qdl_hash": str((transformed_qdl.get("provenance") or {}).get("source_hash") or "")
            if isinstance(transformed_qdl.get("provenance"), dict)
            else "",
            "projection_status": "candidate",
        }
        source_scope_id = str(source_scope.get("scope_id") or getattr(source_item, "memory_id", ""))
        target_scope_type = str(target_scope.get("scope_type") or getattr(transfer_log, "to_scope_type", ""))
        target_scope_id = str(target_scope.get("scope_id") or getattr(transfer_log, "to_scope_id", ""))
        source_room_id = str(getattr(transfer_log, "from_scope_id", "") or source_scope_id)
        source_trace = str(getattr(source_item, "trace_id", None) or getattr(source_item, "source_trace_id", None) or projection_trace)
        projection = MemoryItem(
            id=str(uuid7()),
            memory_id=target_memory_id,
            org_id=self._org_id,
            user_id=getattr(source_item, "user_id", None),
            memory_type=str(getattr(source_item, "memory_type", "decision") or "decision"),
            scope_json=self._memory_scope_json(target_scope_type, target_scope_id, source_room_id=source_room_id),
            applicability_json=dict(transformed_qdl.get("applicability") or getattr(source_item, "applicability_json", None) or {}),
            content_summary=summary,
            content_json=projection_content,
            source_event_ids=getattr(source_item, "source_event_ids", None),
            evidence_pointers={
                **dict(getattr(source_item, "evidence_pointers", None) or {}),
                "source_memory_id": str(source_item.memory_id),
                "transfer_id": str(transfer_log.id),
                "source_scope": source_scope,
                "target_scope": target_scope,
                "mapping_version": mapping_plan.get("mapping_version"),
                "interpolation_strategy": mapping_plan.get("interpolation_strategy"),
                "source_qdl": source_qdl,
            },
            version_parent_id=None,
            idempotency_key=f"knowledge-tunnel:{transfer_log.id}",
            source_trace_id=source_trace,
            source_message_id=getattr(source_item, "source_message_id", None),
            source_task_id=getattr(source_item, "source_task_id", None),
            task_id=getattr(source_item, "task_id", None),
            product_line=getattr(source_item, "product_line", None),
            rag_space_id=getattr(source_item, "rag_space_id", None),
            standard_code=getattr(source_item, "standard_code", None),
            standard_version=getattr(source_item, "standard_version", None),
            target_market=getattr(source_item, "target_market", None),
            product_category=getattr(source_item, "product_category", None),
            index_status="pending",
            vector_status="pending",
            graph_status="pending",
            policy_key=getattr(source_item, "policy_key", None),
            policy_version=getattr(source_item, "policy_version", None),
            candidate_key=f"tunnel:{source_item.memory_id}:{target_scope_type}:{target_scope_id}:{mapping_plan.get('mapping_version') or 'manual-v1'}",
            canonical_claim=dict(claim),
            origin_evidence_count=1,
            independent_support_count=0,
            support_count=1,
            trust_score=float(getattr(source_item, "trust_score", 0.65) or 0.65),
            confidence=float(getattr(source_item, "confidence", 0.65) or 0.65),
            visibility_scope=target_scope,
            usage_policy=str(getattr(source_item, "usage_policy", "context_only") or "context_only"),
            ttl_policy=str(getattr(source_item, "ttl_policy", "never") or "never"),
            privacy_level=str(getattr(source_item, "privacy_level", "tenant_private") or "tenant_private"),
            review_status="candidate",
            governance_target_scope_type=target_scope_type,
            governance_target_scope_id=target_scope_id,
            readiness_status="collecting",
            readiness_blockers=["target_scope_approval_required"],
            migration_review_required=False,
            migration_review_reason=None,
            status="candidate",
            created_by=getattr(source_item, "created_by", None) or self._user_id,
            created_by_type="knowledge_tunnel",
            trace_id=projection_trace,
            expires_at=getattr(source_item, "expires_at", None),
        )
        await create_item(projection)
        create_binding = getattr(self._repo, "create_memory_scope_binding", None)
        if callable(create_binding):
            await create_binding(
                org_id=self._org_id,
                memory_id=target_memory_id,
                scope_type=target_scope_type,
                scope_id=target_scope_id,
                permission="read",
                created_by=self._user_id,
                binding_kind="shared",
                binding_status="pending",
                source_transfer_id=str(transfer_log.id),
            )
        create_origin = getattr(self._repo, "create_memory_origin", None)
        create_evidence = getattr(self._repo, "create_memory_evidence", None)
        dedupe_key = hashlib.sha256(
            f"knowledge_tunnel\x1f{source_item.memory_id}\x1f{transfer_log.id}".encode("utf-8")
        ).hexdigest()
        if callable(create_origin):
            origin = await create_origin(
                MemoryOrigin(
                    id=str(uuid7()),
                    org_id=self._org_id,
                    memory_id=target_memory_id,
                    origin_kind="knowledge_tunnel",
                    source_type="memory_transfer",
                    source_id=str(transfer_log.id),
                    trace_id=projection_trace,
                    dedupe_key=dedupe_key,
                    source_span=None,
                    metadata_json={
                        "source_memory_id": str(source_item.memory_id),
                        "source_scope": source_scope,
                        "target_scope": target_scope,
                        "mapping_version": mapping_plan.get("mapping_version"),
                        "interpolation_strategy": mapping_plan.get("interpolation_strategy"),
                    },
                    occurred_at=datetime.utcnow(),
                )
            )
            if callable(create_evidence):
                await create_evidence(
                    MemoryEvidence(
                        id=str(uuid7()),
                        org_id=self._org_id,
                        memory_id=target_memory_id,
                        evidence_role="origin",
                        source_kind="knowledge_tunnel",
                        source_type="memory_transfer",
                        source_id=str(transfer_log.id),
                        independence_key=dedupe_key,
                        trace_id=projection_trace,
                        evidence_pointer={
                            "origin_id": str(origin.id),
                            "source_memory_id": str(source_item.memory_id),
                            "transfer_id": str(transfer_log.id),
                            "mapping_plan": mapping_plan,
                        },
                        confidence=projection.confidence,
                        weight=1.0,
                        occurred_at=datetime.utcnow(),
                    )
                )
        await self._enqueue_tunnel_projection_sync(
            projection,
            binding_status="pending",
            edge_status="candidate",
            source_memory_id=str(source_item.memory_id),
            transfer_id=str(transfer_log.id),
        )
        return projection

    async def _enqueue_tunnel_projection_sync(
        self,
        item: MemoryItem,
        *,
        binding_status: str,
        edge_status: str,
        source_memory_id: str,
        transfer_id: str,
    ) -> None:
        """Queue target projection index/node/edge updates when outbox is available."""
        if not callable(getattr(self._session, "execute", None)):
            return
        list_bindings = getattr(self._repo, "list_memory_scope_bindings", None)
        bindings = []
        if callable(list_bindings):
            bindings = await list_bindings(org_id=self._org_id, memory_ids=[str(item.memory_id)])
        active_bindings = [row for row in bindings if str(getattr(row, "binding_status", "")) == "active"]
        outbox = MemorySyncOutboxRepository(self._session, self._org_id)
        common_payload = {
            "memory_id": str(item.memory_id),
            "org_id": self._org_id,
            "user_id": str(getattr(item, "user_id", None) or ""),
            "memory_type": str(getattr(item, "memory_type", "") or ""),
            "summary": str(getattr(item, "content_summary", "") or ""),
            "trust_score": float(getattr(item, "trust_score", 0) or 0),
            "confidence": float(getattr(item, "confidence", 0) or 0),
            "expires_at": item.expires_at.isoformat() if getattr(item, "expires_at", None) else "",
            "product_line": str(getattr(item, "product_line", None) or ""),
            "rag_space_id": str(getattr(item, "rag_space_id", None) or ""),
            "task_id": str(getattr(item, "task_id", None) or getattr(item, "source_task_id", None) or ""),
            "extra_payload": {
                "review_status": str(getattr(item, "review_status", "candidate") or "candidate"),
                "scope_bindings": [
                    {
                        "scope_type": str(row.scope_type),
                        "scope_id": str(row.scope_id),
                        "binding_kind": str(getattr(row, "binding_kind", "shared")),
                        "binding_status": str(getattr(row, "binding_status", binding_status)),
                    }
                    for row in bindings
                ],
                "applicability": dict(getattr(item, "applicability_json", None) or {}),
                "source_memory_id": source_memory_id,
                "transfer_id": transfer_id,
                "projection": True,
            },
        }
        is_active = edge_status == "active"
        candidate_payload = {
            "collection": MEMORY_COLLECTION if is_active else CANDIDATE_MEMORY_COLLECTION,
            "status": "active" if is_active else "candidate",
            **common_payload,
        }
        await outbox.create_pending(
            memory_id=str(item.memory_id),
            action="UPSERT_ACTIVE_VECTOR" if is_active else "UPSERT_CANDIDATE_VECTOR",
            target_backend="qdrant",
            payload=candidate_payload,
            trace_id=str(getattr(item, "trace_id", "") or "") or None,
        )
        node_payload = {
            "memory_id": str(item.memory_id),
            "org_id": self._org_id,
            "memory_type": str(getattr(item, "memory_type", "") or ""),
            "status": edge_status,
            "trust_score": float(getattr(item, "trust_score", 0) or 0),
            "confidence": float(getattr(item, "confidence", 0) or 0),
            "scope_key": "|".join(f"{row.scope_type}:{row.scope_id}" for row in active_bindings),
            "review_status": str(getattr(item, "review_status", "candidate") or "candidate"),
            "origin_kind": "knowledge_tunnel",
            "scope_bindings_json": json.dumps(common_payload["extra_payload"]["scope_bindings"], ensure_ascii=False),
            "applicability_json": json.dumps(dict(getattr(item, "applicability_json", None) or {}), ensure_ascii=False),
            "sync_version": 2,
        }
        await outbox.create_pending(
            memory_id=str(item.memory_id),
            action="UPSERT_MEMORY_NODE",
            target_backend="neo4j",
            payload=node_payload,
            trace_id=str(getattr(item, "trace_id", "") or "") or None,
        )
        await outbox.create_pending(
            memory_id=str(item.memory_id),
            action="UPSERT_MEMORY_EDGE",
            target_backend="neo4j",
            payload={
                "org_id": self._org_id,
                "source_memory_id": str(item.memory_id),
                "target_memory_id": source_memory_id,
                "edge_type": "derived_from",
                "strength": 1.0,
                "trace_id": str(getattr(item, "trace_id", "") or "") or None,
                "reason": "Knowledge Tunnel cross-scope projection",
                "metadata_json": {
                    "transfer_id": transfer_id,
                    "edge_status": edge_status,
                    "binding_status": binding_status,
                },
            },
            trace_id=str(getattr(item, "trace_id", "") or "") or None,
        )

    async def _resolve_tunnel_projection(self, row: Any) -> MemoryItem | None:
        mapping = getattr(row, "mapping_plan_json", None)
        if not isinstance(mapping, dict):
            return None
        target_id = str(mapping.get("target_memory_id") or "")
        if not target_id:
            return None
        getter = getattr(self._repo, "get_memory_item", None)
        if not callable(getter):
            return None
        return await getter(self._org_id, target_id)

    async def _activate_tunnel_projection(self, row: Any) -> MemoryItem | None:
        projection = await self._resolve_tunnel_projection(row)
        if projection is None:
            return None
        content = dict(getattr(projection, "content_json", None) or {})
        content.update({"projection_status": "active", "approved_at": datetime.utcnow().isoformat(), "approved_by": self._user_id})
        update_item = getattr(self._repo, "update_memory_item", None)
        if callable(update_item):
            projection = await self._update_memory_item_compat(
                org_id=self._org_id,
                memory_id=str(projection.memory_id),
                status="active",
                review_status="approved",
                readiness_status="ready",
                readiness_blockers=[],
                content_json=content,
            ) or projection
        create_binding = getattr(self._repo, "create_memory_scope_binding", None)
        if callable(create_binding):
            await create_binding(
                org_id=self._org_id,
                memory_id=str(projection.memory_id),
                scope_type=str(row.to_scope_type),
                scope_id=str(row.to_scope_id),
                permission="read",
                created_by=self._user_id,
                binding_kind="shared",
                binding_status="active",
                approved_by=self._user_id,
                approved_at=datetime.utcnow(),
                source_transfer_id=str(row.id),
            )
        await self._enqueue_tunnel_projection_sync(
            projection,
            binding_status="active",
            edge_status="active",
            source_memory_id=str(row.memory_id),
            transfer_id=str(row.id),
        )
        if callable(getattr(self._session, "execute", None)):
            outbox = MemorySyncOutboxRepository(self._session, self._org_id)
            await outbox.create_pending(
                memory_id=str(projection.memory_id),
                action="DELETE_CANDIDATE_VECTOR",
                target_backend="qdrant",
                payload={"collection": CANDIDATE_MEMORY_COLLECTION, "memory_id": str(projection.memory_id), "trace_id": projection.trace_id},
                trace_id=projection.trace_id,
            )
        return projection

    async def _isolate_tunnel_projection(self, row: Any, *, status: str, reason: str | None = None) -> MemoryItem | None:
        projection = await self._resolve_tunnel_projection(row)
        if projection is None:
            return None
        content = dict(getattr(projection, "content_json", None) or {})
        content.update({"projection_status": status, "isolated_at": datetime.utcnow().isoformat(), "isolation_reason": reason})
        update_item = getattr(self._repo, "update_memory_item", None)
        if callable(update_item):
            projection = await self._update_memory_item_compat(
                org_id=self._org_id,
                memory_id=str(projection.memory_id),
                status=status,
                review_status="rejected" if status == "rejected" else "pending",
                readiness_status="blocked",
                readiness_blockers=[reason or f"projection_{status}"],
                content_json=content,
            ) or projection
        if callable(getattr(self._session, "execute", None)):
            outbox = MemorySyncOutboxRepository(self._session, self._org_id)
            await outbox.create_pending(
                memory_id=str(projection.memory_id),
                action="DELETE_CANDIDATE_VECTOR",
                target_backend="qdrant",
                payload={"collection": CANDIDATE_MEMORY_COLLECTION, "memory_id": str(projection.memory_id), "trace_id": projection.trace_id},
                trace_id=projection.trace_id,
            )
            await outbox.create_pending(
                memory_id=str(projection.memory_id),
                action="UPDATE_MEMORY_NODE_STATUS",
                target_backend="neo4j",
                payload={
                    "memory_id": str(projection.memory_id),
                    "org_id": self._org_id,
                    "memory_type": str(getattr(projection, "memory_type", "") or ""),
                    "status": status,
                    "trust_score": float(getattr(projection, "trust_score", 0) or 0),
                    "confidence": float(getattr(projection, "confidence", 0) or 0),
                    "scope_key": "",
                    "review_status": "rejected" if status == "rejected" else "pending",
                    "origin_kind": "knowledge_tunnel",
                    "scope_bindings_json": "[]",
                    "applicability_json": json.dumps(dict(getattr(projection, "applicability_json", None) or {}), ensure_ascii=False),
                    "sync_version": 2,
                },
                trace_id=projection.trace_id,
            )
        return projection

    async def share_memory(
        self,
        memory_id: str,
        request: MeetingMemoryShareRequest,
    ) -> MeetingMemoryResponse:
        result = await self.create_memory_share_request(
            memory_id,
            MeetingMemoryShareCreateRequest(
                target_scope_type=request.target_scope_type,
                target_scope_id=request.target_scope_id,
                share_reason=request.share_reason,
                idempotency_key=request.idempotency_key or f"legacy-share:{uuid.uuid4().hex}",
            ),
        )
        return result.memory

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

    async def approve_memory_share(
        self,
        transfer_id: str,
        request: MeetingMemoryShareDecisionRequest | None = None,
    ) -> MeetingMemoryResponse:
        row = await self._repo.get_memory_transfer_log(self._org_id, transfer_id)
        if row is None:
            raise NotFoundError("memory share request not found")
        if str(row.status) != "pending_approval":
            raise ConflictError("memory share request has already been handled")
        await self._ensure_memory_share_approver(row)
        item = await self._repo.get_memory_item(self._org_id, str(row.memory_id))
        if item is None:
            raise NotFoundError("meeting memory not found")
        mapping_plan = getattr(row, "mapping_plan_json", None)
        if isinstance(mapping_plan, dict) and str(mapping_plan.get("status") or "") == "needs_review":
            unmapped = ", ".join(str(value) for value in list(mapping_plan.get("unmapped_fields") or [])[:8])
            suffix = f": {unmapped}" if unmapped else ""
            raise ValidationError(f"knowledge tunnel mapping requires review{suffix}")
        try:
            claimed = await self._repo.update_memory_transfer_log_status(
                org_id=self._org_id,
                transfer_id=transfer_id,
                status="approved",
                operator_id=self._user_id,
                decision_note=(request.decision_note if request else None),
                expected_status="pending_approval",
            )
            if claimed is None:
                raise ConflictError("memory share request was handled by another approver")
            await self._repo.create_memory_scope_binding(
                org_id=self._org_id,
                memory_id=str(row.memory_id),
                scope_type=str(row.to_scope_type),
                scope_id=str(row.to_scope_id),
                permission="read",
                created_by=self._user_id,
                binding_kind="shared",
                binding_status="active",
                approved_by=self._user_id,
                approved_at=datetime.utcnow(),
                source_transfer_id=transfer_id,
            )
            content_json = dict(item.content_json or {})
            content_json["target_scope_type"] = str(row.to_scope_type)
            content_json["target_scope_id"] = str(row.to_scope_id)
            content_json["share_reason"] = row.transfer_reason
            pending_requests = [
                dict(entry)
                for entry in list(content_json.get("pending_share_requests") or [])
                if isinstance(entry, dict) and str(entry.get("id") or "") != transfer_id
            ]
            content_json["pending_share_requests"] = pending_requests
            content_json["pending_transfer_id"] = (
                str(pending_requests[-1].get("id") or "") or None
                if pending_requests
                else None
            )
            content_json["approved_transfer_id"] = str(row.id)
            content_json["approved_mapping_version"] = getattr(row, "mapping_version", None)
            content_json["approved_interpolation_strategy"] = getattr(row, "interpolation_strategy", None)
            shared_scopes = [
                dict(entry)
                for entry in list(content_json.get("shared_scopes") or [])
                if isinstance(entry, dict)
            ]
            target_key = (str(row.to_scope_type), str(row.to_scope_id))
            if not any(
                (str(entry.get("scope_type") or ""), str(entry.get("scope_id") or "")) == target_key
                for entry in shared_scopes
            ):
                shared_scopes.append(
                    {
                        "scope_type": str(row.to_scope_type),
                        "scope_id": str(row.to_scope_id),
                        "transfer_id": transfer_id,
                    }
                )
            content_json["shared_scopes"] = shared_scopes
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
            )
            # Activate the independent target-domain projection only after the
            # transfer claim is atomically approved.  The source memory keeps
            # its original room scope and remains the canonical origin.
            await self._activate_tunnel_projection(row)
            if str(row.to_scope_type) == _MEMORY_SCOPE_ORG_SPACE:
                trace_id = f"memory-org-approve:{transfer_id}"
                await MemoryService(self._session, self._org_id).approve_organization_memory(
                    str(row.memory_id),
                    reviewer_id=self._user_id,
                    transfer_id=transfer_id,
                    trace_id=trace_id,
                )
                updated = await self._repo.get_memory_item(self._org_id, str(row.memory_id)) or updated
            if str(row.from_scope_type) == _MEMORY_SCOPE_MEETING_ROOM:
                await self._publish_system_message(str(row.from_scope_id), "一条记忆共享请求已通过审批并生效。")
            await self._publish_memory_share_work_item_event(claimed, "work_item_completed")
            return self._serialize_memory_item(updated or item, room_id=str(row.from_scope_id or ""))
        except Exception:
            logger.exception("approve_memory_share failed for transfer_id=%s", transfer_id)
            raise

    async def reject_memory_share(
        self,
        transfer_id: str,
        request: MeetingMemoryShareRejectRequest,
    ) -> MeetingMemoryShareApprovalResponse:
        row = await self._repo.get_memory_transfer_log(self._org_id, transfer_id)
        if row is None:
            raise NotFoundError("memory share request not found")
        if str(row.status) != "pending_approval":
            raise ConflictError("memory share request has already been handled")
        await self._ensure_memory_share_approver(row)
        updated = await self._repo.update_memory_transfer_log_status(
            org_id=self._org_id,
            transfer_id=transfer_id,
            status="rejected",
            operator_id=self._user_id,
            decision_note=request.decision_note,
            expected_status="pending_approval",
        )
        if updated is None:
            raise ConflictError("memory share request was handled by another approver")
        item = await self._repo.get_memory_item(self._org_id, str(row.memory_id))
        if item is not None:
            content_json = dict(item.content_json or {})
            pending_requests = [
                dict(entry)
                for entry in list(content_json.get("pending_share_requests") or [])
                if isinstance(entry, dict) and str(entry.get("id") or "") != transfer_id
            ]
            content_json["pending_share_requests"] = pending_requests
            content_json["pending_transfer_id"] = (
                str(pending_requests[-1].get("id") or "") or None
                if pending_requests
                else None
            )
            content_json["last_rejected_transfer_id"] = transfer_id
            content_json["last_rejected_transfer_at"] = datetime.utcnow().isoformat()
            content_json["last_rejected_transfer_note"] = request.decision_note
            await self._repo.update_memory_item(
                org_id=self._org_id,
                memory_id=str(row.memory_id),
                content_json=content_json,
            )
        await self._isolate_tunnel_projection(
            row,
            status="rejected",
            reason=request.decision_note or "target scope rejected the transfer",
        )
        if str(row.from_scope_type) == _MEMORY_SCOPE_MEETING_ROOM:
            await self._publish_system_message(str(row.from_scope_id), "一条记忆共享请求已被拒绝。")
        await self._publish_memory_share_work_item_event(updated, "work_item_completed")
        return await self._serialize_memory_share_approval(updated or row)

    async def cancel_memory_share(self, transfer_id: str) -> MeetingMemoryShareApprovalResponse:
        row = await self._repo.get_memory_transfer_log(self._org_id, transfer_id)
        if row is None:
            raise NotFoundError("memory share request not found")
        if str(row.status) != "pending_approval":
            raise ConflictError("memory share request has already been handled")
        requested_by = str(getattr(row, "requested_by", None) or getattr(row, "operator_id", None) or "")
        if requested_by != self._user_id:
            raise ForbiddenError("only the requester can cancel this memory share")
        updated = await self._repo.update_memory_transfer_log_status(
            org_id=self._org_id,
            transfer_id=transfer_id,
            status="cancelled",
            operator_id=self._user_id,
            decision_note="发起人撤销",
            expected_status="pending_approval",
        )
        if updated is None:
            raise ConflictError("memory share request was handled by another approver")
        item = await self._repo.get_memory_item(self._org_id, str(row.memory_id))
        if item is not None:
            content_json = dict(item.content_json or {})
            pending_requests = [
                dict(entry)
                for entry in list(content_json.get("pending_share_requests") or [])
                if isinstance(entry, dict) and str(entry.get("id") or "") != transfer_id
            ]
            content_json["pending_share_requests"] = pending_requests
            content_json["pending_transfer_id"] = (
                str(pending_requests[-1].get("id") or "") or None
                if pending_requests
                else None
            )
            await self._repo.update_memory_item(
                org_id=self._org_id,
                memory_id=str(row.memory_id),
                content_json=content_json,
            )
        await self._isolate_tunnel_projection(
            row,
            status="isolated",
            reason="发起人撤销跨域共享",
        )
        if str(row.from_scope_type) == _MEMORY_SCOPE_MEETING_ROOM:
            await self._publish_system_message(str(row.from_scope_id), "一条记忆共享请求已由发起人撤销。")
        await self._publish_memory_share_work_item_event(updated, "work_item_completed")
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

    async def _list_private_agent_context_messages(
        self,
        *,
        room_id: str,
        limit: int = 80,
    ) -> list[Any]:
        list_context = getattr(self._repo, "list_private_agent_context_messages", None)
        if callable(list_context):
            return await list_context(
                org_id=self._org_id,
                room_id=room_id,
                user_id=self._user_id,
                limit=limit,
            )
        messages = await self._list_recent_messages(room_id=room_id, limit=limit)
        result: list[Any] = []
        for message in messages:
            metadata = getattr(message, "metadata_json", None) or {}
            recipient = self._message_recipient_user_id(message)
            visibility = str(metadata.get("visibility") or ("private" if recipient else "room"))
            if visibility != "private" and not recipient:
                result.append(message)
                continue
            belongs_to_user = (
                str(getattr(message, "user_id", "") or "") == self._user_id
                or recipient == self._user_id
                or str(metadata.get("audience_scope_id") or "") == self._user_id
            )
            is_private_agent = (
                str(metadata.get("interaction_mode") or "") == _INTERACTION_PRIVATE_CHAT
                or bool(metadata.get("agent_sidecar_question"))
                or str(getattr(message, "agent_id", "") or "") == _MEETING_GENERAL_AGENT_ID
            )
            if belongs_to_user and is_private_agent:
                result.append(message)
        return result[-limit:]

    async def _context_summary_json(
        self,
        *,
        room_id: str,
        context_scope: str,
        user_key: str,
    ) -> dict[str, Any]:
        get_summary = getattr(self._repo, "get_context_summary", None)
        if not callable(get_summary):
            return {}
        row = await get_summary(
            org_id=self._org_id,
            room_id=room_id,
            context_scope=context_scope,
            user_key=user_key,
        )
        summary_json = getattr(row, "summary_json", None) if row is not None else None
        return dict(summary_json) if isinstance(summary_json, dict) else {}

    async def _refresh_private_context_summary(
        self,
        *,
        room_id: str,
        messages: list[Any] | None = None,
    ) -> None:
        upsert_summary = getattr(self._repo, "upsert_context_summary", None)
        if not callable(upsert_summary):
            return
        rows = messages or await self._list_private_agent_context_messages(room_id=room_id, limit=80)
        if not rows:
            return
        previous = await self._context_summary_json(
            room_id=room_id,
            context_scope="private",
            user_key=self._user_id,
        )
        await upsert_summary(
            org_id=self._org_id,
            room_id=room_id,
            context_scope="private",
            user_key=self._user_id,
            through_seq=max(int(getattr(row, "seq_no", 0) or 0) for row in rows),
            summary_json=self._build_rolling_summary(rows, previous),
        )

    async def _list_recent_public_messages(self, *, room_id: str, limit: int = 50) -> list[Any]:
        list_recent = getattr(self._repo, "list_recent_public_messages", None)
        if callable(list_recent):
            return await list_recent(org_id=self._org_id, room_id=room_id, limit=limit)
        list_public = getattr(self._repo, "list_public_messages", None)
        if callable(list_public):
            return await list_public(
                org_id=self._org_id,
                room_id=room_id,
                after_seq=None,
                limit=limit,
            )
        try:
            messages = await self._repo.list_recent_messages(
                org_id=self._org_id,
                room_id=room_id,
                limit=limit,
                visible_user_id=None,
            )
        except TypeError:
            messages = await self._repo.list_recent_messages(
                org_id=self._org_id,
                room_id=room_id,
                limit=limit,
            )
        except AttributeError:
            messages = list(getattr(self._repo, "messages", []) or [])[-limit:]
        return [
            message for message in messages
            if not self._message_recipient_user_id(message)
            and str((getattr(message, "metadata_json", None) or {}).get("visibility") or "room") != "private"
        ][-limit:]

    async def _invalidate_agent_replies_for_source(
        self,
        room_id: str,
        message_id: str,
        *,
        recalled: bool = False,
    ) -> None:
        workflow_run_id = _PUBLIC_AGENT_WORKFLOWS.get((room_id, message_id))
        if workflow_run_id:
            meeting_agent_cancel_registry.cancel(room_id, workflow_run_id)
        try:
            replies = await self._list_recent_public_messages(room_id=room_id, limit=200)
        except (AttributeError, TypeError):
            replies = []
        for reply in replies:
            if str(getattr(reply, "message_type", "")) not in {"agent", "agent_streaming"}:
                continue
            metadata = dict(getattr(reply, "metadata_json", None) or {})
            linked_id = str(metadata.get("question_message_id") or metadata.get("trigger_message_id") or "")
            if linked_id != message_id:
                continue
            metadata["source_recalled" if recalled else "source_revised"] = True
            metadata["confirmation_status"] = "invalid_source"
            updated = await self._repo.update_message_content(
                org_id=self._org_id,
                room_id=room_id,
                message_id=str(reply.id),
                content=str(getattr(reply, "content", "") or ""),
                metadata_json=metadata,
            )
            if updated:
                await self._publish_message_event(
                    room_id,
                    MeetingMessageResponse.model_validate(updated),
                )

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
        agent_message_id = self._agent_message_id_for_request(room_id, request)
        access = self._authorize_general_agent_request(room=room, question=request.query, intent="agent_manager")
        requested_visibility = self._response_visibility_for_request(request)
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
                    **self._response_visibility_metadata(requested_visibility, room_id=room_id),
                    "response_visibility": requested_visibility,
                    **self._interaction_message_metadata(request, workflow_run_id=workflow_run_id),
                    **self._auto_participation_message_metadata(request),
                },
                private_recipient_user_id=self._user_id if requested_visibility == _RESPONSE_VISIBILITY_PRIVATE else None,
            )
            denial_response = MeetingMessageResponse.model_validate(denial_message)
            await self._record_agent_query_audit(
                room=room,
                question=request.query,
                intent="access_denied",
                source_refs=[],
                tool_calls=[],
                response_visibility=requested_visibility,
            )
            await self._session.commit()
            await meeting_stream_broker.publish(
                room_id,
                {
                    "event": "message_created",
                    "room_id": room_id,
                    "message": denial_response.model_dump(),
                    **({"private_user_ids": [self._user_id]} if requested_visibility == _RESPONSE_VISIBILITY_PRIVATE else {}),
                },
            )
            return MeetingAgentRunResponse(
                selected_subgraph="access_denied",
                answer=denial_response.content,
                message=denial_response,
                memory_sources=[],
                candidate_memories=[],
                response_visibility=requested_visibility,
                escalation_required=False,
            )
        if self._is_general_agent_cancelled(room_id, workflow_run_id):
            raise asyncio.CancelledError()
        response_visibility = requested_visibility
        response_metadata = self._response_visibility_metadata(response_visibility, room_id=room_id)
        private_user_ids = self._private_user_ids_for_visibility(response_visibility)
        recent_messages = (
            await self._list_private_agent_context_messages(room_id=room_id, limit=80)
            if response_visibility == _RESPONSE_VISIBILITY_PRIVATE
            else await self._list_recent_public_messages(room_id=room_id, limit=80)
        )
        rolling_summary = await self._context_summary_json(
            room_id=room_id,
            context_scope="private" if response_visibility == _RESPONSE_VISIBILITY_PRIVATE else "room",
            user_key=self._user_id if response_visibility == _RESPONSE_VISIBILITY_PRIVATE else "public",
        )
        allowed_domains = access.allowed_domains or self._effective_domains_for_room(room)
        query = self._clean_general_agent_query(request.query)
        attachment_echo = self._normalize_message_attachments(request.attachments)
        inspection_context = await self._call_build_meeting_inspection_context(room)
        business_context = self._merge_business_context(
            self._business_context_from_room(room),
            self._business_context_from_inspection_context(inspection_context),
        )
        effective_memory_scope = (
            request.memory_scope
            if response_visibility == _RESPONSE_VISIBILITY_PRIVATE
            else MeetingMemoryScopeRequest(
                include_meeting=True,
                include_confirmed=True,
                include_personal_authorized=False,
                include_user=False,
                include_agent=True,
                include_org_space=True,
            )
        )
        memory_sources = await self._collect_memory_sources(
            room_id,
            effective_memory_scope,
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
                    "rolling_summary": rolling_summary,
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
        trust_protocol = agent_output.get("trust_protocol")
        if not isinstance(trust_protocol, dict):
            trust_protocol = build_trust_answer_protocol(
                question=request.query,
                answer=answer,
                status=router_output.status,
                citations=[item for item in list(agent_output.get("citations") or []) if isinstance(item, dict)],
                route_trace=agent_output.get("route_trace") if isinstance(agent_output.get("route_trace"), dict) else {},
                trace_id=str(agent_output.get("trace_id") or workflow_run_id),
                route_confidence=route_decision.confidence,
                refusal_reason=str(router_output.degrade_reason or "").strip() or None,
            ).model_dump(mode="json")
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
                "trust_protocol": trust_protocol,
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
                **self._interaction_message_metadata(request, workflow_run_id=workflow_run_id),
                **({"attachment_echo": attachment_echo} if attachment_echo else {}),
                **self._auto_participation_message_metadata(request),
            },
        )
        response_message = MeetingMessageResponse.model_validate(message)
        if response_visibility == _RESPONSE_VISIBILITY_PRIVATE:
            await self._refresh_private_context_summary(
                room_id=room_id,
                messages=[*recent_messages, message],
            )
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
            trust_protocol=trust_protocol,
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
        rolling_summary: dict[str, Any] | None = None,
    ) -> str:
        user_messages = [
            (
                f"会议Agent建议（未确认）：{str(msg.content).strip()}"
                if str(getattr(msg, "message_type", "")) in {"agent", "agent_streaming"}
                else str(msg.content).strip()
            )
            for msg in messages
            if str(getattr(msg, "content", "")).strip()
            and str(getattr(msg, "message_type", "user")) in {"user", "system", "agent", "agent_streaming"}
        ]
        summarized_messages = [
            str(item.get("content") or "").strip()
            for item in list((rolling_summary or {}).get("discussion_summary") or [])
            if isinstance(item, dict) and str(item.get("content") or "").strip()
        ]
        recent = [*summarized_messages[-8:], *user_messages[-8:]]
        recent = list(dict.fromkeys(recent))[-12:]
        source_lines = "\n".join(f"- {item.title}: {item.summary}" for item in memory_sources[:5])
        if selected_subgraph == "capability_intro":
            return (
                "我是会议Agent，负责把会议室里的讨论整理成可执行、可追溯的结果。\n\n"
                "我现在可以做这些事：\n"
                "1. 回答你在会议里点名提出的问题。\n"
                "2. 基于当前会议内容生成会议纪要。\n"
                "3. 从公共讨论中整理待确认知识，经人工确认后进入共享知识。\n"
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
                "我已根据公共会议内容整理待确认知识，人工确认前不会成为正式结论；原始会议聊天不会自动共享到其他会议室。\n\n"
                f"整理依据：\n{self._bullet_recent(recent[-5:])}"
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
            "可沉淀内容已整理为待确认知识，请在知识区确认后再进入共享知识。"
        )

    @staticmethod
    def _bullet_recent(items: list[str]) -> str:
        if not items:
            return "- 暂无足够会议上下文"
        return "\n".join(f"- {item[:160]}" for item in items)

    async def _hybrid_candidate_entries(
        self,
        messages: list[Any],
        *,
        room_id: str,
        business_context: MeetingBusinessContext,
        topic: str,
        intent: str,
        max_items: int,
    ) -> list[dict[str, Any]]:
        has_semantic_input = any(
            not self._is_low_value_memory_text(str(getattr(message, "content", "") or ""))
            for message in messages
        )
        if not has_semantic_input:
            return []

        trace_id = f"meeting-qdl:{room_id}:{uuid.uuid4().hex[:12]}"
        semantic_result = await MeetingQDLExtractionService(self._session, self._org_id).extract(
            messages,
            max_items=max_items,
            topic=topic,
            trace_id=trace_id,
        )
        extraction_usage = semantic_result.usage or {}
        logger.info(
            "meeting QDL extraction room_id=%s status=%s method=%s elapsed_ms=%s candidates=%s invalid=%s "
            "prompt_tokens=%s completion_tokens=%s total_tokens=%s error=%s",
            room_id,
            semantic_result.status,
            "mixed" if semantic_result.status == "success" else "heuristic",
            semantic_result.elapsed_ms,
            len(semantic_result.entries),
            semantic_result.invalid_candidate_count,
            int(extraction_usage.get("prompt_tokens") or 0),
            int(extraction_usage.get("completion_tokens") or 0),
            int(extraction_usage.get("total_tokens") or 0),
            semantic_result.error_code,
        )
        if semantic_result.status == "success":
            return list(semantic_result.entries)

        entries = (
            self._risk_forecast_candidate_entries(messages, business_context, topic=topic, max_items=max_items)
            if intent == "risk_forecast"
            else self._candidate_entries_from_messages(messages, topic=topic, max_items=max_items)
        )
        for entry in entries:
            entry["extraction_method"] = "heuristic"
            entry["extraction_model_id"] = semantic_result.model_id
            entry["extraction_elapsed_ms"] = semantic_result.elapsed_ms
            entry["extraction_usage"] = semantic_result.usage
            entry["extraction_fallback_reason"] = semantic_result.error_code
        return entries

    async def _extract_candidate_memories_from_messages(
        self,
        room_id: str,
        *,
        max_items: int,
        topic: str = "",
        intent: str = "",
    ) -> list[MeetingCandidateMemoryResponse]:
        # Shared knowledge admission is strictly public. Private AI-side questions
        # and answers must never become meeting knowledge candidates.
        messages = await self._list_recent_public_messages(room_id=room_id, limit=80)
        room = await self._repo.get_room(self._org_id, room_id)
        business_context = self._business_context_from_room(room)
        candidate_entries = await self._hybrid_candidate_entries(
            messages,
            room_id=room_id,
            business_context=business_context,
            topic=topic,
            intent=intent,
            max_items=max_items,
        )
        results: list[MeetingCandidateMemoryResponse] = []
        duplicate_skip_count = 0
        low_value_skip_count = 0
        validation_failure_count = 0
        unresolved_entity_count = 0
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
        existing_source_hashes = {
            str((item.content_json or {}).get("extraction_source_hash") or "")
            for item in existing
            if str((item.content_json or {}).get("extraction_source_hash") or "")
        }
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
            if not summary:
                low_value_skip_count += 1
                continue
            if summary in existing_summaries:
                duplicate_skip_count += 1
                continue
            source_spans = list(entry.get("source_spans") or [])
            if source_spans and self._source_spans_seen(source_spans, existing_source_span_keys):
                duplicate_skip_count += 1
                continue
            source_hash = self._candidate_source_hash(room_id, source_spans)
            if source_hash and source_hash in existing_source_hashes:
                duplicate_skip_count += 1
                continue
            memory_id = f"mem_meeting_{uuid.uuid4().hex[:12]}"
            memory_trace_id = f"meeting:{room_id}:{memory_id}"
            content = self._candidate_detail_text(str(entry.get("content") or summary))
            if not entry.get("qdl_semantics") and not self._candidate_has_memory_value(summary, content):
                low_value_skip_count += 1
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
            structured_payload.update(
                {
                    "qdl_semantics": entry.get("qdl_semantics"),
                    "extraction_method": str(entry.get("extraction_method") or "heuristic"),
                    "extraction_model_id": entry.get("extraction_model_id"),
                    "extraction_elapsed_ms": int(entry.get("extraction_elapsed_ms") or 0),
                    "extraction_usage": entry.get("extraction_usage") if isinstance(entry.get("extraction_usage"), dict) else None,
                    "extraction_fallback_reason": entry.get("extraction_fallback_reason"),
                    "extraction_source_hash": source_hash,
                    "trace_id": memory_trace_id,
                }
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
            idempotency_key = (
                f"meeting-qdl:{room_id}:{source_hash}" if source_hash else None
            )
            candidate_key = self._meeting_candidate_key(memory_type, dedupe_key)
            canonical_claim = self._meeting_canonical_claim(
                memory_type=memory_type,
                room_id=room_id,
                summary=summary,
                content=content,
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
                low_value_skip_count += 1
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
            qdl_result = parse_qdl(qdl_json)
            if qdl_result.document is None:
                validation_failure_count += 1
                logger.warning(
                    "meeting QDL candidate rejected room_id=%s validation_errors=%s",
                    room_id,
                    len(qdl_result.errors),
                )
                continue
            affected_objects = structured_payload.get("affected_objects")
            has_entity_candidate = bool(structured_payload.get("object_candidates")) or bool(
                isinstance(affected_objects, dict)
                and any(bool(value) for value in affected_objects.values())
            )
            if (
                has_entity_candidate
                and str(structured_payload.get("object_resolution_status") or "") != _OBJECT_RESOLUTION_RESOLVED
            ):
                unresolved_entity_count += 1
            discussion_relations = self._merge_discussion_relations(
                [],
                related_memory_ids,
                relation_type="supplement",
                status="pending",
                created_by=self._user_id,
                note="会议Agent根据主题和业务对象自动识别的关联",
            )
            item = MemoryItem(
                id=str(uuid7()),
                memory_id=memory_id,
                org_id=self._org_id,
                user_id=None,
                memory_type=memory_type,
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
                applicability_json={
                    "task_ids": business_context.task_ids,
                    "product_ids": business_context.product_ids,
                    "batch_nos": business_context.batch_nos,
                    "standard_ids": business_context.standard_ids,
                    "business_context": business_context.model_dump(mode="json"),
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
                    "discussion_relations": discussion_relations,
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
                idempotency_key=idempotency_key,
                source_trace_id=memory_trace_id,
                source_message_id=source_message_id,
                candidate_key=candidate_key,
                canonical_claim=canonical_claim,
                origin_evidence_count=1,
                independent_support_count=0,
                support_count=1,
                human_confirmation_count=0,
                opposition_count=0,
                last_supported_at=datetime.utcnow(),
                last_evidence_at=datetime.utcnow(),
                trust_score=0.65,
                confidence=0.65,
                visibility_scope={"meeting_room_id": room_id},
                usage_policy="context_only",
                ttl_policy="never",
                privacy_level="tenant_private",
                review_status="candidate",
                readiness_status="collecting",
                readiness_blockers=[],
                migration_review_required=False,
                status="candidate",
                created_by=self._user_id,
                created_by_type="agent",
                trace_id=memory_trace_id,
                expires_at=None,
            )
            try:
                begin_nested = getattr(self._session, "begin_nested", None)
                if idempotency_key and callable(begin_nested):
                    async with begin_nested():
                        await self._repo.create_memory_item(item)
                else:
                    await self._repo.create_memory_item(item)
            except IntegrityError:
                existing_item = await self._repo.get_memory_item_by_idempotency_key(
                    self._org_id,
                    idempotency_key,
                ) if idempotency_key else None
                if existing_item is None:
                    raise
                logger.info(
                    "meeting QDL candidate duplicate skipped room_id=%s source_hash=%s memory_id=%s",
                    room_id,
                    source_hash,
                    existing_item.memory_id,
                )
                duplicate_skip_count += 1
                existing_source_hashes.add(source_hash)
                continue
            await self._repo.create_memory_scope_binding(
                org_id=self._org_id,
                memory_id=memory_id,
                scope_type="meeting_room",
                scope_id=room_id,
                permission="confirm",
                created_by=self._user_id,
                binding_kind="home",
                binding_status="active",
            )
            origin_source_type = "meeting_message" if source_message_id else "meeting_room"
            origin_source_id = source_message_id or room_id
            origin_dedupe_key = hashlib.sha256(
                f"meeting\x1f{origin_source_type}\x1f{origin_source_id}".encode("utf-8")
            ).hexdigest()
            origin = await self._repo.create_memory_origin(
                MemoryOrigin(
                    id=str(uuid7()),
                    org_id=self._org_id,
                    memory_id=memory_id,
                    origin_kind="meeting",
                    source_type=origin_source_type,
                    source_id=origin_source_id,
                    trace_id=memory_trace_id,
                    dedupe_key=origin_dedupe_key,
                    source_span=source_spans[0] if source_spans else None,
                    metadata_json={"meeting_room_id": room_id, "source_refs": source_refs},
                    occurred_at=datetime.utcnow(),
                )
            )
            await self._repo.create_memory_evidence(
                MemoryEvidence(
                    id=str(uuid7()),
                    org_id=self._org_id,
                    memory_id=memory_id,
                    evidence_role="origin",
                    source_kind="meeting",
                    source_type=origin_source_type,
                    source_id=origin_source_id,
                    independence_key=origin_dedupe_key,
                    trace_id=memory_trace_id,
                    evidence_pointer={
                        "origin_id": str(origin.id),
                        "meeting_room_id": room_id,
                        "source_message_id": source_message_id,
                        "source_refs": source_refs,
                    },
                    confidence=max(0.35, min(0.92, value_score)),
                    weight=1.0,
                    occurred_at=datetime.utcnow(),
                )
            )
            create_candidate_support = getattr(self._repo, "create_memory_candidate_support", None)
            if callable(create_candidate_support):
                await create_candidate_support(
                    MemoryCandidateSupport(
                        id=str(uuid7()),
                        org_id=self._org_id,
                        candidate_memory_id=memory_id,
                        support_type="source_evidence",
                        source_kind="meeting",
                        source_agent=_MEETING_GENERAL_AGENT_ID,
                        trace_id=memory_trace_id,
                        evidence_pointer={
                            "meeting_room_id": room_id,
                            "source_message_id": source_message_id,
                            "source_refs": source_refs,
                        },
                        confidence=max(0.35, min(0.92, value_score)),
                        weight=max(0.35, min(0.92, value_score)),
                    )
                )
            if source_hash:
                existing_source_hashes.add(source_hash)
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
                    discussion_relations=discussion_relations,
                    extraction_reason=self._candidate_extraction_reason(memory_type, content, structured_payload, value_score),
                    confidence=max(0.35, min(0.92, value_score)),
                    source_message_id=source_message_id,
                    qdl_json=qdl_json,
                    qdl_schema_version=qdl_result.schema_version,
                    qdl_validation_status=qdl_result.validation_status,
                    qdl_validation_errors=list(qdl_result.errors),
                    extraction_method=str(structured_payload.get("extraction_method") or "heuristic"),
                    extraction_model_id=(
                        str(structured_payload.get("extraction_model_id"))
                        if structured_payload.get("extraction_model_id")
                        else None
                    ),
                    extraction_metrics={
                        "elapsed_ms": int(structured_payload.get("extraction_elapsed_ms") or 0),
                        "usage": structured_payload.get("extraction_usage"),
                        "fallback_reason": structured_payload.get("extraction_fallback_reason"),
                    },
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
                    "discussion_relations": discussion_relations,
                    "value_score": value_score,
                },
            )
        extraction_usage = next(
            (
                entry.get("extraction_usage")
                for entry in candidate_entries
                if isinstance(entry.get("extraction_usage"), dict)
            ),
            {},
        )
        logger.info(
            "meeting QDL extraction summary room_id=%s public_messages=%s generated=%s created=%s "
            "duplicate_skipped=%s low_value_skipped=%s validation_failed=%s unresolved_entities=%s "
            "fallback_candidates=%s prompt_tokens=%s completion_tokens=%s total_tokens=%s",
            room_id,
            len(messages),
            len(candidate_entries),
            len(results),
            duplicate_skip_count,
            low_value_skip_count,
            validation_failure_count,
            unresolved_entity_count,
            sum(1 for entry in candidate_entries if str(entry.get("extraction_method") or "") == "heuristic"),
            int(extraction_usage.get("prompt_tokens") or 0),
            int(extraction_usage.get("completion_tokens") or 0),
            int(extraction_usage.get("total_tokens") or 0),
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
                        "text": detail_text,
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
            r"^\s*一条待确认知识已被拒绝.*$",
            r"^\s*待确认知识已被拒绝.*$",
            r"^\s*用户拒绝待确认知识.*$",
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
        if any(term in text for term in (
            "候选记忆已拒绝",
            "一条候选记忆已被拒绝",
            "待确认知识已拒绝",
            "一条待确认知识已被拒绝",
            "会议agent正在",
        )):
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
        return (compact[:36] or f"会议待确认知识 {index}").strip()

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
        return title or f"会议待确认知识 {index}"

    @staticmethod
    def _candidate_title_source(value: str) -> str:
        text = str(value or "").replace("\r\n", "\n").strip()
        text = re.sub(r"^@\S+\s*", "", text)
        text = re.sub(
            r"^\s*(会议形成待确认结论|会议待确认结论|会议结论|会议待确认知识|待确认知识|候选记忆|风险洞察候选|行动项|建议)\s*[：:]\s*",
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
    def _candidate_source_hash(room_id: str, source_spans: list[dict[str, Any]]) -> str:
        parts = [str(room_id or "")]
        for span in source_spans:
            if not isinstance(span, dict):
                continue
            parts.append(
                "|".join(
                    [
                        str(span.get("message_id") or ""),
                        str(span.get("start") or 0),
                        str(span.get("end") or 0),
                        re.sub(r"\s+", " ", str(span.get("text") or "")).strip(),
                    ]
                )
            )
        if len(parts) == 1:
            return ""
        return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()

    @staticmethod
    def _meeting_candidate_key(memory_type: str, dedupe_key: str) -> str:
        semantic_hash = hashlib.sha256(
            f"{memory_type}\x1f{dedupe_key}".encode("utf-8")
        ).hexdigest()
        return f"meeting-qdl:{memory_type}:{semantic_hash}"[:256]

    @staticmethod
    def _meeting_canonical_claim(
        *,
        memory_type: str,
        room_id: str,
        summary: str,
        content: str,
    ) -> dict[str, Any]:
        normalize = lambda value: re.sub(r"\s+", " ", str(value or "")).strip().lower()
        return {
            "memory_type": memory_type,
            "scope": {"scope_type": "meeting_room", "scope_id": room_id},
            "summary": normalize(summary)[:240],
            "facts": [normalize(content)[:1000]],
        }

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
                        "必要时在协作中心发起结构化处理请求",
                    ],
                }
            )
        return payload

    def _memory_qdl_json(
        self,
        memory_type: str,
        title: str,
        content: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = payload or {}
        semantics = payload.get("qdl_semantics") if isinstance(payload.get("qdl_semantics"), dict) else {}
        semantic_properties = semantics.get("properties") if isinstance(semantics.get("properties"), dict) else {}
        try:
            properties = QDLKnowledgeProperties.model_validate(semantic_properties)
        except Exception:
            properties = QDLKnowledgeProperties()

        room_id = str(payload.get("source_room_id") or payload.get("source_id") or "legacy-unknown")
        source_spans = [item for item in list(payload.get("source_spans") or []) if isinstance(item, dict)]
        evidence: list[QDLEvidence] = []
        message_ids: list[str] = []
        for span in source_spans:
            message_id = str(span.get("message_id") or payload.get("source_message_id") or "") or None
            if message_id and message_id not in message_ids:
                message_ids.append(message_id)
            evidence.append(
                QDLEvidence(
                    source_type="meeting_message",
                    source_id=message_id,
                    message_id=message_id,
                    quote_text=str(span.get("text") or "") or None,
                    span_start=int(span.get("start")) if isinstance(span.get("start"), int) else None,
                    span_end=int(span.get("end")) if isinstance(span.get("end"), int) else None,
                    occurred_at=self._parse_datetime(span.get("occurred_at")),
                )
            )
        for ref in list(payload.get("evidence_refs") or payload.get("source_refs") or []):
            if not isinstance(ref, dict):
                continue
            source_type = str(ref.get("type") or ref.get("source_type") or "meeting_source")
            source_id = str(ref.get("id") or ref.get("source_id") or "") or None
            message_id = source_id if source_type == "meeting_message" else None
            if message_id and message_id not in message_ids:
                message_ids.append(message_id)
            if any(item.source_type == source_type and item.source_id == source_id for item in evidence):
                continue
            evidence.append(
                QDLEvidence(
                    source_type=source_type,
                    source_id=source_id or room_id,
                    message_id=message_id,
                    quote_text=str(ref.get("text") or ref.get("quote_text") or "") or None,
                    occurred_at=self._parse_datetime(ref.get("occurred_at") or ref.get("created_at")),
                )
            )
        source_message_id = str(payload.get("source_message_id") or "") or None
        if source_message_id and source_message_id not in message_ids:
            message_ids.append(source_message_id)
            evidence.append(
                QDLEvidence(
                    source_type="meeting_message",
                    source_id=source_message_id,
                    message_id=source_message_id,
                )
            )
        if not evidence:
            evidence.append(QDLEvidence(source_type="meeting_room", source_id=room_id))

        affected_objects = payload.get("affected_objects") if isinstance(payload.get("affected_objects"), dict) else {}
        object_status = str(payload.get("object_resolution_status") or _OBJECT_RESOLUTION_UNRESOLVED)
        if object_status not in {_OBJECT_RESOLUTION_RESOLVED, _OBJECT_RESOLUTION_AMBIGUOUS, _OBJECT_RESOLUTION_UNRESOLVED}:
            object_status = _OBJECT_RESOLUTION_UNRESOLVED
        entities: list[QDLEntity] = []
        entity_keys = {
            "product_ids": "product",
            "batch_nos": "batch",
            "inspection_task_ids": "task",
            "task_ids": "task",
            "standard_ids": "standard",
        }
        for key, entity_type in entity_keys.items():
            for raw_value in list(affected_objects.get(key) or []):
                value = str(raw_value or "").strip()
                if not value:
                    continue
                entities.append(
                    QDLEntity(
                        entity_type=entity_type,
                        value=value,
                        entity_id=value,
                        resolution_status=object_status,
                        confidence=1 if object_status == _OBJECT_RESOLUTION_RESOLVED else None,
                    )
                )
        deterministic_entities = {(item.entity_type, item.value) for item in entities}
        for raw_entity in list(semantics.get("entities") or []):
            try:
                entity = QDLEntity.model_validate(raw_entity)
            except Exception:
                continue
            key = (entity.entity_type, entity.value)
            if key in deterministic_entities:
                continue
            entities.append(entity.model_copy(update={"resolution_status": "unresolved"}))

        raw_scope = str(
            payload.get("target_scope_type")
            or payload.get("published_scope")
            or payload.get("recommended_scope")
            or _MEMORY_SCOPE_MEETING_ROOM
        )
        scope_type = self._normalize_memory_scope(raw_scope)
        if scope_type not in _MEMORY_PUBLISH_SCOPES:
            scope_type = _MEMORY_SCOPE_MEETING_ROOM
        scope_id = str(
            payload.get("target_scope_id")
            or payload.get("recommended_scope_id")
            or (room_id if scope_type == _MEMORY_SCOPE_MEETING_ROOM else "")
        ) or None
        conditions = [str(item)[:500] for item in list(semantics.get("applicability_conditions") or []) if str(item).strip()]
        forecast_window = payload.get("forecast_window")
        if isinstance(forecast_window, dict) and forecast_window.get("label"):
            conditions.append(f"forecast_window:{forecast_window['label']}")

        relation_mapping = {
            "support": "supports",
            "confirm": "supports",
            "oppose": "contradicts",
            "conflict": "contradicts",
            "supplement": "supplements",
            "revise": "refines",
            "depends": "depends_on",
        }
        relations: list[QDLRelation] = []
        for raw_relation in list(payload.get("discussion_relations") or []):
            if not isinstance(raw_relation, dict):
                continue
            target_id = str(raw_relation.get("target_memory_id") or raw_relation.get("target_id") or "")
            relation_type = relation_mapping.get(str(raw_relation.get("relation_type") or ""))
            if not target_id or not relation_type:
                continue
            relations.append(
                QDLRelation(
                    relation_type=relation_type,
                    target_id=target_id,
                    status=str(raw_relation.get("status") or "") or None,
                    confidence=(
                        float(raw_relation["confidence"])
                        if isinstance(raw_relation.get("confidence"), (int, float))
                        else None
                    ),
                    note=str(raw_relation.get("note") or "") or None,
                )
            )
        conflicting_id = str(payload.get("conflicting_memory_id") or "")
        if conflicting_id and not any(item.target_id == conflicting_id for item in relations):
            relations.append(QDLRelation(relation_type="contradicts", target_id=conflicting_id, status="disputed"))

        governance_status = str(payload.get("governance_status") or "")
        if not governance_status:
            if payload.get("rejected_at"):
                governance_status = "rejected"
            elif payload.get("superseded_at") or payload.get("superseded_by"):
                governance_status = "superseded"
            elif payload.get("last_disputed_at") or payload.get("disputes"):
                governance_status = "disputed"
            elif payload.get("confirmed_at"):
                governance_status = "confirmed"
            else:
                governance_status = "candidate"
        allowed_statuses = {"candidate", "confirmed", "disputed", "active", "rejected", "isolated", "superseded", "discarded"}
        if governance_status not in allowed_statuses:
            governance_status = "candidate"
        consensus_status = {
            "confirmed": "confirmed",
            "active": "confirmed",
            "superseded": "confirmed",
            "disputed": "disputed",
            "isolated": "disputed",
            "rejected": "rejected",
            "discarded": "rejected",
        }.get(governance_status, "candidate")
        confirmed_by = str(payload.get("confirmed_by") or "") or None
        try:
            lifecycle_revision = max(int(payload.get("revision") or payload.get("memory_version") or 1), 1)
        except (TypeError, ValueError):
            lifecycle_revision = 1
        semantic_level = str(semantics.get("knowledge_level") or "")
        knowledge_level = (
            semantic_level
            if semantic_level in {"fact", "decision", "rule", "pattern", "concept", "hypothesis"}
            else knowledge_level_for_memory_type(memory_type)
        )
        document = QDLDocument(
            knowledge_level=knowledge_level,
            claim=QDLClaim(
                title=str(title or "会议记忆")[:200],
                text=str(content or "")[:8000],
                type=str(memory_type or "decision")[:64],
            ),
            properties=properties,
            entities=entities,
            applicability=QDLApplicability(
                scope_type=scope_type,
                scope_id=scope_id,
                conditions=self._dedupe_text_values(conditions, limit=30, max_length=500),
                business_tags={
                    str(key): [str(item) for item in list(values or []) if str(item).strip()]
                    for key, values in affected_objects.items()
                    if isinstance(values, list)
                },
            ),
            evidence=evidence,
            relations=relations,
            provenance=QDLProvenance(
                org_id=self._org_id,
                room_id=room_id,
                message_ids=message_ids,
                extraction_method=(
                    str(payload.get("extraction_method"))
                    if str(payload.get("extraction_method") or "") in {"llm", "heuristic", "mixed"}
                    else "heuristic"
                ),
                model_id=str(payload.get("extraction_model_id") or "") or None,
                trace_id=str(payload.get("trace_id") or "") or None,
                source_hash=str(payload.get("extraction_source_hash") or "") or None,
                generated_at=self._parse_datetime(payload.get("extraction_generated_at")) or datetime.utcnow(),
            ),
            governance=QDLGovernance(
                status=governance_status,
                requires_human_confirmation=governance_status in {"candidate", "disputed", "isolated"},
                confirmed_by=confirmed_by,
                confirmed_at=self._parse_datetime(payload.get("confirmed_at")),
                disputed_by=str(payload.get("last_disputed_by") or "") or None,
                rejected_by=str(payload.get("rejected_by") or "") or None,
            ),
            consensus=QDLConsensus(
                status=consensus_status,
                support_count=int(payload.get("support_count") or 0),
                oppose_count=int(payload.get("negative_count") or payload.get("oppose_count") or 0),
                confirmed_by=[confirmed_by] if confirmed_by else [],
            ),
            lifecycle=QDLLifecycle(
                revision=lifecycle_revision,
                parent_memory_id=str(payload.get("version_parent_id") or "") or None,
                effective_at=self._parse_datetime(payload.get("confirmed_at")),
                supersedes_memory_id=str(payload.get("supersedes_memory_id") or "") or None,
                superseded_by_memory_id=str(payload.get("superseded_by") or "") or None,
            ),
        )
        return document.model_dump(mode="json")

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
            warnings.append("该记忆默认沉淀到当前会议室；确认后可申请共享给成员、其他会议室、Agent 或组织共享空间。")
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
            warnings.append("该待确认知识可能关联多个业务标签，确认前可人工校准标签。")
        if object_resolution_status == _OBJECT_RESOLUTION_UNRESOLVED and memory_category == _BUSINESS_MEMORY_CATEGORY:
            warnings.append("该待确认知识尚未识别业务标签，但仍可沉淀为共享知识。")
        if related_memory_ids:
            warnings.append("该待确认知识可能与既有知识重复或形成补充，确认前请检查关联知识。")
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
            "governance_status": "confirmed",
            "discussion_relations": self._merge_discussion_relations(
                list(content_json.get("discussion_relations") or []),
                [str(item.memory_id)],
                relation_type="revise",
                status="confirmed",
                created_by=self._user_id,
                note="由上一版本修订生成",
            ),
            "published_scope": requested_scope,
            "target_scope_type": target_scope_type,
            "target_scope_id": target_scope_id,
        }
        revision_content["qdl_json"] = self._memory_qdl_json(
            str(revision_content.get("memory_type") or "decision"),
            str(revision_content.get("title") or item.content_summary or ""),
            content,
            revision_content,
        )
        revision = MemoryItem(
            id=str(uuid7()),
            memory_id=revision_memory_id,
            org_id=self._org_id,
            user_id=getattr(item, "user_id", None),
            memory_type=str(revision_content.get("memory_type") or getattr(item, "memory_type", "") or "decision"),
            scope_json=self._memory_scope_json(target_scope_type, target_scope_id, source_room_id=room_id),
            applicability_json=dict(getattr(item, "applicability_json", None) or {}),
            content_summary=content[:1000],
            content_json=revision_content,
            source_event_ids=getattr(item, "source_event_ids", None),
            evidence_pointers={
                **dict(getattr(item, "evidence_pointers", None) or {}),
                "revision_parent_id": str(item.memory_id),
            },
            version_parent_id=str(item.memory_id),
            origin_evidence_count=1,
            independent_support_count=0,
            support_count=2,
            human_confirmation_count=1,
            opposition_count=0,
            human_approved=True,
            last_evidence_at=datetime.utcnow(),
            last_supported_at=datetime.utcnow(),
            trust_score=getattr(item, "trust_score", None),
            confidence=getattr(item, "confidence", None),
            visibility_scope=getattr(item, "visibility_scope", None),
            usage_policy=str(getattr(item, "usage_policy", "") or "context_only"),
            ttl_policy=str(getattr(item, "ttl_policy", "") or "never"),
            privacy_level=str(getattr(item, "privacy_level", "") or "tenant_private"),
            review_status="approved",
            readiness_status="ready",
            readiness_blockers=[],
            migration_review_required=False,
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
            binding_kind="home",
            binding_status="active",
            approved_by=self._user_id,
            approved_at=datetime.utcnow(),
        )
        revision_origin_key = hashlib.sha256(
            f"meeting\x1fmemory_revision\x1f{item.memory_id}".encode("utf-8")
        ).hexdigest()
        origin = await self._repo.create_memory_origin(
            MemoryOrigin(
                id=str(uuid7()),
                org_id=self._org_id,
                memory_id=revision_memory_id,
                origin_kind="meeting",
                source_type="memory_revision",
                source_id=str(item.memory_id),
                trace_id=revision.trace_id,
                dedupe_key=revision_origin_key,
                metadata_json={"meeting_room_id": room_id},
                occurred_at=datetime.utcnow(),
            )
        )
        await self._repo.create_memory_evidence(
            MemoryEvidence(
                id=str(uuid7()),
                org_id=self._org_id,
                memory_id=revision_memory_id,
                evidence_role="origin",
                source_kind="meeting",
                source_type="memory_revision",
                source_id=str(item.memory_id),
                independence_key=revision_origin_key,
                trace_id=revision.trace_id,
                evidence_pointer={"origin_id": str(origin.id), "parent_memory_id": str(item.memory_id)},
                confidence=revision.confidence,
                weight=1.0,
                occurred_at=datetime.utcnow(),
            )
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
            return True
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

    async def _enrich_memory_share_state(
        self,
        memories: list[MeetingMemoryResponse],
    ) -> list[MeetingMemoryResponse]:
        memory_ids = [memory.memory_id for memory in memories]
        if not memory_ids:
            return memories
        list_bindings = getattr(self._repo, "list_memory_scope_bindings", None)
        list_transfers = getattr(self._repo, "list_memory_transfer_logs", None)
        if list_bindings is None or list_transfers is None:
            return memories
        bindings = await list_bindings(org_id=self._org_id, memory_ids=memory_ids)
        pending = await list_transfers(
            org_id=self._org_id,
            memory_ids=memory_ids,
            statuses=["pending_approval"],
            limit=max(200, len(memory_ids) * 5),
        )
        bindings_by_memory: dict[str, list[Any]] = {}
        for binding in bindings:
            bindings_by_memory.setdefault(str(binding.memory_id), []).append(binding)
        pending_by_memory: dict[str, list[Any]] = {}
        for row in pending:
            pending_by_memory.setdefault(str(row.memory_id), []).append(row)
        enriched: list[MeetingMemoryResponse] = []
        for memory in memories:
            home_key = (str(memory.scope_type or ""), str(memory.scope_id or ""))
            shared_scopes = [
                {
                    "scope_type": str(binding.scope_type),
                    "scope_id": str(binding.scope_id),
                    "permission": str(binding.permission),
                }
                for binding in bindings_by_memory.get(memory.memory_id, [])
                if (str(binding.scope_type), str(binding.scope_id)) != home_key
            ]
            pending_requests = [
                {
                    "id": str(row.id),
                    "target_scope_type": str(row.to_scope_type),
                    "target_scope_id": str(row.to_scope_id),
                    "status": "pending_approval",
                    "requested_by": str(getattr(row, "requested_by", None) or getattr(row, "operator_id", None) or "") or None,
                    "share_reason": getattr(row, "transfer_reason", None),
                    "created_at": getattr(row, "created_at", None),
                }
                for row in pending_by_memory.get(memory.memory_id, [])
            ]
            enriched.append(
                memory.model_copy(
                    update={
                        "shared_scopes": shared_scopes,
                        "pending_share_requests": pending_requests,
                        "pending_transfer_id": (
                            str(pending_requests[-1]["id"])
                            if pending_requests
                            else None
                        ),
                        "requested_scope_type": (
                            str(pending_requests[-1]["target_scope_type"])
                            if pending_requests
                            else None
                        ),
                        "requested_scope_id": (
                            str(pending_requests[-1]["target_scope_id"])
                            if pending_requests
                            else None
                        ),
                    }
                )
            )
        return enriched

    def _serialize_memory_item(self, item: MemoryItem, *, room_id: str) -> MeetingMemoryResponse:
        content_json = item.content_json or {}
        scope_json = item.scope_json or {}
        parsed_qdl = parse_qdl(content_json.get("qdl_json"))
        business_context = content_json.get("business_context")
        shareability = content_json.get("shareability")
        scope_type = str(
            scope_json.get("scope_type")
            or content_json.get("published_scope")
            or ("meeting_room" if scope_json.get("meeting_room_id") or room_id else "")
        ) or None
        scope_id = str(
            scope_json.get("scope_id")
            or scope_json.get("meeting_room_id")
            or scope_json.get("room_id")
            or (room_id if scope_type == "meeting_room" else "")
        ) or None
        pending_transfer_id = str(content_json.get("pending_transfer_id") or "") or None
        requested_scope_type = (
            str(content_json.get("target_scope_type") or "") or None
            if pending_transfer_id
            else None
        )
        requested_scope_id = (
            str(content_json.get("target_scope_id") or "") or None
            if pending_transfer_id
            else None
        )
        return MeetingMemoryResponse(
            memory_id=str(item.memory_id),
            title=str(content_json.get("title") or item.content_summary or item.memory_id),
            content=str(content_json.get("content") or item.content_summary or ""),
            summary=str(item.content_summary or ""),
            memory_type=str(content_json.get("memory_type") or item.memory_type),
            status=str(item.status),
            review_status=str(getattr(item, "review_status", "") or "candidate"),
            readiness_status=str(getattr(item, "readiness_status", "") or "collecting"),
            scope=str(content_json.get("published_scope") or content_json.get("recommended_scope") or _MEMORY_SCOPE_MEETING_ROOM),
            scope_type=scope_type,
            scope_id=scope_id,
            requested_scope_type=requested_scope_type,
            requested_scope_id=requested_scope_id,
            pending_transfer_id=pending_transfer_id,
            shared_scopes=[
                dict(entry)
                for entry in list(content_json.get("shared_scopes") or [])
                if isinstance(entry, dict)
            ],
            pending_share_requests=[
                dict(entry)
                for entry in list(content_json.get("pending_share_requests") or [])
                if isinstance(entry, dict)
            ],
            applicability=dict(getattr(item, "applicability_json", None) or {}),
            evidence_summary={
                "origin": int(getattr(item, "origin_evidence_count", 0) or 0),
                "independent_support": int(getattr(item, "independent_support_count", 0) or 0),
                "rag": int(getattr(item, "rag_evidence_count", 0) or 0),
                "agent_verification": int(getattr(item, "agent_verifier_count", 0) or 0),
                "human_confirmation": int(getattr(item, "human_confirmation_count", 0) or 0),
                "opposition": int(getattr(item, "opposition_count", 0) or 0),
                "conflict": int(getattr(item, "conflict_count", 0) or 0),
                "last_evidence_at": (
                    getattr(item, "last_evidence_at", None).isoformat()
                    if getattr(item, "last_evidence_at", None)
                    else None
                ),
            },
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
            discussion_relations=[
                dict(relation)
                for relation in list(content_json.get("discussion_relations") or [])
                if isinstance(relation, dict)
            ],
            extraction_reason=str(content_json.get("extraction_reason")) if content_json.get("extraction_reason") is not None else None,
            publish_reason=content_json.get("publish_reason"),
            version_parent_id=(
                str(content_json.get("version_parent_id") or getattr(item, "version_parent_id", "") or "") or None
            ),
            confidence=float(item.confidence) if item.confidence is not None else None,
            source_message_id=content_json.get("source_message_id"),
            qdl_json=(
                parsed_qdl.document.model_dump(mode="json")
                if parsed_qdl.document is not None
                else None
            ),
            qdl_schema_version=parsed_qdl.schema_version,
            qdl_validation_status=parsed_qdl.validation_status,
            qdl_validation_errors=list(parsed_qdl.errors),
            extraction_method=(
                str(content_json.get("extraction_method"))
                if content_json.get("extraction_method")
                else (
                    parsed_qdl.document.provenance.extraction_method
                    if parsed_qdl.document is not None
                    else None
                )
            ),
            extraction_model_id=(
                str(content_json.get("extraction_model_id"))
                if content_json.get("extraction_model_id")
                else None
            ),
            extraction_metrics={
                "elapsed_ms": int(content_json.get("extraction_elapsed_ms") or 0),
                "usage": content_json.get("extraction_usage") if isinstance(content_json.get("extraction_usage"), dict) else None,
                "fallback_reason": content_json.get("extraction_fallback_reason"),
            },
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
            # Event recording is auxiliary. A sink failure must not poison the
            # surrounding meeting-memory transaction.
            async with self._session.begin_nested():
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

    async def _enqueue_confirmed_memory_sync(self, item: MemoryItem) -> None:
        """Queue derived-index writes for a locally confirmed meeting memory.

        A meeting confirmation makes the home scope usable, but it does not
        grant organization scope.  The payload therefore carries the full
        binding set while keeping organization promotion as a separate
        approval operation.
        """
        list_bindings = getattr(self._repo, "list_memory_scope_bindings", None)
        if not callable(list_bindings) or not callable(getattr(self._session, "execute", None)):
            return
        bindings = await list_bindings(
            org_id=self._org_id,
            memory_ids=[str(item.memory_id)],
        )
        active_bindings = [row for row in bindings if str(row.binding_status) == "active"]
        scope_bindings = [
            {
                "scope_type": row.scope_type,
                "scope_id": row.scope_id,
                "binding_kind": row.binding_kind,
                "binding_status": row.binding_status,
            }
            for row in bindings
        ]
        content = dict(item.content_json or {})
        applicability = dict(getattr(item, "applicability_json", None) or {})
        vector_payload = {
            "collection": MEMORY_COLLECTION,
            "memory_id": str(item.memory_id),
            "org_id": self._org_id,
            "user_id": str(item.user_id or ""),
            "memory_type": str(item.memory_type or ""),
            "status": "active",
            "summary": str(item.content_summary or ""),
            "trust_score": float(item.trust_score or 0),
            "confidence": float(item.confidence or 0),
            "expires_at": item.expires_at.isoformat() if item.expires_at else "",
            "product_line": str(item.product_line or ""),
            "rag_space_id": str(item.rag_space_id or ""),
            "task_id": str(item.task_id or item.source_task_id or ""),
            "extra_payload": {
                "review_status": str(item.review_status or "approved"),
                "origin_kind": str(content.get("source_type") or "meeting"),
                "scope_bindings": scope_bindings,
                "applicability": applicability,
                "trace_id": str(item.trace_id or ""),
            },
        }
        outbox = MemorySyncOutboxRepository(self._session, self._org_id)
        await outbox.create_pending(
            memory_id=str(item.memory_id),
            action="UPSERT_ACTIVE_VECTOR",
            target_backend="qdrant",
            payload=vector_payload,
            trace_id=str(item.trace_id or "") or None,
        )
        await outbox.create_pending(
            memory_id=str(item.memory_id),
            action="UPSERT_MEMORY_NODE",
            target_backend="neo4j",
            payload={
                "memory_id": str(item.memory_id),
                "org_id": self._org_id,
                "memory_type": str(item.memory_type or ""),
                "status": "active",
                "trust_score": float(item.trust_score or 0),
                "confidence": float(item.confidence or 0),
                "scope_key": "|".join(
                    f"{row.scope_type}:{row.scope_id}" for row in active_bindings
                ),
                "review_status": str(item.review_status or "approved"),
                "origin_kind": str(content.get("source_type") or "meeting"),
                "scope_bindings_json": json.dumps(scope_bindings, ensure_ascii=False),
                "applicability_json": json.dumps(applicability, ensure_ascii=False),
                "sync_version": 2,
            },
            trace_id=str(item.trace_id or "") or None,
        )

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
        return (
            _RESPONSE_VISIBILITY_PRIVATE
            if request.interaction_mode == _INTERACTION_PRIVATE_CHAT
            else _RESPONSE_VISIBILITY_ROOM
        )

    @staticmethod
    def _agent_message_id_for_request(room_id: str, request: MeetingAgentRunRequest) -> str:
        if request.replace_message_id:
            return str(request.replace_message_id)
        if request.interaction_mode != _INTERACTION_PRIVATE_CHAT and request.question_message_id:
            revision = str(request.question_revision or "initial")
            return str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"meeting-agent:{room_id}:{request.question_message_id}:{revision}",
                )
            )
        return str(uuid7())

    async def _public_request_uses_private_sources(
        self,
        room_id: str,
        request: MeetingAgentRunRequest,
    ) -> bool:
        source_ids = [
            str(item.get("message_id") or item.get("id") or "").strip()
            for item in request.question_sources
            if isinstance(item, dict)
        ]
        for source_id in filter(None, source_ids):
            source = await self._repo.get_message(self._org_id, room_id, source_id)
            if not source:
                continue
            metadata = getattr(source, "metadata_json", None) or {}
            if self._message_recipient_user_id(source) or str(metadata.get("visibility") or "room") == "private":
                return True
        return False

    @staticmethod
    def _interaction_message_metadata(
        request: MeetingAgentRunRequest,
        *,
        workflow_run_id: str,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "interaction_mode": request.interaction_mode,
            "workflow_run_id": workflow_run_id,
            "confirmation_status": "unconfirmed_ai_suggestion",
        }
        if request.question_message_id:
            metadata["question_message_id"] = request.question_message_id
        if request.trigger_message_id:
            metadata["trigger_message_id"] = request.trigger_message_id
        if request.question_revision:
            metadata["question_revision"] = request.question_revision
        if request.question_sources:
            metadata["question_sources"] = [dict(item) for item in request.question_sources if isinstance(item, dict)]
        return metadata

    @staticmethod
    def _auto_participation_message_metadata(request: MeetingAgentRunRequest) -> dict[str, Any]:
        value = request.auto_participation
        return {"auto_participation": dict(value)} if isinstance(value, dict) and value else {}

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

    async def _publish_memory_share_work_item_event(self, row: Any, event: str) -> None:
        recipient_ids = {
            str(self._user_id),
            str(getattr(row, "requested_by", None) or getattr(row, "operator_id", None) or ""),
            str(getattr(row, "decided_by", None) or ""),
        }
        target_scope_type = str(getattr(row, "to_scope_type", "") or "")
        target_scope_id = str(getattr(row, "to_scope_id", "") or "")
        try:
            if target_scope_type == _MEMORY_SCOPE_USER:
                recipient_ids.add(target_scope_id)
            elif target_scope_type == _MEMORY_SCOPE_MEETING_ROOM:
                members = await self._repo.list_members(self._org_id, target_scope_id)
                recipient_ids.update(
                    str(member.user_id)
                    for member in members
                    if str(getattr(member, "role", "") or "") == "host"
                )
                room = await self._repo.get_room(self._org_id, target_scope_id)
                if room is not None:
                    recipient_ids.add(str(getattr(room, "created_by", "") or ""))
            elif target_scope_type == _MEMORY_SCOPE_ORG_SPACE:
                users = await self._users.list_by_org_id(self._org_id)
                recipient_ids.update(
                    str(user.id)
                    for user in users
                    if str(getattr(user, "role", "") or "") == ROLE_ADMIN
                )
        except Exception:
            logger.debug("failed to resolve all memory share event recipients", exc_info=True)
        payload = {
            "event": event,
            "work_item_id": f"memory_share:{row.id}",
            "resource_id": str(row.id),
            "item_type": "memory_share",
            "status": "approved" if str(row.status) in {"confirmed", "executed"} else str(row.status),
        }
        for recipient_id in {item for item in recipient_ids if item}:
            await collab_stream_broker.publish(recipient_id, payload)

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
        memory_content = ""
        source_refs: list[dict] = []
        affected_objects: dict | None = None
        source_room_id: str | None = None
        item = await self._repo.get_memory_item(self._org_id, str(row.memory_id))
        if item is not None:
            content_json = dict(getattr(item, "content_json", None) or {})
            memory_title = str(content_json.get("title") or getattr(item, "content_summary", "") or item.memory_id)
            memory_content = str(content_json.get("content") or getattr(item, "content_summary", "") or "")
            source_refs = [dict(entry) for entry in list(content_json.get("source_refs") or []) if isinstance(entry, dict)]
            affected_objects = content_json.get("affected_objects") if isinstance(content_json.get("affected_objects"), dict) else None
            source_room_id = str(content_json.get("source_room_id") or "") or None
        can_approve = False
        try:
            await self._ensure_memory_share_approver(row)
            can_approve = str(getattr(row, "status", "") or "") == "pending_approval"
        except Exception:
            can_approve = False
        requested_by = str(
            getattr(row, "requested_by", None)
            or getattr(row, "operator_id", None)
            or ""
        ) or None
        raw_status = str(getattr(row, "status", "") or "")
        status = "approved" if raw_status in {"confirmed", "executed"} else raw_status
        return MeetingMemoryShareApprovalResponse(
            id=str(row.id),
            memory_id=str(row.memory_id),
            from_scope_type=str(row.from_scope_type),
            from_scope_id=str(row.from_scope_id),
            to_scope_type=str(row.to_scope_type),
            to_scope_id=str(row.to_scope_id),
            transfer_reason=getattr(row, "transfer_reason", None),
            status=status,
            operator_id=str(row.operator_id) if getattr(row, "operator_id", None) else None,
            requested_by=requested_by,
            decided_by=(str(row.decided_by) if getattr(row, "decided_by", None) else None),
            decided_at=getattr(row, "decided_at", None),
            decision_note=getattr(row, "decision_note", None),
            idempotency_key=getattr(row, "idempotency_key", None),
            mapping_plan=(
                dict(getattr(row, "mapping_plan_json", None))
                if isinstance(getattr(row, "mapping_plan_json", None), dict)
                else None
            ),
            mapping_version=(str(getattr(row, "mapping_version", "") or "") or None),
            interpolation_strategy=(str(getattr(row, "interpolation_strategy", "") or "") or None),
            unmapped_fields=(
                [
                    str(value)
                    for value in list((getattr(row, "mapping_plan_json", None) or {}).get("unmapped_fields") or [])
                ]
                if isinstance(getattr(row, "mapping_plan_json", None), dict)
                else []
            ),
            memory_title=memory_title,
            memory_content=memory_content,
            source_refs=source_refs,
            affected_objects=affected_objects,
            source_room_id=source_room_id,
            can_approve=can_approve,
            can_cancel=status == "pending_approval" and requested_by == self._user_id,
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

    async def _invoke_general_agent_reply(
        self,
        *,
        room_id: str,
        query: str,
        question_message_id: str,
        question_revision: str,
    ) -> None:
        try:
            async with get_session() as session:
                service = MeetingService(session, self._org_id, self._user_id, role=self._role)
                await service.run_general_agent(
                    room_id,
                    MeetingAgentRunRequest(
                        query=query,
                        mode="auto",
                        interaction_mode=_INTERACTION_PUBLIC_MENTION,
                        question_message_id=question_message_id,
                        trigger_message_id=question_message_id,
                        question_revision=question_revision,
                        question_sources=[{"message_id": question_message_id, "kind": "public_message"}],
                    ),
                )
                await session.commit()
        except Exception as exc:
            logger.exception("meeting general agent invocation failed room_id=%s", room_id)
            await self._publish_general_agent_failure(
                room_id=room_id,
                error=str(exc) or exc.__class__.__name__,
                interaction_mode=_INTERACTION_PUBLIC_MENTION,
                question_message_id=question_message_id,
            )

    async def _publish_general_agent_failure(
        self,
        *,
        room_id: str,
        error: str,
        interaction_mode: str = _INTERACTION_PRIVATE_CHAT,
        question_message_id: str | None = None,
    ) -> None:
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
                        "interaction_mode": interaction_mode,
                        "question_message_id": question_message_id,
                        "trigger_message_id": question_message_id,
                        "visibility": (
                            _RESPONSE_VISIBILITY_PRIVATE
                            if interaction_mode == _INTERACTION_PRIVATE_CHAT
                            else _RESPONSE_VISIBILITY_ROOM
                        ),
                        **(
                            {"private_recipient_user_id": self._user_id}
                            if interaction_mode == _INTERACTION_PRIVATE_CHAT
                            else {}
                        ),
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
                        **(
                            {"private_user_ids": [self._user_id]}
                            if interaction_mode == _INTERACTION_PRIVATE_CHAT
                            else {}
                        ),
                    },
                )
        except Exception:
            logger.exception("meeting general agent failure message publish failed room_id=%s", room_id)
