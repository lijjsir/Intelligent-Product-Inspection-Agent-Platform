from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from app.core.ids import uuid7
from app.repositories.meeting_repo import MeetingRepository
from agent.adapters.factory import AgentAdapterFactory
from app.services.stream_service import meeting_stream_broker
from infra.database.session import get_session

logger = logging.getLogger(__name__)

# Track last agent message time per (room_id, agent_def_id) for cooldown
_last_agent_message: dict[tuple[str, str], datetime] = {}


class MeetingAgentService:
    def __init__(self) -> None:
        self._factory = AgentAdapterFactory()

    async def invoke_agent(
        self,
        *,
        room_id: str,
        agent_def_id: str,
        agent_name: str,
        message_id: str,
        query: str,
        org_id: str,
        user_id: str,
        username: str,
    ) -> None:
        """Called when a user @mentions an agent in a message."""
        workflow_run_id = str(uuid7())
        agent_message_id = str(uuid7())

        async def emit(event: dict[str, Any]) -> None:
            event.setdefault("ts", datetime.utcnow().isoformat())
            await meeting_stream_broker.publish(room_id, event)

        try:
            async with get_session() as session:
                repo = MeetingRepository(session)
                agent_def = await repo.get_agent_definition(org_id, agent_def_id)
                if not agent_def:
                    logger.warning("agent definition not found: %s", agent_def_id)
                    return

                context_msgs = await repo.list_messages(
                    org_id=org_id, room_id=room_id, after_seq=0, limit=20
                )
                context_dicts = [
                    {
                        "role": msg.message_type,
                        "username": msg.username,
                        "content": msg.content,
                    }
                    for msg in context_msgs
                ]

                adapter = self._factory.get_for_agent(agent_def)

                await emit({
                    "event": "agent_run_started",
                    "room_id": room_id,
                    "message_id": agent_message_id,
                    "agent_id": agent_def_id,
                    "agent_name": agent_name,
                    "workflow_run_id": workflow_run_id,
                })

                full_content = await adapter.invoke(
                    room_id=room_id,
                    agent_def=agent_def,
                    query=query,
                    context_messages=context_dicts,
                    emit=emit,
                )

                await repo.create_message(
                    org_id=org_id,
                    room_id=room_id,
                    user_id=user_id,
                    username=agent_name,
                    content=full_content,
                    message_type="agent",
                    agent_id=agent_def_id,
                )
                await session.commit()

            _last_agent_message[(room_id, agent_def_id)] = datetime.utcnow()

            await emit({
                "event": "message_final",
                "room_id": room_id,
                "message_id": agent_message_id,
                "agent_id": agent_def_id,
                "agent_name": agent_name,
                "workflow_run_id": workflow_run_id,
                "content": full_content,
            })

        except Exception as exc:
            logger.exception(
                "meeting agent invocation failed room_id=%s agent_id=%s workflow_run_id=%s",
                room_id, agent_def_id, workflow_run_id,
            )
            error_content = f"[Agent {agent_name}] 响应失败: {exc}"
            async with get_session() as session:
                repo = MeetingRepository(session)
                await repo.create_message(
                    org_id=org_id,
                    room_id=room_id,
                    user_id=user_id,
                    username=agent_name,
                    content=error_content,
                    message_type="agent",
                    agent_id=agent_def_id,
                )
                await session.commit()

            await emit({
                "event": "agent_run_failed",
                "room_id": room_id,
                "message_id": agent_message_id,
                "agent_id": agent_def_id,
                "agent_name": agent_name,
                "workflow_run_id": workflow_run_id,
                "error": str(exc),
            })

    async def check_autonomous_participation(
        self,
        *,
        room_id: str,
        org_id: str,
        user_id: str,
    ) -> None:
        """Check all agents in the room for autonomous participation eligibility."""
        async with get_session() as session:
            repo = MeetingRepository(session)

            room_agents = await repo.get_agents(org_id, room_id)
            if not room_agents:
                return

            recent_msgs = await repo.list_messages(
                org_id=org_id, room_id=room_id, after_seq=0, limit=30
            )
            recent_content = " ".join(m.content for m in recent_msgs[-10:])
            recent_dicts = [
                {
                    "role": m.message_type,
                    "username": m.username,
                    "content": m.content,
                }
                for m in recent_msgs[-20:]
            ]

            for ra in room_agents:
                agent_def = await repo.get_agent_definition(org_id, ra.agent_id)
                if not agent_def or not agent_def.is_active:
                    continue

                adapter = self._factory.get_for_agent(agent_def)

                last_time = _last_agent_message.get((room_id, ra.agent_id))
                seconds_since = (
                    (datetime.utcnow() - last_time).total_seconds() if last_time else 999999
                )
                msg_count_since = (
                    sum(
                        1 for m in recent_msgs
                        if last_time and m.created_at and m.created_at > last_time
                    ) if last_time else len(recent_msgs)
                )

                try:
                    if await adapter.should_participate(
                        agent_def=agent_def,
                        messages_since_last=msg_count_since,
                        seconds_since_last=seconds_since,
                        recent_content=recent_content,
                    ):
                        workflow_run_id = str(uuid7())
                        agent_message_id = str(uuid7())
                        agent_name = agent_def.name

                        async def emit(event: dict[str, Any]) -> None:
                            event.setdefault("ts", datetime.utcnow().isoformat())
                            await meeting_stream_broker.publish(room_id, event)

                        await emit({
                            "event": "agent_run_started",
                            "room_id": room_id,
                            "message_id": agent_message_id,
                            "agent_id": ra.agent_id,
                            "agent_name": agent_name,
                            "workflow_run_id": workflow_run_id,
                        })

                        content = await adapter.generate_autonomous_reply(
                            room_id=room_id,
                            agent_def=agent_def,
                            recent_messages=recent_dicts,
                            emit=emit,
                        )

                        if content:
                            await repo.create_message(
                                org_id=org_id,
                                room_id=room_id,
                                user_id=user_id,
                                username=agent_name,
                                content=content,
                                message_type="agent",
                                agent_id=ra.agent_id,
                            )
                            await session.commit()

                            _last_agent_message[(room_id, ra.agent_id)] = datetime.utcnow()

                            await emit({
                                "event": "message_final",
                                "room_id": room_id,
                                "message_id": agent_message_id,
                                "agent_id": ra.agent_id,
                                "agent_name": agent_name,
                                "workflow_run_id": workflow_run_id,
                                "content": content,
                            })
                except NotImplementedError:
                    continue
                except Exception as exc:
                    logger.exception(
                        "autonomous participation failed room_id=%s agent_id=%s",
                        room_id, ra.agent_id,
                    )
