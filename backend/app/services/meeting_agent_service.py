from __future__ import annotations

import asyncio
import logging
import uuid as _uuid
from datetime import datetime
from typing import Any

from agent.adapters.factory import AgentAdapterFactory
from agent.llm.gateway import LLMGateway
from app.core.data_domain_policy import (
    RESPONSE_VISIBILITY_PRIVATE,
    RESPONSE_VISIBILITY_ROOM,
    authorize_meeting_query,
    infer_requested_domains_for_query,
    is_sensitive_authorization,
    normalize_domains,
)
from app.core.ids import uuid7
from app.core.permissions import ROLE_USER
from app.repositories.meeting_repo import MeetingRepository
from app.services.ai_response_text import normalize_ai_response_content
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


async def _list_recent_messages(repo: Any, *, org_id: str, room_id: str, limit: int, visible_user_id: str | None = None):
    list_recent = getattr(repo, "list_recent_messages", None)
    if list_recent:
        try:
            return await list_recent(org_id=org_id, room_id=room_id, limit=limit, visible_user_id=visible_user_id)
        except TypeError:
            return await list_recent(org_id=org_id, room_id=room_id, limit=limit)
    try:
        messages = await repo.list_messages(org_id=org_id, room_id=room_id, after_seq=0, limit=limit, visible_user_id=visible_user_id)
    except TypeError:
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
        user_role: str = ROLE_USER,
    ) -> None:
        workflow_run_id = str(uuid7())
        agent_message_id = str(uuid7())

        async def emit(event: dict[str, Any]) -> None:
            event.setdefault("ts", datetime.utcnow().isoformat())
            event.setdefault("private_user_ids", [user_id])
            event.setdefault("response_visibility", RESPONSE_VISIBILITY_PRIVATE)
            await meeting_stream_broker.publish(room_id, event)

        try:
            if not _is_valid_uuid(agent_def_id):
                logger.warning("invalid agent_def_id (not a UUID): %s", agent_def_id)
                return

            async with get_session() as session:
                repo = MeetingRepository(session)
                room = await self._get_room(repo, org_id=org_id, room_id=room_id)
                room_agent = await self._get_room_agent(
                    repo,
                    org_id=org_id,
                    room_id=room_id,
                    agent_id=agent_def_id,
                )
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
                    visible_user_id=user_id,
                )
                context_dicts = [
                    {"role": msg.message_type, "username": msg.username, "content": msg.content}
                    for msg in context_msgs
                ]
                access = self._authorize_named_agent_query(
                    role=user_role,
                    question=query,
                    room=room,
                    room_agent=room_agent,
                )
                if access.decision == "denied":
                    denial_answer = "当前请求超出你的会议室或 Agent 权限范围，无法回答该问题。"
                    await self._persist_agent_message(
                        repo,
                        org_id=org_id,
                        room_id=room_id,
                        user_id=user_id,
                        agent_id=agent_def_id,
                        agent_name=agent_name,
                        content=denial_answer,
                        message_id=agent_message_id,
                        metadata_json={
                            "query": query,
                            "workflow_run_id": workflow_run_id,
                            "selected_subgraph": "access_denied",
                            "requested_data_domains": access.requested_domains,
                            "allowed_data_domains": access.allowed_domains,
                            "denied_data_domains": access.denied_domains,
                            "denied_reasons": access.denied_reasons,
                            "redacted_fields": access.redacted_fields,
                            "visibility": RESPONSE_VISIBILITY_PRIVATE,
                            "response_visibility": RESPONSE_VISIBILITY_PRIVATE,
                            "audience_scope_type": "user",
                            "audience_scope_id": user_id,
                            "private_recipient_user_id": user_id,
                        },
                        private_recipient_user_id=user_id,
                    )
                    await self._record_agent_query_audit(
                        repo,
                        org_id=org_id,
                        room_id=room_id,
                        user_id=user_id,
                        agent_id=agent_def_id,
                        question=query,
                        intent="access_denied",
                        authorization=access,
                    )
                    await session.commit()
                    await emit(
                        {
                            "event": "message_final",
                            "room_id": room_id,
                            "message_id": agent_message_id,
                            "agent_id": agent_def_id,
                            "agent_name": agent_name,
                            "workflow_run_id": workflow_run_id,
                            "content": denial_answer,
                        }
                    )
                    return
                if access.denied_domains or is_sensitive_authorization(access):
                    context_dicts.append(
                        {
                            "role": "system",
                            "username": "权限边界",
                            "content": (
                                f"本次只允许回答这些数据域：{', '.join(access.allowed_domains) or '无'}。"
                                f"这些数据域已被拒绝，不能回答或推测：{', '.join(access.denied_domains) or '无'}。"
                                "如果涉及 api_key、token、password、secret、连接串等字段，只能说明脱敏状态，不能输出明文。"
                            ),
                        }
                    )

            adapter = self._factory.get_for_agent(agent_def)
            await emit(
                {
                    "event": "agent_run_started",
                    "room_id": room_id,
                    "message_id": agent_message_id,
                    "agent_id": agent_def_id,
                    "agent_name": agent_name,
                    "workflow_run_id": workflow_run_id,
                    "query": query,
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
            display_content, response_metadata = normalize_ai_response_content(full_content)

            async with get_session() as session:
                repo = MeetingRepository(session)
                await self._persist_agent_message(
                    repo,
                    org_id=org_id,
                    room_id=room_id,
                    user_id=user_id,
                    username=agent_name,
                    agent_name=agent_name,
                    content=display_content,
                    message_type="agent",
                    agent_id=agent_def_id,
                    metadata_json={
                        "query": query,
                        "workflow_run_id": workflow_run_id,
                        "private_recipient_user_id": user_id,
                        "visibility": RESPONSE_VISIBILITY_PRIVATE,
                        "response_visibility": RESPONSE_VISIBILITY_PRIVATE,
                        "audience_scope_type": "user",
                        "audience_scope_id": user_id,
                        "requested_data_domains": access.requested_domains,
                        "allowed_data_domains": access.allowed_domains,
                        "denied_data_domains": access.denied_domains,
                        "denied_reasons": access.denied_reasons,
                        "redacted_fields": access.redacted_fields,
                        **(response_metadata or {}),
                    },
                    private_recipient_user_id=user_id,
                    message_id=agent_message_id,
                )
                await self._record_agent_query_audit(
                    repo,
                    org_id=org_id,
                    room_id=room_id,
                    user_id=user_id,
                    agent_id=agent_def_id,
                    question=query,
                    intent="named_agent",
                    authorization=access,
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
                    "content": display_content,
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
                autonomous_query = "基于最近会议上下文主动提醒"

                async def emit(event: dict[str, Any]) -> None:
                    event.setdefault("ts", datetime.utcnow().isoformat())
                    event.setdefault("private_user_ids", [user_id])
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
                            "query": autonomous_query,
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
                    display_content, response_metadata = normalize_ai_response_content(content)

                    await repo.create_message(
                        org_id=org_id,
                        room_id=room_id,
                        user_id=user_id,
                        username=agent_name,
                        content=display_content,
                        message_type="agent",
                        agent_id=str(room_agent.agent_id),
                        metadata_json={
                            "query": autonomous_query,
                            "private_recipient_user_id": user_id,
                            **(response_metadata or {}),
                        },
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
                            "content": display_content,
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
                        metadata_json={"private_recipient_user_id": user_id},
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

    async def _get_room(self, repo: Any, *, org_id: str, room_id: str) -> Any | None:
        get_room = getattr(repo, "get_room", None)
        if not get_room:
            return None
        try:
            return await get_room(org_id, room_id)
        except TypeError:
            return await get_room(org_id=org_id, room_id=room_id)

    async def _get_room_agent(self, repo: Any, *, org_id: str, room_id: str, agent_id: str) -> Any | None:
        get_agent = getattr(repo, "get_agent", None)
        if not get_agent:
            return None
        try:
            return await get_agent(org_id, room_id, agent_id)
        except TypeError:
            return await get_agent(org_id=org_id, room_id=room_id, agent_id=agent_id)

    def _authorize_named_agent_query(
        self,
        *,
        role: str,
        question: str,
        room: Any | None,
        room_agent: Any | None,
    ):
        room_domains = normalize_domains(getattr(room, "allowed_data_domains", None)) or None
        agent_domains = normalize_domains(getattr(room_agent, "allowed_domains", None)) if room_agent is not None else None
        return authorize_meeting_query(
            role=role,
            requested_domains=infer_requested_domains_for_query("named_agent", question),
            room_domains=room_domains,
            agent_domains=agent_domains,
            question=question,
        )

    async def _persist_agent_message(
        self,
        repo: Any,
        *,
        org_id: str,
        room_id: str,
        user_id: str,
        agent_id: str,
        agent_name: str,
        content: str,
        metadata_json: dict[str, Any],
        private_recipient_user_id: str,
        message_id: str | None = None,
        username: str | None = None,
        message_type: str = "agent",
    ) -> Any:
        kwargs = {
            "org_id": org_id,
            "room_id": room_id,
            "user_id": user_id,
            "username": username or agent_name,
            "content": content,
            "message_type": message_type,
            "agent_id": agent_id,
            "metadata_json": metadata_json,
            "private_recipient_user_id": private_recipient_user_id,
        }
        if message_id:
            kwargs["message_id"] = message_id
        try:
            return await repo.create_message(**kwargs)
        except TypeError:
            kwargs.pop("message_id", None)
            return await repo.create_message(**kwargs)

    async def _record_agent_query_audit(
        self,
        repo: Any,
        *,
        org_id: str,
        room_id: str,
        user_id: str,
        agent_id: str,
        question: str,
        intent: str,
        authorization: Any,
    ) -> None:
        create_audit = getattr(repo, "create_agent_query_audit", None)
        if create_audit is None:
            return
        await create_audit(
            org_id=org_id,
            room_id=room_id,
            user_id=user_id,
            agent_id=agent_id,
            question=str(question or "").strip()[:4000],
            intent=intent,
            requested_domains=authorization.requested_domains,
            allowed_domains=authorization.allowed_domains,
            denied_domains=authorization.denied_domains,
            tool_calls=[],
            source_refs=[],
            redacted_fields=authorization.redacted_fields,
            decision=authorization.decision,
            response_visibility=authorization.response_visibility,
            redaction_level=authorization.redaction_level,
            denied_reasons=authorization.denied_reasons,
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
            await self._persist_agent_message(
                repo,
                org_id=org_id,
                room_id=room_id,
                user_id=user_id,
                agent_name=agent_name,
                content=f"[Agent {agent_name}] 响应失败: {error}",
                agent_id=agent_id,
                metadata_json={
                    "private_recipient_user_id": user_id,
                    "visibility": RESPONSE_VISIBILITY_PRIVATE,
                    "response_visibility": RESPONSE_VISIBILITY_PRIVATE,
                    "audience_scope_type": "user",
                    "audience_scope_id": user_id,
                },
                private_recipient_user_id=user_id,
            )
            await session.commit()
