from __future__ import annotations

import logging

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ForbiddenError, NotFoundError, ServiceUnavailableError
from app.repositories.meeting_repo import MeetingRepository
from app.schemas.meeting import MeetingMessageResponse

logger = logging.getLogger(__name__)


class MeetingAiService:
    """Simple LLM chat for meeting rooms — no agent pipeline, just direct API call."""

    def __init__(self, session: AsyncSession, org_id: str, user_id: str):
        self._session = session
        self._org_id = org_id
        self._user_id = user_id
        self._repo = MeetingRepository(session)

    async def ai_respond(
        self, room_id: str, agent_id: str = "ai_assistant", agent_name: str = "AI 助手"
    ) -> MeetingMessageResponse:
        await self._ensure_member(room_id)

        # Gather context: last 20 messages
        messages = await self._repo.list_messages(
            org_id=self._org_id, room_id=room_id, after_seq=0, limit=20
        )

        # Build LLM messages
        llm_messages = [
            {
                "role": "system",
                "content": (
                    "你是一个会议协作助手，正在参与一个多人会议室。"
                    "请用中文回复，语气友好、简洁、专业。"
                    "根据最近的对话内容给出有价值的回应。"
                ),
            }
        ]
        for msg in messages:
            role = "assistant" if msg.message_type in ("agent", "agent_streaming") else "user"
            llm_messages.append({"role": role, "content": f"{msg.username}: {msg.content}"})

        # Call LLM directly via httpx (plain text, no JSON mode)
        api_key = settings.deepseek_api_key
        base_url = settings.deepseek_base_url.rstrip("/")
        model = settings.deepseek_model_id

        if not api_key:
            raise ServiceUnavailableError("AI 助手未配置（缺少 DEEPSEEK_API_KEY）")

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
                        "messages": llm_messages,
                        "temperature": 0.7,
                        "max_tokens": 2000,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"].strip()
        except httpx.HTTPStatusError as exc:
            logger.error("LLM API error: %s", exc)
            raise ServiceUnavailableError(f"AI 助手请求失败: {exc.response.status_code}")
        except Exception as exc:
            logger.error("LLM call failed: %s", exc)
            raise ServiceUnavailableError(f"AI 助手调用失败: {exc}")

        # Save AI response as meeting message
        message = await self._repo.create_message(
            org_id=self._org_id,
            room_id=room_id,
            user_id=self._user_id,
            username=agent_name,
            content=content,
            message_type="agent",
            agent_id=agent_id,
        )

        # Publish to stream broker
        from app.services.stream_service import meeting_stream_broker
        await meeting_stream_broker.publish(room_id, {
            "event": "message_created",
            "room_id": room_id,
            "message": MeetingMessageResponse.model_validate(message).model_dump(),
        })

        return MeetingMessageResponse.model_validate(message)

    async def _ensure_member(self, room_id: str) -> None:
        room = await self._repo.get_room(self._org_id, room_id)
        if not room:
            raise NotFoundError("meeting room not found")
        member = await self._repo.get_member(self._org_id, room_id, self._user_id)
        if not member:
            raise ForbiddenError("join the meeting room before using AI assistant")
