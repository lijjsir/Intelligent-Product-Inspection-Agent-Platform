from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime import utcnow
from app.models.meeting import MeetingAgentDefinition, MeetingMessage, MeetingRoom, MeetingRoomAgent, MeetingRoomMember


class MeetingRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create_room(
        self,
        *,
        org_id: str,
        user_id: str,
        title: str,
        access_code: str,
        password_hash: str | None,
    ) -> MeetingRoom:
        room = MeetingRoom(
            org_id=org_id,
            title=title,
            access_code=access_code,
            password_hash=password_hash,
            created_by=user_id,
            status="active",
        )
        self._session.add(room)
        await self._session.flush()
        await self.add_member(org_id=org_id, room_id=str(room.id), user_id=user_id, role="host")
        await self._session.refresh(room, attribute_names=["created_at", "updated_at"])
        return room

    async def get_room(self, org_id: str, room_id: str) -> MeetingRoom | None:
        result = await self._session.execute(
            select(MeetingRoom).where(
                MeetingRoom.org_id == org_id,
                MeetingRoom.id == room_id,
                MeetingRoom.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_room_by_code(self, org_id: str, access_code: str) -> MeetingRoom | None:
        result = await self._session.execute(
            select(MeetingRoom).where(
                MeetingRoom.org_id == org_id,
                MeetingRoom.access_code == access_code.upper(),
                MeetingRoom.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_joined_rooms(self, org_id: str, user_id: str, limit: int = 100) -> list[MeetingRoom]:
        result = await self._session.execute(
            select(MeetingRoom)
            .join(MeetingRoomMember, MeetingRoomMember.room_id == MeetingRoom.id)
            .where(
                MeetingRoom.org_id == org_id,
                MeetingRoomMember.org_id == org_id,
                MeetingRoomMember.user_id == user_id,
                MeetingRoom.deleted_at.is_(None),
                MeetingRoomMember.deleted_at.is_(None),
            )
            .order_by(MeetingRoom.last_message_at.desc(), MeetingRoom.updated_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_member(self, org_id: str, room_id: str, user_id: str) -> MeetingRoomMember | None:
        result = await self._session.execute(
            select(MeetingRoomMember).where(
                MeetingRoomMember.org_id == org_id,
                MeetingRoomMember.room_id == room_id,
                MeetingRoomMember.user_id == user_id,
                MeetingRoomMember.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def add_member(self, *, org_id: str, room_id: str, user_id: str, role: str = "member") -> MeetingRoomMember:
        existing = await self.get_member(org_id, room_id, user_id)
        if existing:
            return existing
        member = MeetingRoomMember(org_id=org_id, room_id=room_id, user_id=user_id, role=role)
        self._session.add(member)
        await self._session.flush()
        await self._session.refresh(member, attribute_names=["created_at", "updated_at"])
        return member

    async def count_members(self, org_id: str, room_ids: Sequence[str]) -> dict[str, int]:
        if not room_ids:
            return {}
        result = await self._session.execute(
            select(MeetingRoomMember.room_id, func.count(MeetingRoomMember.id))
            .where(
                MeetingRoomMember.org_id == org_id,
                MeetingRoomMember.room_id.in_(list(room_ids)),
                MeetingRoomMember.deleted_at.is_(None),
            )
            .group_by(MeetingRoomMember.room_id)
        )
        return {str(room_id): int(count) for room_id, count in result.all()}

    async def next_message_seq(self, room_id: str) -> int:
        max_seq = await self._session.scalar(
            select(func.max(MeetingMessage.seq_no)).where(MeetingMessage.room_id == room_id)
        )
        return int(max_seq or 0) + 1

    async def create_message(
        self,
        *,
        org_id: str,
        room_id: str,
        user_id: str,
        username: str,
        content: str,
        message_type: str = "user",
        agent_id: str | None = None,
        mentions: dict | None = None,
    ) -> MeetingMessage:
        message = MeetingMessage(
            org_id=org_id,
            room_id=room_id,
            user_id=user_id,
            username=username,
            seq_no=await self.next_message_seq(room_id),
            content=content,
            message_type=message_type,
            agent_id=agent_id,
            mentions=mentions,
        )
        self._session.add(message)
        await self._session.flush()
        await self._session.refresh(message, attribute_names=["created_at", "updated_at"])
        await self.touch_room(org_id, room_id)
        return message

    async def list_messages(
        self,
        *,
        org_id: str,
        room_id: str,
        after_seq: int = 0,
        limit: int = 200,
    ) -> list[MeetingMessage]:
        result = await self._session.execute(
            select(MeetingMessage)
            .where(
                MeetingMessage.org_id == org_id,
                MeetingMessage.room_id == room_id,
                MeetingMessage.seq_no > after_seq,
                MeetingMessage.deleted_at.is_(None),
            )
            .order_by(MeetingMessage.seq_no.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_recent_messages(
        self,
        *,
        org_id: str,
        room_id: str,
        limit: int = 50,
    ) -> list[MeetingMessage]:
        result = await self._session.execute(
            select(MeetingMessage)
            .where(
                MeetingMessage.org_id == org_id,
                MeetingMessage.room_id == room_id,
                MeetingMessage.deleted_at.is_(None),
            )
            .order_by(MeetingMessage.seq_no.desc())
            .limit(limit)
        )
        return list(reversed(list(result.scalars().all())))

    async def touch_room(self, org_id: str, room_id: str) -> None:
        await self._session.execute(
            update(MeetingRoom)
            .where(
                MeetingRoom.org_id == org_id,
                MeetingRoom.id == room_id,
                MeetingRoom.deleted_at.is_(None),
            )
            .values(last_message_at=utcnow())
        )

    # ── Agent management ──────────────────────────────────────────

    async def add_agent(self, *, org_id: str, room_id: str, agent_id: str, added_by: str, role: str = "participant") -> MeetingRoomAgent:
        row = MeetingRoomAgent(org_id=org_id, room_id=room_id, agent_id=agent_id, added_by=added_by, role=role)
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row, attribute_names=["created_at", "updated_at"])
        return row

    async def remove_agent(self, org_id: str, room_id: str, agent_id: str) -> bool:
        result = await self._session.execute(
            select(MeetingRoomAgent).where(
                MeetingRoomAgent.org_id == org_id,
                MeetingRoomAgent.room_id == room_id,
                MeetingRoomAgent.agent_id == agent_id,
                MeetingRoomAgent.deleted_at.is_(None),
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True

    async def get_agents(self, org_id: str, room_id: str) -> list[MeetingRoomAgent]:
        result = await self._session.execute(
            select(MeetingRoomAgent).where(
                MeetingRoomAgent.org_id == org_id,
                MeetingRoomAgent.room_id == room_id,
                MeetingRoomAgent.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def get_agent(self, org_id: str, room_id: str, agent_id: str) -> MeetingRoomAgent | None:
        result = await self._session.execute(
            select(MeetingRoomAgent).where(
                MeetingRoomAgent.org_id == org_id,
                MeetingRoomAgent.room_id == room_id,
                MeetingRoomAgent.agent_id == agent_id,
                MeetingRoomAgent.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def count_agents(self, org_id: str, room_ids: Sequence[str]) -> dict[str, int]:
        if not room_ids:
            return {}
        result = await self._session.execute(
            select(MeetingRoomAgent.room_id, func.count(MeetingRoomAgent.id))
            .where(
                MeetingRoomAgent.org_id == org_id,
                MeetingRoomAgent.room_id.in_(list(room_ids)),
                MeetingRoomAgent.deleted_at.is_(None),
            )
            .group_by(MeetingRoomAgent.room_id)
        )
        return {str(room_id): int(count) for room_id, count in result.all()}

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
        result = await self._session.execute(
            select(MeetingAgentDefinition).where(
                MeetingAgentDefinition.org_id == org_id,
                MeetingAgentDefinition.id == agent_def_id,
                MeetingAgentDefinition.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_visible_agent_definition(self, org_id: str, agent_def_id: str) -> MeetingAgentDefinition | None:
        system_org_id = "00000000-0000-0000-0000-000000000000"
        result = await self._session.execute(
            select(MeetingAgentDefinition).where(
                MeetingAgentDefinition.id == agent_def_id,
                or_(
                    MeetingAgentDefinition.org_id == org_id,
                    MeetingAgentDefinition.org_id == system_org_id,
                ),
                MeetingAgentDefinition.deleted_at.is_(None),
            )
        )
        rows = list(result.scalars().all())
        if not rows:
            return None
        for row in rows:
            if str(row.org_id) == org_id:
                return row
        return rows[0]

    async def list_active_agent_definitions(self, org_id: str) -> list[MeetingAgentDefinition]:
        system_org_id = "00000000-0000-0000-0000-000000000000"
        result = await self._session.execute(
            select(MeetingAgentDefinition).where(
                or_(
                    MeetingAgentDefinition.org_id == org_id,
                    MeetingAgentDefinition.org_id == system_org_id,
                ),
                MeetingAgentDefinition.is_active.is_(True),
                MeetingAgentDefinition.deleted_at.is_(None),
            ).order_by(MeetingAgentDefinition.name.asc())
        )
        return list(result.scalars().all())

    async def update_agent_definition(
        self, org_id: str, agent_def_id: str, **fields
    ) -> MeetingAgentDefinition | None:
        row = await self.get_agent_definition(org_id, agent_def_id)
        if row is None:
            return None
        for key, value in fields.items():
            if value is not None and hasattr(row, key):
                setattr(row, key, value)
        await self._session.flush()
        return row

    async def delete_agent_definition(self, org_id: str, agent_def_id: str) -> bool:
        row = await self.get_agent_definition(org_id, agent_def_id)
        if row is None:
            return False
        row.deleted_at = utcnow()
        await self._session.flush()
        return True

    # ── Admin ─────────────────────────────────────────────────────

    async def list_all_rooms(
        self, *, org_id: str, page: int = 1, size: int = 20, keyword: str | None = None, status: str | None = None
    ) -> tuple[list[MeetingRoom], int]:
        base = select(MeetingRoom).where(MeetingRoom.org_id == org_id, MeetingRoom.deleted_at.is_(None))
        if keyword:
            base = base.where(MeetingRoom.title.ilike(f"%{keyword}%"))
        if status:
            base = base.where(MeetingRoom.status == status)

        count_q = select(func.count()).select_from(base.subquery())
        total = (await self._session.execute(count_q)).scalar() or 0

        rows = await self._session.execute(
            base.order_by(MeetingRoom.created_at.desc()).offset((page - 1) * size).limit(size)
        )
        return list(rows.scalars().all()), int(total)

    async def delete_room_admin(self, org_id: str, room_id: str) -> bool:
        result = await self._session.execute(
            select(MeetingRoom).where(
                MeetingRoom.org_id == org_id,
                MeetingRoom.id == room_id,
                MeetingRoom.deleted_at.is_(None),
            )
        )
        room = result.scalar_one_or_none()
        if room is None:
            return False
        room.deleted_at = utcnow()
        await self._session.flush()
        return True

    async def count_messages(self, org_id: str, room_ids: Sequence[str]) -> dict[str, int]:
        if not room_ids:
            return {}
        result = await self._session.execute(
            select(MeetingMessage.room_id, func.count(MeetingMessage.id))
            .where(
                MeetingMessage.org_id == org_id,
                MeetingMessage.room_id.in_(list(room_ids)),
                MeetingMessage.deleted_at.is_(None),
            )
            .group_by(MeetingMessage.room_id)
        )
        return {str(room_id): int(count) for room_id, count in result.all()}
