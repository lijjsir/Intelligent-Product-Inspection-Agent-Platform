from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.meeting import MeetingMessage, MeetingRoom, MeetingRoomMember


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
    ) -> MeetingMessage:
        message = MeetingMessage(
            org_id=org_id,
            room_id=room_id,
            user_id=user_id,
            username=username,
            seq_no=await self.next_message_seq(room_id),
            content=content,
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

    async def touch_room(self, org_id: str, room_id: str) -> None:
        await self._session.execute(
            update(MeetingRoom)
            .where(
                MeetingRoom.org_id == org_id,
                MeetingRoom.id == room_id,
                MeetingRoom.deleted_at.is_(None),
            )
            .values(last_message_at=datetime.utcnow())
        )
