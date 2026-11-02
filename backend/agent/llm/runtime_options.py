from __future__ import annotations

from typing import Any

from app.core.config import settings


def apply_runtime_options(payload: dict[str, Any], provider: str | None) -> dict[str, Any]:
    """Apply explicit local serving defaults without changing cloud providers."""
    result = dict(payload)
    if str(provider or "").strip().lower() == "local_openai" and "messages" in result:
        effort = str(settings.local_model_reasoning_effort or "").strip()
        if effort:
            result.setdefault("reasoning_effort", effort)
        result.setdefault("max_tokens", settings.local_model_max_tokens)
    return result
