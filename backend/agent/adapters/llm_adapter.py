from __future__ import annotations

import json
import logging
from typing import Any, Callable

import httpx

from app.core.config import settings
from agent.adapters.base import BaseAgentAdapter

logger = logging.getLogger(__name__)


class LLMAgentAdapter(BaseAgentAdapter):
    """Calls LLM API directly with agent system_prompt + room context."""

    async def invoke(
        self,
        *,
        room_id: str,
        agent_def: Any,
        query: str,
        context_messages: list[dict[str, str]],
        emit: Callable,
    ) -> str:
        llm_messages = self._build_messages(agent_def, context_messages, query)
        return await self._stream_llm(llm_messages, emit)

    async def should_participate(
        self,
        *,
        agent_def: Any,
        messages_since_last: int,
        seconds_since_last: float,
        recent_content: str,
    ) -> bool:
        strategy = getattr(agent_def, "participation_strategy", None) or {}
        if not strategy.get("auto_reply", True):
            return False

        cooldown = int(strategy.get("cooldown_seconds", 30))
        if seconds_since_last < cooldown:
            return False

        strategies = strategy.get("strategies", {})
        if strategies.get("message_count", {}).get("enabled"):
            if messages_since_last >= int(strategies["message_count"].get("every_n_messages", 5)):
                return True

        if strategies.get("silence_timer", {}).get("enabled"):
            if seconds_since_last >= int(strategies["silence_timer"].get("after_seconds", 300)):
                return True

        if strategies.get("topic_match", {}).get("enabled"):
            keywords = strategies["topic_match"].get("keywords", [])
            if keywords and any(kw.lower() in recent_content.lower() for kw in keywords):
                return True

        return False

    async def generate_autonomous_reply(
        self,
        *,
        room_id: str,
        agent_def: Any,
        recent_messages: list[dict[str, str]],
        emit: Callable,
    ) -> str:
        system_prompt = getattr(agent_def, "system_prompt", "")
        name = getattr(agent_def, "name", "AI 助手")
        llm_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": (
                f"你叫{name}，你正在自主参与一个会议讨论。"
                f"请根据最近的对话，给出有价值的发言。"
            )},
        ]
        for msg in recent_messages:
            role = "assistant" if msg.get("role") in ("agent", "agent_streaming") else "user"
            llm_messages.append({
                "role": role,
                "content": f"{msg.get('username', '')}: {msg.get('content', '')}",
            })

        return await self._stream_llm(llm_messages, emit)

    # ── private ────────────────────────────────────────────────────

    def _build_messages(
        self,
        agent_def: Any,
        context_messages: list[dict[str, str]],
        query: str,
    ) -> list[dict[str, str]]:
        system_prompt = getattr(agent_def, "system_prompt", "")
        name = getattr(agent_def, "name", "AI 助手")
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": (
                f"你叫{name}，你正在参与一个多人会议室。"
                f"有人在消息中 @了你，请直接回答这个人的问题。"
            )},
        ]
        for msg in context_messages:
            role = "assistant" if msg.get("role") in ("agent", "agent_streaming") else "user"
            messages.append({
                "role": role,
                "content": f"{msg.get('username', '')}: {msg.get('content', '')}",
            })
        messages.append({"role": "user", "content": query})
        return messages

    async def _stream_llm(
        self,
        messages: list[dict[str, str]],
        emit: Callable,
    ) -> str:
        api_key = settings.deepseek_api_key
        base_url = settings.deepseek_base_url.rstrip("/")
        model = settings.deepseek_model_id

        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY not configured")

        full_content = ""
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 2000,
                    "stream": True,
                },
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[len("data:"):].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        delta = data["choices"][0].get("delta", {}).get("content", "")
                        if delta:
                            full_content += delta
                            await emit({
                                "event": "message_delta",
                                "delta": delta,
                            })
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

        if not full_content:
            full_content = "抱歉，我暂时无法回答这个问题。"

        return full_content
