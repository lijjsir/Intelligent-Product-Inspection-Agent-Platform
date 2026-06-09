"""ShortTermMemoryService - session-scoped context builder.

Distinct from shared memory: operates only on current chat_session/chat_messages.
Hard errors — no silent fallback.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

MAX_PROMPT_CHARS = 6000
DEFAULT_CONTEXT_WINDOW = 8192


class ShortTermMemoryService:
    """Builds short-term memory context from chat_messages and chat_sessions."""

    def __init__(self, session, org_id: str):
        self._session = session
        self._org_id = org_id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def build_context(
        self,
        *,
        user_id: str,
        session_id: str,
        current_user_seq_no: int,
        max_recent_messages: int = 20,
        max_prompt_chars: int = MAX_PROMPT_CHARS,
    ) -> dict[str, Any]:
        """Build short-term context from current chat session.

        Returns:
            Dict with conversation_summary, session_facts, recent_messages,
            pending_action, awaiting_confirmation, task_draft, missing_slots,
            selected_rag_space, token_budget.
        """
        from app.repositories.chat_repo import (
            ChatMessageRepository,
            ChatSessionRepository,
        )

        msg_repo = ChatMessageRepository(self._session)
        session_repo = ChatSessionRepository(self._session)

        # Load session-level summary/facts
        chat_session = await session_repo.get(self._org_id, user_id, session_id)
        if not chat_session:
            raise ValueError("chat session not found for short-term memory")
        conversation_summary = chat_session.context_summary or ""
        session_facts: dict[str, Any] = dict(chat_session.context_facts_json or {})

        # Load recent messages (exclude current user message)
        rows = await msg_repo.list_for_session(
            org_id=self._org_id, session_id=session_id, after_seq=0, limit=60
        )
        filtered: list[dict[str, Any]] = []
        eligible_rows = [m for m in rows if int(m.seq_no or 0) < current_user_seq_no]

        for m in eligible_rows:
            seq = int(m.seq_no or 0)
            if m.message_type in ("streaming", "error") and not (m.content or "").strip():
                continue
            content = (m.content or "").strip()
            if not content:
                continue
            filtered.append({
                "role": m.role,
                "content": content[:2000],
                "seq_no": seq,
            })

        pending_state = self._latest_pending_state(eligible_rows)
        pending_action = pending_state.get("pending_action")
        selected_rag_space = pending_state.get("selected_rag_space")

        recent = filtered[-max_recent_messages:]

        # Token-aware truncation
        model_window = await self._resolve_model_context_window()
        system_overhead = self._estimate_tokens(
            str(conversation_summary)
            + str(session_facts)
            + str(pending_action or "")
        )
        reserved = 3000 + system_overhead
        available = max(500, model_window - reserved)

        recent_messages, truncated = self._truncate_by_budget(
            list(recent),
            max_tokens=available,
            max_chars=max_prompt_chars,
        )
        estimated_used = sum(self._estimate_tokens(m["content"]) for m in recent_messages)

        return {
            "conversation_summary": conversation_summary,
            "session_facts": session_facts,
            "recent_messages": [{"role": m["role"], "content": m["content"]} for m in recent_messages],
            "pending_action": pending_action,
            "awaiting_confirmation": pending_state.get("awaiting_confirmation"),
            "task_draft": pending_state.get("task_draft"),
            "task_form_defaults": pending_state.get("task_form_defaults"),
            "missing_slots": pending_state.get("missing_slots"),
            "paper_review_status": pending_state.get("paper_review_status"),
            "selected_rag_space": selected_rag_space,
            "token_budget": {
                "model_window": model_window,
                "reserved": reserved,
                "available": available,
                "estimated_used": estimated_used,
                "truncated": truncated,
            },
        }

    # ------------------------------------------------------------------
    # Token estimation & budget
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough token count: Chinese ~1 token/char, others ~4 chars/token."""
        if not text:
            return 0
        chinese = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        other = max(0, len(text) - chinese)
        return chinese + max(1, other // 4)

    @staticmethod
    def _latest_pending_state(messages: list[Any]) -> dict[str, Any]:
        """Recover structured state from the latest assistant payload only."""
        for m in reversed(messages):
            if m.role != "assistant" or not m.payload:
                continue
            if getattr(m, "message_type", "text") == "error":
                continue
            payload = dict(m.payload)
            state: dict[str, Any] = {
                "awaiting_confirmation": payload.get("awaiting_confirmation"),
                "task_draft": payload.get("task_draft"),
                "task_form_defaults": payload.get("task_form_defaults"),
                "missing_slots": payload.get("missing_slots"),
                "paper_review_status": payload.get("paper_review_status"),
            }

            pa = payload.get("pending_action")
            if pa:
                state["pending_action"] = dict(pa) if isinstance(pa, dict) else {"type": str(pa)}
            elif any(state.values()):
                state["pending_action"] = {
                    "type": payload.get("pending_action_type") or "fill_slots",
                    "task_draft": state["task_draft"],
                    "task_form_defaults": state["task_form_defaults"],
                    "missing_slots": state["missing_slots"],
                    "awaiting_confirmation": state["awaiting_confirmation"],
                    "paper_review_status": state["paper_review_status"],
                }
            else:
                state["pending_action"] = None

            rs = payload.get("selected_rag_space")
            state["selected_rag_space"] = dict(rs) if isinstance(rs, dict) else ({"id": str(rs)} if rs else None)
            return state

        return {
            "pending_action": None,
            "awaiting_confirmation": None,
            "task_draft": None,
            "task_form_defaults": None,
            "missing_slots": None,
            "paper_review_status": None,
            "selected_rag_space": None,
        }

    @staticmethod
    def _truncate_by_budget(
        messages: list[dict],
        *,
        max_tokens: int,
        max_chars: int,
    ) -> tuple[list[dict], bool]:
        """Truncate messages from oldest until within token and character budgets."""
        truncated = False
        total = sum(
            ShortTermMemoryService._estimate_tokens(m.get("content", ""))
            for m in messages
        )
        total_chars = sum(len(str(m.get("content", ""))) for m in messages)
        while (total > max_tokens or total_chars > max_chars) and len(messages) > 1:
            removed = messages.pop(0)
            total -= ShortTermMemoryService._estimate_tokens(removed.get("content", ""))
            total_chars -= len(str(removed.get("content", "")))
            truncated = True
        return messages, truncated

    async def _resolve_model_context_window(self) -> int:
        """Look up the current model's context window size."""
        try:
            from agent.llm.gateway import LLMGateway
            from app.services.model_config_service import ModelConfigService
            from infra.database.session import get_session

            async with get_session() as s:
                runtime_models = await ModelConfigService(s, self._org_id).list_runtime_models()
                runtime = await LLMGateway().select_runtime(
                    runtime_models, model_types={"chat", "text_generation"}
                )
                if runtime:
                    return int(runtime.get("context_window", DEFAULT_CONTEXT_WINDOW))
        except Exception:
            pass
        return DEFAULT_CONTEXT_WINDOW
