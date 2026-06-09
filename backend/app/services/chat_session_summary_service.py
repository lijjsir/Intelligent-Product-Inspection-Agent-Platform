"""ChatSessionSummaryService - incremental LLM summarization of chat sessions.

Triggers when unsummarized messages >= 8 or estimated chars > 6000.
Only summarizes messages older than the most recent 6.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

SUMMARY_TRIGGER_COUNT = 8
SUMMARY_TRIGGER_CHARS = 6000
KEEP_RECENT_COUNT = 6

SUMMARY_PROMPT = """Summarize the following conversation excerpt in 2-3 sentences in the same language as the conversation. Also extract stable facts (e.g., preferred language, current work topic, user name). Output as JSON:

{"summary": "...", "facts": {"preferred_language": "...", "current_work": "...", ...}}"""


class ChatSessionSummaryService:
    """Incrementally summarizes older chat messages into ChatSession context fields."""

    def __init__(self, session, org_id: str, user_id: str):
        self._session = session
        self._org_id = org_id
        self._user_id = user_id

    async def maybe_summarize(self, session_id: str) -> bool:
        """Trigger incremental summary if threshold exceeded. Returns True if summarized."""
        from app.repositories.chat_repo import ChatMessageRepository, ChatSessionRepository

        msg_repo = ChatMessageRepository(self._session)
        session_repo = ChatSessionRepository(self._session)

        chat_session = await session_repo.get(self._org_id, self._user_id, session_id)
        if not chat_session:
            return False

        summary_seq = int(chat_session.summary_seq_no or 0)
        rows = await msg_repo.list_for_session(
            org_id=self._org_id, session_id=session_id, after_seq=summary_seq, limit=100
        )

        completed = [
            m for m in rows
            if m.message_type not in ("streaming",)
            and (m.content or "").strip()
        ]
        if len(completed) < KEEP_RECENT_COUNT:
            return False

        to_summarize = completed[:-KEEP_RECENT_COUNT]
        if len(to_summarize) < SUMMARY_TRIGGER_COUNT:
            total_chars = sum(len(m.content or "") for m in to_summarize)
            if total_chars < SUMMARY_TRIGGER_CHARS:
                return False

        transcript = "\n".join(
            f"[{m.role}]: {(m.content or '')[:500]}"
            for m in to_summarize[-20:]
        )
        new_summary, new_facts = await self._llm_summarize(transcript)

        existing_summary = chat_session.context_summary or ""
        merged_summary = f"{existing_summary}\n{new_summary}".strip() if existing_summary else new_summary
        merged_facts = {**(chat_session.context_facts_json or {}), **new_facts}
        max_seq = max(int(m.seq_no or 0) for m in to_summarize)

        chat_session.context_summary = merged_summary[:2000]
        chat_session.context_facts_json = merged_facts
        chat_session.summary_seq_no = max_seq
        chat_session.context_updated_at = datetime.now(timezone.utc)
        await self._session.flush()

        logger.debug(
            "Session %s summarized: %d messages, seq_no=%d",
            session_id, len(to_summarize), max_seq,
        )
        return True

    async def _llm_summarize(self, transcript: str) -> tuple[str, dict[str, Any]]:
        """Call LLM to generate summary and extract facts."""
        import json
        from agent.llm.client import LLMClient
        from agent.llm.gateway import LLMGateway
        from app.services.model_config_service import ModelConfigService
        from infra.database.session import get_session

        prompt = SUMMARY_PROMPT + "\n\nConversation:\n" + transcript

        async with get_session() as s:
            runtime_models = await ModelConfigService(s, self._org_id).list_runtime_models()
            runtime = await LLMGateway().select_runtime(runtime_models, model_types={"chat", "text_generation"})
            if not runtime:
                return "", {}

            client = LLMClient(
                api_key=runtime.get("api_key"),
                base_url=runtime.get("base_url"),
                model_id=str(runtime.get("model_id") or ""),
                org_id=self._org_id,
                provider=str(runtime.get("provider") or ""),
            )
            response = await client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=300,
                observation_name="chat.session_summary",
            )

        raw = str(response.get("content", "")).strip()
        try:
            if "{" in raw and "}" in raw:
                start = raw.index("{")
                end = raw.rindex("}") + 1
                data = json.loads(raw[start:end])
                return str(data.get("summary", "")), dict(data.get("facts", {}))
        except (json.JSONDecodeError, ValueError):
            pass
        return raw[:200], {}
