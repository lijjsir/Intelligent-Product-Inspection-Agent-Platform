"""Deterministic conversation compression inspired by bk-aidev-agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ContextCompressionStats:
    original_messages: int
    kept_messages: int
    dropped_messages: int
    original_chars: int
    kept_chars: int


def compress_history(
    messages: list[dict[str, Any]] | None,
    *,
    max_chars: int = 8_000,
    keep_recent: int = 6,
    per_message_chars: int = 1_600,
) -> tuple[list[dict[str, str]], ContextCompressionStats]:
    normalized = [
        {
            "role": str(item.get("role") or "user"),
            "content": str(item.get("content") or "").strip(),
        }
        for item in (messages or [])
        if str(item.get("content") or "").strip()
    ]
    original_chars = sum(len(item["content"]) for item in normalized)
    if not normalized:
        return [], ContextCompressionStats(0, 0, 0, 0, 0)

    budget = max(256, int(max_chars))
    message_limit = max(128, int(per_message_chars))
    prioritized = normalized[-max(1, int(keep_recent)) :]
    older = normalized[: -len(prioritized)] if len(prioritized) < len(normalized) else []

    selected_reversed: list[dict[str, str]] = []
    used = 0
    for item in reversed(prioritized):
        content = _truncate(item["content"], min(message_limit, max(64, budget - used)))
        if used and used + len(content) > budget:
            break
        selected_reversed.append({"role": item["role"], "content": content})
        used += len(content)
        if used >= budget:
            break

    for item in reversed(older):
        remaining = budget - used
        if remaining < 128:
            break
        content = _truncate(item["content"], min(message_limit, remaining))
        selected_reversed.append({"role": item["role"], "content": content})
        used += len(content)

    selected = list(reversed(selected_reversed))
    kept_chars = sum(len(item["content"]) for item in selected)
    return selected, ContextCompressionStats(
        original_messages=len(normalized),
        kept_messages=len(selected),
        dropped_messages=len(normalized) - len(selected),
        original_chars=original_chars,
        kept_chars=kept_chars,
    )


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    marker = f"\n...[truncated {len(value) - limit} chars]...\n"
    remaining = max(16, limit - len(marker))
    head = max(8, int(remaining * 0.7))
    tail = max(8, remaining - head)
    return f"{value[:head]}{marker}{value[-tail:]}"
