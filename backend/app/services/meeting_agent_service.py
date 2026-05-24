from __future__ import annotations

import asyncio
import logging
import uuid as _uuid
from datetime import datetime
from typing import Any

from agent.adapters.factory import AgentAdapterFactory
from agent.llm.gateway import LLMGateway
from app.core.ids import uuid7
from app.repositories.meeting_repo import MeetingRepository
from app.services.model_config_service import ModelConfigService
from app.services.stream_service import meeting_stream_broker
from infra.database.session import get_session

logger = logging.getLogger(__name__)


def _is_valid_uuid(value: str) -> bool:
    try:
        _uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


async def _list_recent_messages(repo: Any, *, org_id: str, room_id: str, limit: int):
    list_recent = getattr(repo, "list_recent_messages", None)
    if list_recent:
        return await list_recent(org_id=org_id, room_id=room_id, limit=limit)
    messages = await repo.list_messages(org_id=org_id, room_id=room_id, after_seq=0, limit=limit)
    return messages[-limit:]


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
        message_id: str | None = None,
        query: str,
        org_id: str,
        user_id: str,
        username: str,
    ) -> None:
        workflow_run_id = str(uuid7())
        agent_message_id = str(uuid7())

        async def emit(event: dict[str, Any]) -> None:
            event.setdefault("ts", datetime.utcnow().isoformat())
            await meeting_stream_broker.publish(room_id, event)

        try:
            if not _is_valid_uuid(agent_def_id):
                logger.warning("invalid agent_def_id (not a UUID): %s", agent_def_id)
                return

            async with get_session() as session:
                repo = MeetingRepository(session)
                agent_def = await repo.get_visible_agent_definition(org_id, agent_def_id)
                if not agent_def:
                    logger.warning("agent definition not found: %s", agent_def_id)
                    return
                if not agent_def.is_active:
                    logger.warning("agent definition is inactive: %s", agent_def_id)
                    return
                runtime_model = await self._select_runtime_model(session, org_id)
                context_msgs = await _list_recent_messages(
                    repo,
                    org_id=org_id,
                    room_id=room_id,
                    limit=50,
                )
                context_dicts = [
                    {"role": msg.message_type, "username": msg.username, "content": msg.content}
                    for msg in context_msgs
                ]

            adapter = self._factory.get_for_agent(agent_def)
            await emit(
                {
                    "event": "agent_run_started",
                    "room_id": room_id,
                    "message_id": agent_message_id,
                    "agent_id": agent_def_id,
                    "agent_name": agent_name,
                    "workflow_run_id": workflow_run_id,
                }
            )
            full_content = await adapter.invoke(
                room_id=room_id,
                agent_def=agent_def,
                query=query,
                context_messages=context_dicts,
                emit=emit,
                runtime_model=runtime_model,
            )

            async with get_session() as session:
                repo = MeetingRepository(session)
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
            await emit(
                {
                    "event": "message_final",
                    "room_id": room_id,
                    "message_id": agent_message_id,
                    "agent_id": agent_def_id,
                    "agent_name": agent_name,
                    "workflow_run_id": workflow_run_id,
                    "content": full_content,
                }
            )
        except Exception as exc:
            logger.exception(
                "meeting agent invocation failed room_id=%s agent_id=%s workflow_run_id=%s",
                room_id,
                agent_def_id,
                workflow_run_id,
            )
            await self._persist_error_message(
                room_id=room_id,
                org_id=org_id,
                user_id=user_id,
                agent_id=agent_def_id,
                agent_name=agent_name,
                error=exc,
            )
            await emit(
                {
                    "event": "agent_run_failed",
                    "room_id": room_id,
                    "message_id": agent_message_id,
                    "agent_id": agent_def_id,
                    "agent_name": agent_name,
                    "workflow_run_id": workflow_run_id,
                    "error": str(exc),
                }
            )

    async def start_discussion_round(
        self,
        *,
        room_id: str,
        org_id: str,
        user_id: str,
        username: str,
        query: str,
        max_agents: int = 3,
    ) -> int:
        async with get_session() as session:
            repo = MeetingRepository(session)
            room_agents = await repo.get_agents(org_id, room_id)
            participants: list[dict[str, str]] = []
            for room_agent in room_agents:
                if getattr(room_agent, "role", "participant") != "participant":
                    continue
                if not _is_valid_uuid(str(room_agent.agent_id)):
                    continue
                agent_def = await repo.get_visible_agent_definition(org_id, str(room_agent.agent_id))
                if not agent_def or not getattr(agent_def, "is_active", True):
                    continue
                participants.append(
                    {
                        "agent_id": str(room_agent.agent_id),
                        "agent_name": str(agent_def.name),
                    }
                )
                if len(participants) >= max_agents:
                    break

        if not participants:
            return 0

        asyncio.create_task(
            self._run_discussion_round(
                room_id=room_id,
                org_id=org_id,
                user_id=user_id,
                username=username,
                query=query,
                participants=participants,
            )
        )
        return len(participants)

    async def _run_discussion_round(
        self,
        *,
        room_id: str,
        org_id: str,
        user_id: str,
        username: str,
        query: str,
        participants: list[dict[str, str]],
    ) -> None:
        for participant in participants:
            await self.invoke_agent(
                room_id=room_id,
                agent_def_id=participant["agent_id"],
                agent_name=participant["agent_name"],
                message_id=str(uuid7()),
                query=query,
                org_id=org_id,
                user_id=user_id,
                username=username,
            )

    async def check_autonomous_participation(
        self,
        *,
        room_id: str,
        org_id: str,
        user_id: str,
    ) -> None:
        async with get_session() as session:
            repo = MeetingRepository(session)
            room_agents = await repo.get_agents(org_id, room_id)
            if not room_agents:
                return

            runtime_model = await self._select_runtime_model(session, org_id)
            recent_msgs = await _list_recent_messages(
                repo,
                org_id=org_id,
                room_id=room_id,
                limit=50,
            )
            recent_content = " ".join(m.content for m in recent_msgs[-10:])
            recent_dicts = [
                {"role": m.message_type, "username": m.username, "content": m.content}
                for m in recent_msgs[-20:]
            ]

            for room_agent in room_agents:
                if getattr(room_agent, "role", "participant") != "participant":
                    continue
                if not _is_valid_uuid(str(room_agent.agent_id)):
                    continue

                agent_def = await repo.get_visible_agent_definition(org_id, str(room_agent.agent_id))
                if not agent_def or not agent_def.is_active:
                    continue

                adapter = self._factory.get_for_agent(agent_def)
                last_time = _last_agent_message.get((room_id, str(room_agent.agent_id)))
                seconds_since = (datetime.utcnow() - last_time).total_seconds() if last_time else 999999
                msg_count_since = (
                    sum(1 for m in recent_msgs if last_time and m.created_at and m.created_at > last_time)
                    if last_time
                    else len(recent_msgs)
                )

                try:
                    should_reply = await adapter.should_participate(
                        agent_def=agent_def,
                        messages_since_last=msg_count_since,
                        seconds_since_last=seconds_since,
                        recent_content=recent_content,
                    )
                except NotImplementedError:
                    continue

                if not should_reply:
                    continue

                workflow_run_id = str(uuid7())
                agent_message_id = str(uuid7())
                agent_name = str(agent_def.name)

                async def emit(event: dict[str, Any]) -> None:
                    event.setdefault("ts", datetime.utcnow().isoformat())
                    await meeting_stream_broker.publish(room_id, event)

                try:
                    await emit(
                        {
                            "event": "agent_run_started",
                            "room_id": room_id,
                            "message_id": agent_message_id,
                            "agent_id": str(room_agent.agent_id),
                            "agent_name": agent_name,
                            "workflow_run_id": workflow_run_id,
                        }
                    )
                    content = await adapter.generate_autonomous_reply(
                        room_id=room_id,
                        agent_def=agent_def,
                        recent_messages=recent_dicts,
                        emit=emit,
                        runtime_model=runtime_model,
                    )
                    if not content:
                        continue

                    await repo.create_message(
                        org_id=org_id,
                        room_id=room_id,
                        user_id=user_id,
                        username=agent_name,
                        content=content,
                        message_type="agent",
                        agent_id=str(room_agent.agent_id),
                    )
                    await session.commit()

                    _last_agent_message[(room_id, str(room_agent.agent_id))] = datetime.utcnow()
                    await emit(
                        {
                            "event": "message_final",
                            "room_id": room_id,
                            "message_id": agent_message_id,
                            "agent_id": str(room_agent.agent_id),
                            "agent_name": agent_name,
                            "workflow_run_id": workflow_run_id,
                            "content": content,
                        }
                    )
                except NotImplementedError:
                    continue
                except Exception as exc:
                    logger.exception(
                        "autonomous participation failed room_id=%s agent_id=%s",
                        room_id,
                        room_agent.agent_id,
                    )
                    await repo.create_message(
                        org_id=org_id,
                        room_id=room_id,
                        user_id=user_id,
                        username=agent_name,
                        content=f"[Agent {agent_name}] 响应失败: {exc}",
                        message_type="agent",
                        agent_id=str(room_agent.agent_id),
                    )
                    await session.commit()
                    await emit(
                        {
                            "event": "agent_run_failed",
                            "room_id": room_id,
                            "message_id": agent_message_id,
                            "agent_id": str(room_agent.agent_id),
                            "agent_name": agent_name,
                            "workflow_run_id": workflow_run_id,
                            "error": str(exc),
                        }
                    )

    async def _select_runtime_model(self, session, org_id: str) -> dict | None:
        runtime_models = await ModelConfigService(session, org_id).list_runtime_models()
        return await LLMGateway().select_runtime(
            models=runtime_models,
            model_types={"chat", "llm", "multimodal"},
        )

    async def _persist_error_message(
        self,
        *,
        room_id: str,
        org_id: str,
        user_id: str,
        agent_id: str,
        agent_name: str,
        error: Exception,
    ) -> None:
        async with get_session() as session:
            repo = MeetingRepository(session)
            await repo.create_message(
                org_id=org_id,
                room_id=room_id,
                user_id=user_id,
                username=agent_name,
                content=f"[Agent {agent_name}] 响应失败: {error}",
                message_type="agent",
                agent_id=agent_id,
            )
            await session.commit()
