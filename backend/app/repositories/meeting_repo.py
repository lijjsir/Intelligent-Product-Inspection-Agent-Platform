from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime import utcnow
from app.models.meeting import (
    MeetingActionItem,
    MeetingAgentQueryAudit,
    MeetingAgentDefinition,
    MeetingConflictEvent,
    MeetingMessage,
    MeetingRoom,
    MeetingRoomAgent,
    MeetingRoomMember,
    MemoryScopeBinding,
    MemoryTransferLog,
)
from app.models.memory import MemoryItem


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
        visibility: str = "private",
        allowed_data_domains: list[str] | None = None,
        memory_policy: dict | None = None,
        audit_policy: dict | None = None,
    ) -> MeetingRoom:
        room = MeetingRoom(
            org_id=org_id,
            title=title,
            access_code=access_code,
            password_hash=password_hash,
            created_by=user_id,
            status="active",
            visibility=visibility,
            allowed_data_domains=allowed_data_domains,
            memory_policy=memory_policy,
            audit_policy=audit_policy,
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

    async def update_room(
        self,
        org_id: str,
        room_id: str,
        *,
        title: str | None = None,
        status: str | None = None,
        visibility: str | None = None,
        allowed_data_domains: list[str] | None = None,
        memory_policy: dict | None = None,
        audit_policy: dict | None = None,
    ) -> MeetingRoom | None:
        room = await self.get_room(org_id, room_id)
        if room is None:
            return None
        if title is not None:
            room.title = title
        if status is not None:
            room.status = status
        if visibility is not None:
            room.visibility = visibility
        if allowed_data_domains is not None:
            room.allowed_data_domains = allowed_data_domains
        if memory_policy is not None:
            room.memory_policy = memory_policy
        if audit_policy is not None:
            room.audit_policy = audit_policy
        await self._session.flush()
        await self._session.refresh(room, attribute_names=["created_at", "updated_at"])
        return room

    async def list_joined_rooms(
        self,
        org_id: str,
        user_id: str,
        limit: int = 100,
    ) -> list[MeetingRoom]:
        conditions = [
            MeetingRoom.org_id == org_id,
            MeetingRoomMember.org_id == org_id,
            MeetingRoomMember.user_id == user_id,
            MeetingRoom.deleted_at.is_(None),
            MeetingRoomMember.deleted_at.is_(None),
        ]
        result = await self._session.execute(
            select(MeetingRoom)
            .join(MeetingRoomMember, MeetingRoomMember.room_id == MeetingRoom.id)
            .where(*conditions)
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

    async def list_members(self, org_id: str, room_id: str) -> list[MeetingRoomMember]:
        result = await self._session.execute(
            select(MeetingRoomMember)
            .where(
                MeetingRoomMember.org_id == org_id,
                MeetingRoomMember.room_id == room_id,
                MeetingRoomMember.deleted_at.is_(None),
            )
            .order_by(MeetingRoomMember.created_at.asc())
        )
        return list(result.scalars().all())

    async def update_member_role(
        self,
        org_id: str,
        room_id: str,
        user_id: str,
        role: str,
    ) -> MeetingRoomMember | None:
        member = await self.get_member(org_id, room_id, user_id)
        if member is None:
            return None
        member.role = role
        await self._session.flush()
        await self._session.refresh(member, attribute_names=["created_at", "updated_at"])
        return member

    async def remove_member(self, org_id: str, room_id: str, user_id: str) -> bool:
        member = await self.get_member(org_id, room_id, user_id)
        if member is None:
            return False
        member.deleted_at = utcnow()
        await self._session.flush()
        return True

    async def _lock_room_for_message_seq(self, *, org_id: str, room_id: str) -> None:
        await self._session.execute(
            select(MeetingRoom.id)
            .where(
                MeetingRoom.org_id == org_id,
                MeetingRoom.id == room_id,
                MeetingRoom.deleted_at.is_(None),
            )
            .with_for_update()
        )

    async def next_message_seq(self, *, org_id: str, room_id: str) -> int:
        await self._lock_room_for_message_seq(org_id=org_id, room_id=room_id)
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
        quote_message_id: str | None = None,
        metadata_json: dict | None = None,
        private_recipient_user_id: str | None = None,
        message_id: str | None = None,
    ) -> MeetingMessage:
        next_metadata = dict(metadata_json or {})
        if private_recipient_user_id:
            next_metadata["private_recipient_user_id"] = private_recipient_user_id
        message = MeetingMessage(
            **({"id": message_id} if message_id else {}),
            org_id=org_id,
            room_id=room_id,
            user_id=user_id,
            username=username,
            seq_no=await self.next_message_seq(org_id=org_id, room_id=room_id),
            content=content,
            message_type=message_type,
            agent_id=agent_id,
            mentions=mentions,
            quote_message_id=quote_message_id,
            metadata_json=next_metadata or None,
        )
        self._session.add(message)
        await self._session.flush()
        await self._session.refresh(message, attribute_names=["created_at", "updated_at"])
        await self.touch_room(org_id, room_id)
        return self.expose_private_recipient(message)

    @staticmethod
    def expose_private_recipient(message: MeetingMessage) -> MeetingMessage:
        metadata = message.metadata_json or {}
        recipient = metadata.get("private_recipient_user_id")
        if isinstance(recipient, str) and recipient.strip():
            setattr(message, "private_recipient_user_id", recipient.strip())
        else:
            setattr(message, "private_recipient_user_id", None)
        return message

    async def get_message(self, org_id: str, room_id: str, message_id: str) -> MeetingMessage | None:
        result = await self._session.execute(
            select(MeetingMessage).where(
                MeetingMessage.org_id == org_id,
                MeetingMessage.room_id == room_id,
                MeetingMessage.id == message_id,
                MeetingMessage.deleted_at.is_(None),
            )
        )
        message = result.scalar_one_or_none()
        return self.expose_private_recipient(message) if message else None

    async def update_message_content(
        self,
        *,
        org_id: str,
        room_id: str,
        message_id: str,
        content: str,
        metadata_json: dict | None = None,
    ) -> MeetingMessage | None:
        message = await self.get_message(org_id, room_id, message_id)
        if not message:
            return None
        message.content = content
        message.metadata_json = metadata_json
        await self._session.flush()
        await self._session.refresh(message, attribute_names=["updated_at"])
        await self.touch_room(org_id, room_id)
        return self.expose_private_recipient(message)

    async def list_messages(
        self,
        *,
        org_id: str,
        room_id: str,
        after_seq: int = 0,
        limit: int = 200,
        visible_user_id: str | None = None,
    ) -> list[MeetingMessage]:
        visibility_clause = self._message_visibility_clause(visible_user_id)
        if visible_user_id is None:
            visibility_clause = and_(
                self._message_visibility_expr() != "private",
                self._private_recipient_expr().is_(None),
                MeetingMessage.message_type.notin_(["agent", "agent_streaming"]),
            )
        result = await self._session.execute(
            select(MeetingMessage)
            .where(
                MeetingMessage.org_id == org_id,
                MeetingMessage.room_id == room_id,
                MeetingMessage.seq_no > after_seq,
                MeetingMessage.deleted_at.is_(None),
                visibility_clause,
            )
            .order_by(MeetingMessage.seq_no.asc())
            .limit(limit)
        )
        return [self.expose_private_recipient(message) for message in result.scalars().all()]

    async def list_recent_messages(
        self,
        *,
        org_id: str,
        room_id: str,
        limit: int = 50,
        visible_user_id: str | None = None,
    ) -> list[MeetingMessage]:
        visibility_clause = self._message_visibility_clause(visible_user_id)
        if visible_user_id is None:
            visibility_clause = and_(
                self._message_visibility_expr() != "private",
                self._private_recipient_expr().is_(None),
                MeetingMessage.message_type.notin_(["agent", "agent_streaming"]),
            )
        result = await self._session.execute(
            select(MeetingMessage)
            .where(
                MeetingMessage.org_id == org_id,
                MeetingMessage.room_id == room_id,
                MeetingMessage.deleted_at.is_(None),
                visibility_clause,
            )
            .order_by(MeetingMessage.seq_no.desc())
            .limit(limit)
        )
        return [self.expose_private_recipient(message) for message in reversed(list(result.scalars().all()))]

    @staticmethod
    def _private_recipient_expr():
        return func.json_unquote(func.json_extract(MeetingMessage.metadata_json, "$.private_recipient_user_id"))

    @staticmethod
    def _message_visibility_expr():
        return func.coalesce(
            func.json_unquote(func.json_extract(MeetingMessage.metadata_json, "$.visibility")),
            "room",
        )

    @staticmethod
    def _audience_scope_id_expr():
        return func.json_unquote(func.json_extract(MeetingMessage.metadata_json, "$.audience_scope_id"))

    @classmethod
    def _message_visibility_clause(cls, visible_user_id: str | None):
        visibility_expr = cls._message_visibility_expr()
        private_recipient_expr = cls._private_recipient_expr()
        public_clause = and_(
            visibility_expr != "private",
            private_recipient_expr.is_(None),
        )
        if not visible_user_id:
            return and_(
                public_clause,
                MeetingMessage.message_type.notin_(["agent", "agent_streaming"]),
            )
        return or_(
            public_clause,
            MeetingMessage.user_id == visible_user_id,
            private_recipient_expr == visible_user_id,
            and_(
                visibility_expr == "private",
                cls._audience_scope_id_expr() == visible_user_id,
            ),
        )

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

    async def add_agent(
        self,
        *,
        org_id: str,
        room_id: str,
        agent_id: str,
        added_by: str,
        role: str = "participant",
        allowed_domains: list[str] | None = None,
        allowed_tools: list[str] | None = None,
    ) -> MeetingRoomAgent:
        row = MeetingRoomAgent(
            org_id=org_id,
            room_id=room_id,
            agent_id=agent_id,
            added_by=added_by,
            role=role,
            allowed_domains=allowed_domains,
            allowed_tools=allowed_tools,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row, attribute_names=["created_at", "updated_at"])
        return row

    async def create_agent_query_audit(
        self,
        *,
        org_id: str,
        room_id: str,
        user_id: str,
        agent_id: str,
        question: str,
        intent: str | None,
        requested_domains: list[str],
        allowed_domains: list[str],
        denied_domains: list[str],
        tool_calls: list[dict] | None = None,
        source_refs: list[dict] | None = None,
        redacted_fields: list[str] | None = None,
        decision: str = "allowed",
        response_visibility: str | None = None,
        redaction_level: str | None = None,
        denied_reasons: dict | None = None,
        conflict_ref_id: str | None = None,
    ) -> MeetingAgentQueryAudit:
        row = MeetingAgentQueryAudit(
            org_id=org_id,
            room_id=room_id,
            user_id=user_id,
            agent_id=agent_id,
            question=question,
            intent=intent,
            requested_domains=requested_domains,
            allowed_domains=allowed_domains,
            denied_domains=denied_domains,
            tool_calls=tool_calls or [],
            source_refs=source_refs or [],
            redacted_fields=redacted_fields or [],
            decision=decision,
            response_visibility=response_visibility,
            redaction_level=redaction_level,
            denied_reasons=denied_reasons or {},
            conflict_ref_id=conflict_ref_id,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row, attribute_names=["created_at", "updated_at"])
        return row

    async def list_agent_query_audits(
        self,
        *,
        org_id: str,
        room_id: str,
        limit: int = 50,
    ) -> list[MeetingAgentQueryAudit]:
        result = await self._session.execute(
            select(MeetingAgentQueryAudit)
            .where(
                MeetingAgentQueryAudit.org_id == org_id,
                MeetingAgentQueryAudit.room_id == room_id,
                MeetingAgentQueryAudit.deleted_at.is_(None),
            )
            .order_by(MeetingAgentQueryAudit.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def create_conflict_event(
        self,
        *,
        org_id: str,
        room_id: str,
        conflict_type: str,
        resource_key: str,
        initiator_user_id: str,
        workflow_run_id: str | None = None,
        related_message_ids: list[str] | None = None,
        candidate_actions: list[dict] | None = None,
        metadata_json: dict | None = None,
        status: str = "pending",
    ) -> MeetingConflictEvent:
        row = MeetingConflictEvent(
            org_id=org_id,
            room_id=room_id,
            conflict_type=conflict_type,
            resource_key=resource_key,
            status=status,
            initiator_user_id=initiator_user_id,
            workflow_run_id=workflow_run_id,
            related_message_ids=related_message_ids or [],
            candidate_actions=candidate_actions or [],
            metadata_json=metadata_json or {},
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row, attribute_names=["created_at", "updated_at"])
        return row

    async def list_conflict_events(
        self,
        *,
        org_id: str,
        room_id: str,
        statuses: Sequence[str] | None = None,
        limit: int = 50,
    ) -> list[MeetingConflictEvent]:
        stmt = (
            select(MeetingConflictEvent)
            .where(
                MeetingConflictEvent.org_id == org_id,
                MeetingConflictEvent.room_id == room_id,
                MeetingConflictEvent.deleted_at.is_(None),
            )
            .order_by(MeetingConflictEvent.created_at.desc())
            .limit(limit)
        )
        if statuses:
            stmt = stmt.where(MeetingConflictEvent.status.in_(list(statuses)))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_conflict_event(self, org_id: str, conflict_id: str) -> MeetingConflictEvent | None:
        result = await self._session.execute(
            select(MeetingConflictEvent).where(
                MeetingConflictEvent.org_id == org_id,
                MeetingConflictEvent.id == conflict_id,
                MeetingConflictEvent.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def resolve_conflict_event(
        self,
        *,
        org_id: str,
        conflict_id: str,
        selected_action: str,
        resolved_by: str,
        status: str = "resolved",
    ) -> MeetingConflictEvent | None:
        row = await self.get_conflict_event(org_id, conflict_id)
        if row is None:
            return None
        row.selected_action = selected_action
        row.resolved_by = resolved_by
        row.resolved_at = utcnow()
        row.status = status
        await self._session.flush()
        await self._session.refresh(row, attribute_names=["updated_at"])
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

    # ── Meeting memory bindings ─────────────────────────────────────────

    async def create_memory_item(self, item: MemoryItem) -> MemoryItem:
        self._session.add(item)
        await self._session.flush()
        await self._session.refresh(item, attribute_names=["created_at", "updated_at"])
        return item

    async def get_memory_item(self, org_id: str, memory_id: str) -> MemoryItem | None:
        result = await self._session.execute(
            select(MemoryItem).where(
                MemoryItem.org_id == org_id,
                MemoryItem.memory_id == memory_id,
                MemoryItem.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def create_memory_scope_binding(
        self,
        *,
        org_id: str,
        memory_id: str,
        scope_type: str,
        scope_id: str,
        permission: str,
        created_by: str,
    ) -> MemoryScopeBinding:
        binding = MemoryScopeBinding(
            org_id=org_id,
            memory_id=memory_id,
            scope_type=scope_type,
            scope_id=scope_id,
            permission=permission,
            created_by=created_by,
        )
        self._session.add(binding)
        await self._session.flush()
        return binding

    async def get_memory_scope_binding(
        self,
        *,
        org_id: str,
        memory_id: str,
        scope_type: str,
        scope_id: str,
    ) -> MemoryScopeBinding | None:
        result = await self._session.execute(
            select(MemoryScopeBinding).where(
                MemoryScopeBinding.org_id == org_id,
                MemoryScopeBinding.memory_id == memory_id,
                MemoryScopeBinding.scope_type == scope_type,
                MemoryScopeBinding.scope_id == scope_id,
                MemoryScopeBinding.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def create_memory_transfer_log(
        self,
        *,
        org_id: str,
        memory_id: str,
        from_scope_type: str,
        from_scope_id: str,
        to_scope_type: str,
        to_scope_id: str,
        transfer_reason: str | None,
        status: str,
        operator_id: str,
    ) -> MemoryTransferLog:
        row = MemoryTransferLog(
            org_id=org_id,
            memory_id=memory_id,
            from_scope_type=from_scope_type,
            from_scope_id=from_scope_id,
            to_scope_type=to_scope_type,
            to_scope_id=to_scope_id,
            transfer_reason=transfer_reason,
            status=status,
            operator_id=operator_id,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row, attribute_names=["created_at", "updated_at"])
        return row

    async def get_memory_transfer_log(self, org_id: str, transfer_id: str) -> MemoryTransferLog | None:
        result = await self._session.execute(
            select(MemoryTransferLog).where(
                MemoryTransferLog.org_id == org_id,
                MemoryTransferLog.id == transfer_id,
                MemoryTransferLog.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_pending_memory_transfer_logs(
        self,
        *,
        org_id: str,
        target_room_ids: Sequence[str] | None = None,
        limit: int = 100,
    ) -> list[MemoryTransferLog]:
        stmt = (
            select(MemoryTransferLog)
            .where(
                MemoryTransferLog.org_id == org_id,
                MemoryTransferLog.status == "pending_approval",
                MemoryTransferLog.deleted_at.is_(None),
            )
            .order_by(MemoryTransferLog.created_at.desc())
            .limit(limit)
        )
        if target_room_ids:
            room_ids = [str(item) for item in target_room_ids]
            stmt = stmt.where(
                or_(
                    and_(
                        MemoryTransferLog.from_scope_type == "meeting_room",
                        MemoryTransferLog.from_scope_id.in_(room_ids),
                    ),
                    and_(
                        MemoryTransferLog.to_scope_type == "meeting_room",
                        MemoryTransferLog.to_scope_id.in_(room_ids),
                    ),
                )
            )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update_memory_transfer_log_status(
        self,
        *,
        org_id: str,
        transfer_id: str,
        status: str,
        operator_id: str,
    ) -> MemoryTransferLog | None:
        row = await self.get_memory_transfer_log(org_id, transfer_id)
        if row is None:
            return None
        row.status = status
        row.operator_id = operator_id
        await self._session.flush()
        await self._session.refresh(row, attribute_names=["updated_at"])
        return row

    async def replace_memory_tags(
        self,
        *,
        org_id: str,
        memory_id: str,
        tags: list[dict[str, str]],
    ) -> list[MemoryTag]:
        result = await self._session.execute(
            select(MemoryTag).where(
                MemoryTag.org_id == org_id,
                MemoryTag.memory_id == memory_id,
            )
        )
        for row in result.scalars().all():
            await self._session.delete(row)
        created: list[MemoryTag] = []
        seen: set[tuple[str, str]] = set()
        for tag in tags:
            tag_type = str(tag.get("tag_type") or "").strip()
            tag_value = str(tag.get("tag_value") or "").strip()
            if not tag_type or not tag_value:
                continue
            key = (tag_type, tag_value)
            if key in seen:
                continue
            seen.add(key)
            row = MemoryTag(
                org_id=org_id,
                memory_id=memory_id,
                tag_type=tag_type[:32],
                tag_value=tag_value[:128],
            )
            self._session.add(row)
            created.append(row)
        await self._session.flush()
        return created

    async def list_memory_items_for_room(
        self,
        *,
        org_id: str,
        room_id: str,
        business_context: dict | None = None,
        include_confirmed: bool = True,
        statuses: Sequence[str] | None = None,
        limit: int = 50,
    ) -> list[MemoryItem]:
        room_binding_filter = exists(
            select(1).where(
                MemoryScopeBinding.org_id == MemoryItem.org_id,
                MemoryScopeBinding.memory_id == MemoryItem.memory_id,
                MemoryScopeBinding.deleted_at.is_(None),
                MemoryScopeBinding.permission.in_(["read", "write", "transfer", "confirm"]),
                MemoryScopeBinding.scope_type == "meeting_room",
                MemoryScopeBinding.scope_id == room_id,
            )
        )
        stmt = (
            select(MemoryItem)
            .where(
                MemoryItem.org_id == org_id,
                MemoryItem.deleted_at.is_(None),
                room_binding_filter,
            )
            .order_by(MemoryItem.updated_at.desc())
            .limit(limit)
        )
        if statuses:
            stmt = stmt.where(MemoryItem.status.in_(list(statuses)))
        if not include_confirmed:
            stmt = stmt.where(MemoryItem.status.notin_(["active", "confirmed"]))
        result = await self._session.execute(stmt)
        seen: set[str] = set()
        items: list[MemoryItem] = []
        for item in result.scalars().all():
            memory_id = str(item.memory_id)
            if memory_id in seen:
                continue
            seen.add(memory_id)
            items.append(item)
        return items

    async def list_memory_items_for_scopes(
        self,
        *,
        org_id: str,
        scope_pairs: Sequence[tuple[str, str]],
        statuses: Sequence[str] | None = None,
        limit: int = 50,
    ) -> list[MemoryItem]:
        normalized_pairs = [
            (str(scope_type or "").strip(), str(scope_id or "").strip())
            for scope_type, scope_id in scope_pairs
            if str(scope_type or "").strip() and str(scope_id or "").strip()
        ]
        if not normalized_pairs:
            return []
        scope_filters = [
            and_(
                MemoryScopeBinding.scope_type == scope_type,
                MemoryScopeBinding.scope_id == scope_id,
            )
            for scope_type, scope_id in normalized_pairs
        ]
        stmt = (
            select(MemoryItem)
            .where(
                MemoryItem.org_id == org_id,
                MemoryItem.deleted_at.is_(None),
                exists(
                    select(1).where(
                        MemoryScopeBinding.org_id == MemoryItem.org_id,
                        MemoryScopeBinding.memory_id == MemoryItem.memory_id,
                        MemoryScopeBinding.deleted_at.is_(None),
                        MemoryScopeBinding.permission.in_(["read", "write", "transfer", "confirm"]),
                        or_(*scope_filters),
                    )
                ),
            )
            .order_by(MemoryItem.updated_at.desc())
            .limit(limit)
        )
        if statuses:
            stmt = stmt.where(MemoryItem.status.in_(list(statuses)))
        result = await self._session.execute(stmt)
        matched_by_memory_id: dict[str, tuple[str, str]] = {}
        rows = result.scalars().all()
        memory_ids = [str(item.memory_id) for item in rows]
        if memory_ids:
            binding_result = await self._session.execute(
                select(
                    MemoryScopeBinding.memory_id,
                    MemoryScopeBinding.scope_type,
                    MemoryScopeBinding.scope_id,
                ).where(
                    MemoryScopeBinding.org_id == org_id,
                    MemoryScopeBinding.memory_id.in_(memory_ids),
                    MemoryScopeBinding.deleted_at.is_(None),
                    MemoryScopeBinding.permission.in_(["read", "write", "transfer", "confirm"]),
                    or_(*scope_filters),
                )
            )
            scope_priority = {
                (scope_type, scope_id): index
                for index, (scope_type, scope_id) in enumerate(normalized_pairs)
            }
            for memory_id, scope_type, scope_id in binding_result.all():
                key = str(memory_id)
                candidate = (str(scope_type or ""), str(scope_id or ""))
                current = matched_by_memory_id.get(key)
                if current is None or scope_priority.get(candidate, 9999) < scope_priority.get(current, 9999):
                    matched_by_memory_id[key] = candidate
        seen: set[str] = set()
        items: list[MemoryItem] = []
        for item in rows:
            memory_id = str(item.memory_id)
            if memory_id in seen:
                continue
            seen.add(memory_id)
            matched_scope_type, matched_scope_id = matched_by_memory_id.get(memory_id, ("", ""))
            setattr(item, "_matched_scope_type", str(matched_scope_type or ""))
            setattr(item, "_matched_scope_id", str(matched_scope_id or ""))
            items.append(item)
        return items

    async def update_memory_item(
        self,
        *,
        org_id: str,
        memory_id: str,
        status: str | None = None,
        content_summary: str | None = None,
        content_json: dict | None = None,
        scope_json: dict | None = None,
    ) -> MemoryItem | None:
        item = await self.get_memory_item(org_id, memory_id)
        if item is None:
            return None
        if status is not None:
            item.status = status
        if content_summary is not None:
            item.content_summary = content_summary
        if content_json is not None:
            item.content_json = content_json
        if scope_json is not None:
            item.scope_json = scope_json
        await self._session.flush()
        await self._session.refresh(item, attribute_names=["created_at", "updated_at"])
        return item

    # ── Meeting action items ───────────────────────────────────────────

    async def create_action_item(
        self,
        *,
        org_id: str,
        room_id: str,
        title: str,
        description: str | None,
        owner_id: str | None,
        due_at: datetime | None,
        source_message_id: str | None,
        created_by: str,
    ) -> MeetingActionItem:
        row = MeetingActionItem(
            org_id=org_id,
            room_id=room_id,
            title=title,
            description=description,
            owner_id=owner_id,
            due_at=due_at,
            source_message_id=source_message_id,
            created_by=created_by,
            status="open",
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row, attribute_names=["created_at", "updated_at"])
        return row

    async def list_action_items(self, org_id: str, room_id: str) -> list[MeetingActionItem]:
        result = await self._session.execute(
            select(MeetingActionItem)
            .where(
                MeetingActionItem.org_id == org_id,
                MeetingActionItem.room_id == room_id,
                MeetingActionItem.deleted_at.is_(None),
            )
            .order_by(MeetingActionItem.status.asc(), MeetingActionItem.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_action_item(self, org_id: str, action_item_id: str) -> MeetingActionItem | None:
        result = await self._session.execute(
            select(MeetingActionItem).where(
                MeetingActionItem.org_id == org_id,
                MeetingActionItem.id == action_item_id,
                MeetingActionItem.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def update_action_item(self, org_id: str, action_item_id: str, **fields) -> MeetingActionItem | None:
        row = await self.get_action_item(org_id, action_item_id)
        if row is None:
            return None
        for key, value in fields.items():
            if value is not None and hasattr(row, key):
                setattr(row, key, value)
        await self._session.flush()
        await self._session.refresh(row, attribute_names=["created_at", "updated_at"])
        return row
