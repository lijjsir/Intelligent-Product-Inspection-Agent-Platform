from __future__ import annotations

import asyncio
import re
import secrets
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.security import hash_password, verify_password
from app.repositories.meeting_repo import MeetingRepository
from app.repositories.user_repo import UserRepository
from app.schemas.meeting import (
    MeetingMessageResponse,
    MeetingRoomAgentResponse,
    MeetingRoomDetailResponse,
    MeetingRoomResponse,
)
from app.services.stream_service import meeting_stream_broker
from app.services.meeting_agent_service import MeetingAgentService

_MENTION_RE = re.compile(r"@(\S+?)(?:\s|$)")


def _is_valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


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
        if room.password_hash and not verify_password(password or "", room.password_hash):
            raise ForbiddenError("meeting password is invalid")
        await self._repo.add_member(org_id=self._org_id, room_id=str(room.id), user_id=self._user_id)
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

    async def send_message(self, room_id: str, content: str) -> MeetingMessageResponse:
        await self._ensure_member(room_id)
        user = await self._users.get_by_id(self._org_id, self._user_id)
        username = user.username if user else self._user_id[-8:]

        # Parse @mentions
        mentions = await self._parse_mentions(content, room_id)

        message = await self._repo.create_message(
            org_id=self._org_id,
            room_id=room_id,
            user_id=self._user_id,
            username=username,
            content=content.strip(),
            message_type="user",
            mentions=mentions if mentions else None,
        )

        response = MeetingMessageResponse.model_validate(message)

        # Publish to stream broker for real-time delivery
        await meeting_stream_broker.publish(room_id, {
            "event": "message_created",
            "room_id": room_id,
            "message": response.model_dump(),
        })

        # Trigger agent invocations in background for each valid mention
        agent_service = MeetingAgentService()
        if mentions:
            for m in mentions:
                asyncio.create_task(
                    agent_service.invoke_agent(
                        room_id=room_id,
                        agent_def_id=m["agent_id"],
                        agent_name=m["agent_name"],
                        message_id=str(message.id),
                        query=content.strip(),
                        org_id=self._org_id,
                        user_id=self._user_id,
                        username=username,
                    )
                )

        # Trigger autonomous participation check for all room agents
        asyncio.create_task(
            agent_service.check_autonomous_participation(
                room_id=room_id,
                org_id=self._org_id,
                user_id=self._user_id,
            )
        )

        return response

    # ── Agent management ──────────────────────────────────────────

    async def add_agent_to_room(self, room_id: str, agent_id: str, role: str = "participant") -> MeetingRoomAgentResponse:
        await self._ensure_member(room_id)

        existing = await self._repo.get_agent(self._org_id, room_id, agent_id)
        if existing:
            raise ForbiddenError("agent is already in this meeting room")

        agent_name = self._resolve_agent_name(agent_id)

        row = await self._repo.add_agent(
            org_id=self._org_id, room_id=room_id, agent_id=agent_id, added_by=self._user_id, role=role,
        )
        return MeetingRoomAgentResponse(
            id=str(row.id), room_id=str(row.room_id), agent_id=str(row.agent_id),
            agent_name=agent_name, role=str(row.role), added_by=str(row.added_by),
        )

    async def remove_agent_from_room(self, room_id: str, agent_id: str) -> None:
        await self._ensure_member(room_id)
        removed = await self._repo.remove_agent(self._org_id, room_id, agent_id)
        if not removed:
            raise NotFoundError("agent not found in this meeting room")

    async def list_room_agents(self, room_id: str) -> list[MeetingRoomAgentResponse]:
        await self._ensure_member(room_id)
        rows = await self._repo.get_agents(self._org_id, room_id)

        # Load agent definitions for name resolution (only valid UUIDs)
        agent_ids = [str(r.agent_id) for r in rows]
        from app.models.meeting import MeetingAgentDefinition
        valid_ids = [aid for aid in agent_ids if _is_valid_uuid(aid)]
        defs_by_id: dict[str, Any] = {}
        if valid_ids:
            result = await self._session.execute(
                select(MeetingAgentDefinition).where(
                    MeetingAgentDefinition.id.in_(valid_ids),
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

    async def delete_room(self, room_id: str) -> None:
        """Delete a meeting room — only the host (creator) can do this."""
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

    # ── Internal helpers ──────────────────────────────────────────

    async def _ensure_member(self, room_id: str) -> None:
        room = await self._repo.get_room(self._org_id, room_id)
        if not room:
            raise NotFoundError("meeting room not found")
        member = await self._repo.get_member(self._org_id, room_id, self._user_id)
        if not member:
            raise ForbiddenError("join the meeting room before sending messages")

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

    def _resolve_agent_name(self, agent_id: str) -> str:
        """Look up agent display name from topology catalog by subgraph_key."""
        from agent.topology_catalog import get_registered_subgraphs
        for item in get_registered_subgraphs():
            if item.get("subgraph_key") == agent_id:
                return item.get("name") or agent_id
        return agent_id

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

        if not room_agent_ids:
            return []

        # Only query with valid UUIDs (old agents may use topology subgraph_keys)
        valid_ids = [aid for aid in room_agent_ids if _is_valid_uuid(aid)]
        agent_defs: dict[str, Any] = {}
        if valid_ids:
            from app.models.meeting import MeetingAgentDefinition
            agent_defs_result = await self._session.execute(
                select(MeetingAgentDefinition).where(
                    MeetingAgentDefinition.id.in_(valid_ids),
                    MeetingAgentDefinition.deleted_at.is_(None),
                )
            )
            agent_defs = {str(ad.id): ad for ad in agent_defs_result.scalars().all()}

        mentions = []
        for name in raw_names:
            for agent_id in room_agent_ids:
                ad = agent_defs.get(agent_id)
                if ad and ad.name.lower() == name.lower():
                    mentions.append({"agent_id": agent_id, "agent_name": ad.name})
                    break
        return mentions
