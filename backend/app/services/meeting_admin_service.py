from __future__ import annotations

from app.core.exceptions import NotFoundError
from app.repositories.agent_ops_repo import AgentDefinitionRepository
from app.repositories.meeting_repo import MeetingRepository
from app.repositories.user_repo import UserRepository
from app.schemas.meeting import AdminMeetingRoomResponse, MeetingRoomAgentResponse, MeetingRoomDetailResponse, MeetingRoomResponse, MeetingMessageResponse


class MeetingAdminService:
    def __init__(self, session, org_id: str):
        self._session = session
        self._org_id = org_id
        self._repo = MeetingRepository(session)
        self._users = UserRepository(session)
        self._agent_repo = AgentDefinitionRepository(session, org_id)

    async def list_all_rooms(
        self, *, page: int = 1, size: int = 20, keyword: str | None = None, status: str | None = None
    ) -> tuple[list[AdminMeetingRoomResponse], int]:
        rooms, total = await self._repo.list_all_rooms(
            org_id=self._org_id, page=page, size=size, keyword=keyword, status=status
        )
        if not rooms:
            return [], total

        room_ids = [str(r.id) for r in rooms]
        member_counts = await self._repo.count_members(self._org_id, room_ids)
        agent_counts = await self._repo.count_agents(self._org_id, room_ids)
        message_counts = await self._repo.count_messages(self._org_id, room_ids)

        results = []
        for room in rooms:
            creator = await self._users.get_by_id(self._org_id, str(room.created_by))
            results.append(AdminMeetingRoomResponse(
                id=str(room.id),
                org_id=str(room.org_id),
                title=str(room.title),
                access_code=str(room.access_code),
                created_by=str(room.created_by),
                status=str(room.status),
                member_count=member_counts.get(str(room.id), 0),
                agent_count=agent_counts.get(str(room.id), 0),
                message_count=message_counts.get(str(room.id), 0),
                created_by_username=creator.username if creator else "",
                last_message_at=room.last_message_at,
                created_at=room.created_at,
                updated_at=room.updated_at,
            ))
        return results, total

    async def get_room_detail(self, room_id: str) -> MeetingRoomDetailResponse:
        room = await self._repo.get_room(self._org_id, room_id)
        if not room:
            raise NotFoundError("meeting room not found")

        counts = await self._repo.count_members(self._org_id, [room_id])
        agent_counts = await self._repo.count_agents(self._org_id, [room_id])
        agents = await self._repo.get_agents(self._org_id, room_id)

        agent_responses = []
        for a in agents:
            name = a.agent_id
            try:
                agent_def = await self._agent_repo.get(a.agent_id)
                if agent_def:
                    name = agent_def.name
            except Exception:
                pass
            agent_responses.append(MeetingRoomAgentResponse(
                id=str(a.id),
                room_id=str(a.room_id),
                agent_id=str(a.agent_id),
                agent_name=name,
                role=str(a.role),
                added_by=str(a.added_by),
            ))

        return MeetingRoomDetailResponse(
            id=str(room.id),
            org_id=str(room.org_id),
            title=str(room.title),
            access_code=str(room.access_code),
            created_by=str(room.created_by),
            status=str(room.status),
            member_count=counts.get(room_id, 0),
            agent_count=agent_counts.get(room_id, 0),
            agents=agent_responses,
            last_message_at=room.last_message_at,
            created_at=room.created_at,
            updated_at=room.updated_at,
        )

    async def archive_room(self, room_id: str) -> None:
        deleted = await self._repo.delete_room_admin(self._org_id, room_id)
        if not deleted:
            raise NotFoundError("meeting room not found")

    async def remove_member(self, room_id: str, user_id: str) -> None:
        member = await self._repo.get_member(self._org_id, room_id, user_id)
        if not member:
            raise NotFoundError("member not found in meeting room")
        from app.core.datetime import utcnow
        member.deleted_at = utcnow()
        await self._session.flush()
