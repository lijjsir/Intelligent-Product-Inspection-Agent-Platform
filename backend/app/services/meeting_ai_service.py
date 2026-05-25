from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from agent.llm.gateway import LLMGateway
from app.core.config import settings
from app.core.exceptions import ForbiddenError, NotFoundError, ServiceUnavailableError
from app.repositories.meeting_repo import MeetingRepository
from app.schemas.meeting import MeetingMessageResponse
from app.services.model_config_service import ModelConfigService

logger = logging.getLogger(__name__)

MEETING_AI_MODEL_TYPES = {"chat", "llm", "multimodal"}


class MeetingAiService:
    """Simple AI assistant for meeting rooms using the best available chat runtime."""

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
        runtime_models = await self._list_runtime_models()
        gateway = LLMGateway()
        excluded_runtime_ids: set[str] = set()
        attempted_runtime = False
        saw_runtime_auth_failure = False

        while True:
            runtime = await gateway.select_runtime(
                models=runtime_models,
                excluded_runtime_ids=excluded_runtime_ids,
                model_types=MEETING_AI_MODEL_TYPES,
            )
            if runtime is None:
                break

            attempted_runtime = True
            try:
                return await self._request_completion(
                    messages,
                    runtime=runtime,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                logger.warning(
                    "Meeting AI runtime HTTP error status=%s runtime=%s",
                    status_code,
                    self._runtime_label(runtime),
                )
                if status_code in (401, 403):
                    saw_runtime_auth_failure = True
                if self._should_failover_status(status_code):
                    runtime_key = self._runtime_key(runtime)
                    if runtime_key:
                        excluded_runtime_ids.add(runtime_key)
                    continue
                raise ServiceUnavailableError(
                    self._status_error_message(status_code, runtime=runtime, default_runtime=False)
                ) from exc
            except Exception as exc:
                logger.error(
                    "Meeting AI runtime call failed runtime=%s error=%s",
                    self._runtime_label(runtime),
                    exc,
                )
                runtime_key = self._runtime_key(runtime)
                if runtime_key:
                    excluded_runtime_ids.add(runtime_key)

        default_runtime = self._build_default_runtime()
        if default_runtime is not None:
            try:
                return await self._request_completion(
                    messages,
                    runtime=default_runtime,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                logger.warning(
                    "Meeting AI default runtime HTTP error status=%s runtime=%s",
                    status_code,
                    self._runtime_label(default_runtime),
                )
                raise ServiceUnavailableError(
                    self._status_error_message(status_code, runtime=default_runtime, default_runtime=True)
                ) from exc
            except Exception as exc:
                logger.error("Meeting AI default runtime call failed: %s", exc)
                raise ServiceUnavailableError(
                    "会议 AI 默认模型调用失败，请检查 backend/.env 中的模型配置。"
                ) from exc

        if saw_runtime_auth_failure:
            raise ServiceUnavailableError(
                "会议 AI 模型鉴权失败，请在“模型配置”中检查聊天模型的 API Key 和 endpoint。"
            )
        if attempted_runtime:
            raise ServiceUnavailableError("会议 AI 暂不可用，请稍后重试或检查模型配置。")
        raise ServiceUnavailableError(
            "会议 AI 暂不可用，请先在“模型配置”中配置可用的聊天模型，或检查 backend/.env 中的默认模型配置。"
        )

    async def _request_completion(
        self,
        messages: list[dict[str, str]],
        *,
        runtime: dict[str, Any],
        temperature: float,
        max_tokens: int,
    ) -> str:
        api_key = str(runtime.get("api_key") or "").strip()
        base_url = str(runtime.get("base_url") or "").strip().rstrip("/")
        model = str(runtime.get("model_id") or "").strip()

        if not api_key:
            raise ServiceUnavailableError("会议 AI 未配置可用模型。")
        if not base_url or not model:
            raise ServiceUnavailableError("会议 AI 模型配置不完整，请检查 endpoint 和模型标识。")

        async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
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

    async def _list_runtime_models(self) -> list[dict[str, Any]]:
        return await ModelConfigService(self._session, self._org_id).list_runtime_models()

    def _build_default_runtime(self) -> dict[str, Any] | None:
        api_key = str(settings.deepseek_api_key or "").strip()
        base_url = str(settings.deepseek_base_url or "").strip().rstrip("/")
        model_id = str(settings.deepseek_model_id or "").strip()
        if not api_key or not base_url or not model_id:
            return None
        return {
            "runtime_key": "default::deepseek",
            "provider": "deepseek",
            "model_id": model_id,
            "base_url": base_url,
            "api_key": api_key,
            "display_name": "DeepSeek default",
        }

    def _status_error_message(
        self,
        status_code: int,
        *,
        runtime: dict[str, Any],
        default_runtime: bool,
    ) -> str:
        if status_code in (401, 403):
            if default_runtime:
                return (
                    "会议 AI 默认模型鉴权失败，请检查 backend/.env 中的 "
                    "PIAP_DEEPSEEK_API_KEY 和 PIAP_DEEPSEEK_BASE_URL。"
                )
            return (
                f"会议 AI 模型“{self._runtime_label(runtime)}”鉴权失败，"
                "请在“模型配置”中检查 API Key 和 endpoint。"
            )
        if status_code == 429:
            return "会议 AI 当前模型已触发速率限制，请稍后重试或切换其他模型。"
        if 500 <= status_code < 600:
            return "会议 AI 上游模型服务暂不可用，请稍后重试。"
        return f"AI 助手请求失败: {status_code}"

    @staticmethod
    def _should_failover_status(status_code: int) -> bool:
        return status_code in {401, 403, 408, 409, 429} or 500 <= status_code < 600

    @staticmethod
    def _runtime_key(runtime: dict[str, Any]) -> str:
        return str(runtime.get("runtime_key") or runtime.get("model_config_id") or runtime.get("model_id") or "")

    @staticmethod
    def _runtime_label(runtime: dict[str, Any]) -> str:
        return str(runtime.get("display_name") or runtime.get("model_id") or runtime.get("runtime_key") or "meeting-ai")

    async def _ensure_member(self, room_id: str) -> None:
        room = await self._repo.get_room(self._org_id, room_id)
        if not room:
            raise NotFoundError("meeting room not found")
        member = await self._repo.get_member(self._org_id, room_id, self._user_id)
        if not member:
            raise ForbiddenError("join the meeting room before using AI assistant")
