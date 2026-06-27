from __future__ import annotations

import json
from typing import Any


class MemoryContextInjector:
    @staticmethod
    def format_shared_memory(
        shared_memory_context: dict | None,
        *,
        max_items: int = 5,
        max_chars: int = 2000,
    ) -> tuple[str, dict[str, Any]]:
        if not isinstance(shared_memory_context, dict):
            return "", {"shared_memory_injected_count": 0}

        suppressed = set(
            str(item)
            for item in ((shared_memory_context.get("conflict_guard") or {}).get("suppressed_memory_ids") or [])
        )
        downranked = set(
            str(item)
            for item in ((shared_memory_context.get("conflict_guard") or {}).get("downranked_memory_ids") or [])
        )

        lines = [
            "[Shared Memory Context]",
            "Use these cross-session memories as historical reference. If they conflict with current task evidence or standards, prefer the current task context.",
        ]
        count = 0
        for item in list(shared_memory_context.get("items") or [])[:max_items]:
            if not isinstance(item, dict):
                continue
            memory_id = str(item.get("memory_id") or "").strip()
            if not memory_id or memory_id in suppressed:
                continue
            hints: list[str] = []
            if memory_id in downranked:
                hints.append("downranked by conflict guard")
            for warning in list(item.get("warnings") or []):
                if warning:
                    hints.append(str(warning))
            count += 1
            lines.extend(
                [
                    f"{count}. [{memory_id}] type={item.get('memory_type') or ''}",
                    f"   summary: {str(item.get('summary') or '')}",
                    f"   trust_score={item.get('trust_score')}, confidence={item.get('confidence')}, score={item.get('score')}",
                    f"   hints: {'; '.join(hints) if hints else 'none'}",
                ]
            )

        if count == 0:
            return "", {"shared_memory_injected_count": 0}
        text = "\n".join(lines)
        if len(text) > max_chars:
            text = text[:max_chars].rstrip() + "\n[truncated]"
        return text, {"shared_memory_injected_count": count}

    @staticmethod
    def format_short_term_context(
        short_term_context: dict | None,
        *,
        max_chars: int = 2000,
    ) -> tuple[str, dict[str, Any]]:
        if not isinstance(short_term_context, dict):
            return "", {"short_term_summary_injected": False, "session_facts_injected_keys": []}

        stm = short_term_context.get("short_term_memory") or {}
        session_summary = stm.get("session_summary") if isinstance(stm, dict) else {}
        summary = (
            short_term_context.get("conversation_summary")
            or (session_summary or {}).get("summary")
            or ""
        )
        facts = short_term_context.get("session_facts")
        if not isinstance(facts, dict):
            facts = (session_summary or {}).get("confirmed_facts") or {}
        if not isinstance(facts, dict):
            facts = {}

        recent = []
        if isinstance(stm, dict):
            recent = list(stm.get("recent_dialogue") or [])
        if not recent:
            recent = list(short_term_context.get("recent_messages") or [])

        working_state = stm.get("working_state") if isinstance(stm, dict) else {}
        lines = ["[Short-Term Session Context]"]
        lines.append(f"conversation_summary: {summary or 'none'}")
        lines.append(f"session_facts: {json.dumps(facts, ensure_ascii=False, sort_keys=True) if facts else '{}'}")
        if isinstance(working_state, dict) and working_state:
            compact_state = {
                key: value
                for key, value in working_state.items()
                if key in {"pending_action", "awaiting_confirmation", "task_draft", "missing_slots"}
                and value
            }
            if compact_state:
                lines.append(f"working_state: {json.dumps(compact_state, ensure_ascii=False, sort_keys=True)}")
        if recent:
            lines.append("recent_dialogue:")
            for item in recent[-12:]:
                if isinstance(item, dict) and item.get("content"):
                    lines.append(f"- {item.get('role', 'user')}: {str(item.get('content'))[:500]}")

        text = "\n".join(lines)
        if len(text) > max_chars:
            text = text[:max_chars].rstrip() + "\n[truncated]"
        keys = sorted(str(key) for key in facts.keys())
        return text, {
            "short_term_summary_injected": bool(str(summary or "").strip()),
            "session_facts_injected_keys": keys,
        }
