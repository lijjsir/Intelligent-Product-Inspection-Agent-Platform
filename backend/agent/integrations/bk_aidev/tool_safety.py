"""Tool output limiting and sensitive-value redaction."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolSafetyPolicy:
    max_output_chars: int = 100_000
    sensitive_values: tuple[str, ...] = ()


_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "password",
    "private_key",
    "secret",
    "token",
}

_SENSITIVE_KEY_SUFFIXES = (
    "_api_key",
    "_credential",
    "_password",
    "_private_key",
    "_secret",
    "_token",
)


def configured_tool_safety_policy(
    additional_values: Iterable[Any] | None = None,
) -> ToolSafetyPolicy:
    from app.core.config import settings

    configured = [
        item.strip()
        for item in settings.tool_sensitive_values_csv.split(",")
        if item.strip()
    ]
    additional = [str(item) for item in (additional_values or []) if str(item)]
    return ToolSafetyPolicy(
        max_output_chars=settings.tool_output_max_chars,
        sensitive_values=tuple(configured + additional),
    )


def sanitize_tool_output(value: Any, policy: ToolSafetyPolicy) -> dict[str, Any] | None:
    if value is None:
        return None

    redacted = _redact(value, policy.sensitive_values)
    normalized = _normalize(redacted)
    serialized = json.dumps(normalized, ensure_ascii=False, default=str)
    max_chars = max(256, int(policy.max_output_chars))
    if len(serialized) <= max_chars:
        if isinstance(normalized, dict):
            return normalized
        if isinstance(normalized, list):
            return {"items": normalized}
        return {"content": normalized}

    return {
        "truncated": True,
        "original_chars": len(serialized),
        "content": serialized[:max_chars],
    }


def _redact(value: Any, sensitive_values: tuple[str, ...]) -> Any:
    secrets = tuple(item for item in sensitive_values if len(item) >= 3)
    if isinstance(value, str):
        result = value
        for secret in secrets:
            result = result.replace(secret, "***REDACTED***")
        return result
    if isinstance(value, dict):
        return {
            str(key): (
                "***REDACTED***"
                if _is_sensitive_key(str(key)) and item is not None
                else _redact(item, secrets)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_redact(item, secrets) for item in value]
    return value


def _normalize(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_normalize(item) for item in value]
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _normalize(model_dump(mode="json"))
    return str(value)


def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_")
    return normalized in _SENSITIVE_KEYS or normalized.endswith(_SENSITIVE_KEY_SUFFIXES)
