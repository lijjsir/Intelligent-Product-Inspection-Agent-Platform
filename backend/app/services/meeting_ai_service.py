from __future__ import annotations

import logging

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from agent.llm.gateway import LLMGateway
from app.core.config import settings
from app.core.exceptions import ForbiddenError, NotFoundError, ServiceUnavailableError
from app.repositories.meeting_repo import MeetingRepository
from app.schemas.meeting import MeetingMessageResponse
from app.services.model_config_service import ModelConfigService

logger = logging.getLogger(__name__)


class MeetingAiService:
    """Simple AI assistant for meeting rooms using the active runtime model."""

    def __init__(self, session: AsyncSession, org_id: str, user_id: str):
        self._session = session
        self._org_id = org_id
        self._user_id = user_id
        self._repo = MeetingRepository(session)

    async def ai_respond(
        self,
        room_id: str,
        agent_id: str = "ai_assistant",
        agent_name: str = "AI 助手",
    ) -> MeetingMessageResponse:
        await self._ensure_member(room_id)

        messages = await self._list_recent_messages(room_id, limit=50)
        llm_messages = [
            {
                "role": "system",
                "content": (
                    "你是一个会议协作助手，正在参与一个多人会议室。"
                    "请用中文回复，语气友好、简洁、专业。"
                    "只回应当前用户明确请求 AI 帮忙的上下文，不要抢话。"
                ),
            }
        ]
        for msg in messages:
            role = "assistant" if msg.message_type in ("agent", "agent_streaming") else "user"
            llm_messages.append({"role": role, "content": f"{msg.username}: {msg.content}"})

        content = await self._call_llm(llm_messages, temperature=0.7, max_tokens=2000)
        return await self._persist_agent_message(
            room_id=room_id,
            agent_id=agent_id,
            agent_name=agent_name,
            content=content,
        )

    async def summarize(self, room_id: str) -> MeetingMessageResponse:
        await self._ensure_member(room_id)

        messages = await self._list_recent_messages(room_id, limit=120)
        if not messages:
            content = "当前会议还没有可总结的内容。"
        else:
            transcript = "\n".join(
                f"{msg.username}: {msg.content}"
                for msg in messages
                if str(getattr(msg, "content", "")).strip()
            )
            llm_messages = [
                {
                    "role": "system",
                    "content": (
                        "你是一个会议纪要助手。请压缩会议上下文，输出中文会议总结。"
                        "结构包括：核心结论、待办事项、分歧或风险、后续建议。"
                        "如果信息不足，请明确说明，不要编造。"
                    ),
                },
                {"role": "user", "content": f"请总结下面的会议内容：\n\n{transcript}"},
            ]
            content = await self._call_llm(llm_messages, temperature=0.2, max_tokens=1600)

        return await self._persist_agent_message(
            room_id=room_id,
            agent_id="meeting_summary",
            agent_name="会议总结",
            content=content,
        )

    async def _list_recent_messages(self, room_id: str, limit: int):
        list_recent = getattr(self._repo, "list_recent_messages", None)
        if list_recent:
            return await list_recent(org_id=self._org_id, room_id=room_id, limit=limit)
        messages = await self._repo.list_messages(
            org_id=self._org_id,
            room_id=room_id,
            after_seq=0,
            limit=limit,
        )
        return messages[-limit:]

    async def _call_llm(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
    ) -> str:
        runtime = await self._select_runtime_model()
        if runtime:
            api_key = str(runtime.get("api_key") or settings.deepseek_api_key)
            base_url = str(runtime.get("base_url") or settings.deepseek_base_url).rstrip("/")
            model = str(runtime.get("model_id") or settings.deepseek_model_id)
        else:
            api_key = settings.deepseek_api_key
            base_url = settings.deepseek_base_url.rstrip("/")
            model = settings.deepseek_model_id

        if not api_key:
            raise ServiceUnavailableError("AI 助手未配置可用模型")

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return str(data["choices"][0]["message"]["content"]).strip()
        except httpx.HTTPStatusError as exc:
            logger.error("Meeting AI HTTP error: %s", exc)
            raise ServiceUnavailableError(f"AI 助手请求失败: {exc.response.status_code}") from exc
        except Exception as exc:
            logger.error("Meeting AI call failed: %s", exc)
            raise ServiceUnavailableError(f"AI 助手调用失败: {exc}") from exc

    async def _persist_agent_message(
        self,
        *,
        room_id: str,
        agent_id: str,
        agent_name: str,
        content: str,
    ) -> MeetingMessageResponse:
        message = await self._repo.create_message(
            org_id=self._org_id,
            room_id=room_id,
            user_id=self._user_id,
            username=agent_name,
            content=content,
            message_type="agent",
            agent_id=agent_id,
        )
        response = MeetingMessageResponse.model_validate(message)

        from app.services.stream_service import meeting_stream_broker

        await meeting_stream_broker.publish(
            room_id,
            {
                "event": "message_created",
                "room_id": room_id,
                "message": response.model_dump(),
            },
        )
        return response

    async def _select_runtime_model(self) -> dict | None:
        runtime_models = await ModelConfigService(self._session, self._org_id).list_runtime_models()
        return await LLMGateway().select_runtime(
            models=runtime_models,
            model_types={"chat", "llm", "multimodal"},
        )

    async def _ensure_member(self, room_id: str) -> None:
        room = await self._repo.get_room(self._org_id, room_id)
        if not room:
            raise NotFoundError("meeting room not found")
        member = await self._repo.get_member(self._org_id, room_id, self._user_id)
        if not member:
            raise ForbiddenError("join the meeting room before using AI assistant")
