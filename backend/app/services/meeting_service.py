from __future__ import annotations

import asyncio
import logging
import re
import secrets
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import uuid7
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.security import hash_password, verify_password
from app.models.memory import MemoryItem
from app.repositories.meeting_repo import MeetingRepository
from app.repositories.user_repo import UserRepository
from app.schemas.meeting import (
    MeetingActionItemCreateRequest,
    MeetingActionItemResponse,
    MeetingActionItemUpdateRequest,
    MeetingAgentRunRequest,
    MeetingAgentRunResponse,
    MeetingCandidateMemoryResponse,
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
from app.services.meeting_agent_service import MeetingAgentService
from app.services.stream_service import meeting_stream_broker
from infra.database.session import get_session

_MENTION_DELIMITER_RE = re.compile(r"(?=$|[\s,.;:!?，。；：！？])")
_MEETING_AI_AGENT_ID = "ai_assistant"
_MEETING_AI_AGENT_NAME = "智能助手"
_MEETING_GENERAL_AGENT_ID = "general_agent"
_MEETING_GENERAL_AGENT_NAME = "总智能体"
_DEFAULT_PROJECT_ID = "default"
logger = logging.getLogger(__name__)


def _is_valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


def _normalize_name(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


class MeetingService:
    def __init__(self, session: AsyncSession, org_id: str, user_id: str):
        self._session = session
        self._org_id = org_id
        self._user_id = user_id
        self._repo = MeetingRepository(session)
        self._users = UserRepository(session)

    async def list_rooms(self, limit: int = 100) -> list[MeetingRoomResponse]:
        rooms = await self._repo.list_joined_rooms(self._org_id, self._user_id, limit=limit)
        return await self._serialize_rooms(rooms)

    async def create_room(self, title: str, password: str | None = None) -> MeetingRoomResponse:
        clean_title = title.strip() or "会议室"
        room = await self._repo.create_room(
            org_id=self._org_id,
            user_id=self._user_id,
            title=clean_title[:120],
            access_code=await self._generate_access_code(),
            password_hash=hash_password(password) if password else None,
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
    ) -> MeetingMessageResponse:
        await self._ensure_active_member(room_id)
        user = await self._users.get_by_id(self._org_id, self._user_id)
        username = user.username if user else self._user_id[-8:]
        clean_content = content.strip()
        if quote_message_id:
            quoted = await self._repo.get_message(self._org_id, room_id, quote_message_id)
            if not quoted:
                raise NotFoundError("quoted meeting message not found")
        mentions = await self._parse_mentions(clean_content, room_id)
        ai_mentioned = not mentions and self._contains_meeting_ai_mention(clean_content)
        general_agent_mentioned = not mentions and self._contains_general_agent_mention(clean_content)
        stored_mentions = list(mentions)
        if ai_mentioned:
            stored_mentions.append({"agent_id": _MEETING_AI_AGENT_ID, "agent_name": _MEETING_AI_AGENT_NAME})
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
        if ai_mentioned:
            asyncio.create_task(self._invoke_meeting_ai_reply(room_id=room_id))
        if general_agent_mentioned:
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

    async def add_agent_to_room(self, room_id: str, agent_id: str, role: str = "participant") -> MeetingRoomAgentResponse:
        await self._ensure_member(room_id)
        existing = await self._repo.get_agent(self._org_id, room_id, agent_id)
        if existing:
            raise ForbiddenError("agent is already in this meeting room")

        agent_name = await self._resolve_visible_agent_name(agent_id)
        row = await self._repo.add_agent(
            org_id=self._org_id,
            room_id=room_id,
            agent_id=agent_id,
            added_by=self._user_id,
            role=role,
        )
        return MeetingRoomAgentResponse(
            id=str(row.id),
            room_id=str(row.room_id),
            agent_id=str(row.agent_id),
            agent_name=agent_name,
            role=str(row.role),
            added_by=str(row.added_by),
        )

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
            results.append(
                MeetingRoomAgentResponse(
                    id=str(row.id),
                    room_id=str(row.room_id),
                    agent_id=agent_id,
                    agent_name=agent_name,
                    role=str(row.role),
                    added_by=str(row.added_by),
                )
            )
        return results

    async def list_room_members(self, room_id: str) -> list[MeetingRoomMemberResponse]:
        await self._ensure_member(room_id)
        rows = await self._repo.list_members(self._org_id, room_id)
        results: list[MeetingRoomMemberResponse] = []
        for row in rows:
            user_id = str(row.user_id)
            user = await self._users.get_by_id(self._org_id, user_id)
            results.append(
                MeetingRoomMemberResponse(
                    id=str(row.id),
                    room_id=str(row.room_id),
                    user_id=user_id,
                    username=user.username if user else user_id[-8:],
                    role=str(row.role),
                    joined_at=row.created_at,
                )
            )
        return results

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

    async def run_general_agent(
        self,
        room_id: str,
        request: MeetingAgentRunRequest,
    ) -> MeetingAgentRunResponse:
        await self._ensure_member(room_id)
        selected_subgraph = self._select_general_agent_subgraph(request.query, request.mode)
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
        await self._ensure_member(room_id)
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
        await self._ensure_member(room_id)

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
        await self._ensure_member(room_id)
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
        await self._publish_system_message(room_id, f"已新增行动项：{row.title}")
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
        await self._publish_system_message(str(row.room_id), f"行动项已完成：{row.title}")
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

    def _select_general_agent_subgraph(self, query: str, mode: str) -> str:
        if mode != "auto":
            return "action_items" if mode == "action_items" else mode
        normalized = query.lower()
        if any(word in normalized for word in ("风险", "预测", "下月", "下个月", "risk")):
            return "risk_forecast"
        if any(word in normalized for word in ("证据", "检测结果", "批次", "任务", "evidence")):
            return "evidence_query"
        if any(word in normalized for word in ("标准", "判定", "依据", "解释", "standard")):
            return "standard_explain"
        if any(word in normalized for word in ("记忆", "沉淀", "共享", "transfer", "memory")):
            return "memory_transfer"
        if any(word in normalized for word in ("行动项", "待办", "todo", "action")):
            return "action_items"
        return "meeting_summary"

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
        if selected_subgraph == "risk_forecast":
            return (
                "已路由到「风险预测」子图。\n"
                "第一版先基于会议上下文和已确认共享记忆给出讨论型预测建议：\n"
                "1. 优先关注会议中被反复提及的产品、批次和缺陷类型。\n"
                "2. 对缺少检测任务或结果来源的结论标记为待核验。\n"
                "3. 后续接入 inspection_tasks / inspection_results 后，可补充分数化风险排序。\n\n"
                f"本次查询：{query}\n"
                f"可用共享记忆：\n{source_lines or '- 暂无已确认共享记忆'}"
            )
        if selected_subgraph == "evidence_query":
            return (
                "已路由到「检测证据」子图。\n"
                "当前版本会先从会议上下文中定位产品、批次、任务 ID 等线索；真正的检测证据列表需要后续接入检测任务与结果表。\n\n"
                f"本次查询：{query}\n"
                f"会议线索：\n{self._bullet_recent(recent)}"
            )
        if selected_subgraph == "standard_explain":
            return (
                "已路由到「标准解释」子图。\n"
                "当前版本会把会议中的判定争议、标准名和缺陷描述整理为待解释问题；接入 RAG 标准条款后可返回具体引用依据。\n\n"
                f"本次查询：{query}\n"
                f"相关上下文：\n{self._bullet_recent(recent)}"
            )
        if selected_subgraph == "memory_transfer":
            return (
                "已路由到「记忆转移」子图。\n"
                "我已根据会议内容生成候选记忆，等待用户确认后才会发布为项目共享记忆；原始会议聊天不会跨会议共享。\n\n"
                f"候选依据：\n{self._bullet_recent(recent[-5:])}"
            )
        if selected_subgraph == "action_items":
            return (
                "已路由到「行动项」子图。\n"
                "建议把会议中的明确责任、截止时间和复核要求拆成行动项；右侧面板可以继续新增、更新和完成。\n\n"
                f"可提取线索：\n{self._bullet_recent(recent[-5:])}"
            )
        return (
            "已路由到「会议纪要」子图。\n"
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
                transfer_reason="总智能体从会议上下文提取候选记忆",
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
                status=str(room.status),
                member_count=counts.get(str(room.id), 0),
                agent_count=agent_counts.get(str(room.id), 0),
                last_message_at=room.last_message_at,
                created_at=room.created_at,
                updated_at=room.updated_at,
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
        aliases = {_MEETING_AI_AGENT_NAME, "AI 助手", "AI助手"}
        compact_name = _normalize_name(_MEETING_AI_AGENT_NAME)
        if compact_name:
            aliases.add(compact_name)

        for alias in aliases:
            pattern = re.compile(rf"@{re.escape(alias)}{_MENTION_DELIMITER_RE.pattern}", re.IGNORECASE)
            if pattern.search(content):
                return True
        return False

    def _contains_general_agent_mention(self, content: str) -> bool:
        aliases = {
            _MEETING_GENERAL_AGENT_NAME,
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

    async def _invoke_meeting_ai_reply(self, *, room_id: str) -> None:
        from app.services.meeting_ai_service import MeetingAiService

        try:
            async with get_session() as session:
                service = MeetingAiService(session, self._org_id, self._user_id)
                await service.ai_respond(room_id)
                await session.commit()
        except Exception:
            logger.exception("meeting ai mention invocation failed room_id=%s", room_id)

    async def _invoke_general_agent_reply(self, *, room_id: str, query: str) -> None:
        try:
            async with get_session() as session:
                service = MeetingService(session, self._org_id, self._user_id)
                await service.run_general_agent(
                    room_id,
                    MeetingAgentRunRequest(query=query, mode="auto"),
                )
                await session.commit()
        except Exception:
            logger.exception("meeting general agent invocation failed room_id=%s", room_id)
