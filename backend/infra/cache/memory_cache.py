from __future__ import annotations

import asyncio
import hashlib
import json
import time
from functools import wraps
from typing import Any, Callable, Coroutine, TypeVar

F = TypeVar("F", bound=Callable[..., Coroutine[Any, Any, Any]])


class MemoryCache:
    """Simple in-memory TTL cache. No Redis needed."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._store[key] = (time.monotonic() + ttl_seconds, value)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def delete_prefix(self, prefix: str) -> None:
        keys = [k for k in self._store if k.startswith(prefix)]
        for k in keys:
            del self._store[k]

    def clear(self) -> None:
        self._store.clear()

    @property
    def size(self) -> int:
        self._expire()
        return len(self._store)

    def _expire(self) -> None:
        now = time.monotonic()
        stale = [k for k, (exp, _) in self._store.items() if now > exp]
        for k in stale:
            del self._store[k]


# Global caches
_model_config_cache = MemoryCache()
_prompt_cache = MemoryCache()
_runtime_guard_cache = MemoryCache()
_rag_space_cache = MemoryCache()
_rag_result_cache = MemoryCache()
_embedding_cache = MemoryCache()
_celery_worker_cache = MemoryCache()


def stable_cache_key(prefix: str, *parts: Any) -> str:
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


def async_ttl_cache(
    cache: MemoryCache,
    key_fn: Callable[..., str],
    ttl_seconds: int = 30,
):
    """Decorator for async functions with in-memory TTL caching."""
    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache_key = key_fn(*args, **kwargs)
            cached = cache.get(cache_key)
            if cached is not None:
                return cached
            result = await func(*args, **kwargs)
            if result is not None:
                cache.set(cache_key, result, ttl_seconds)
            return result
        return wrapper  # type: ignore[return-value]
    return decorator


def invalidate_model_cache(org_id: str) -> None:
    _model_config_cache.delete_prefix(f"models:{org_id}")


def invalidate_prompt_cache(org_id: str, prompt_key: str | None = None) -> None:
    if prompt_key:
        _prompt_cache.delete(f"prompt:{org_id}:{prompt_key}")
    else:
        _prompt_cache.delete_prefix(f"prompt:{org_id}")


def invalidate_runtime_guard_cache(org_id: str) -> None:
    _runtime_guard_cache.delete_prefix(f"runtime_guard:{org_id}")
