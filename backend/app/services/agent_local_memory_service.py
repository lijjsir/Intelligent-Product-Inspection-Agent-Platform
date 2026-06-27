"""Agent-private, workflow-scoped local memory."""
from __future__ import annotations

import asyncio
import copy
import json
import logging
import time
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings

_LOCAL_FALLBACK: dict[str, tuple[float, list[dict[str, Any]]]] = {}
logger = logging.getLogger(__name__)


class AgentLocalMemoryService:
    """Stores short-term private agent context in Redis with TTL."""

    def __init__(
        self,
        redis_client: Redis | None = None,
        *,
        long_term_service: Any = None,
    ) -> None:
        self._redis = redis_client
        self._fallback = False
        self._long_term = long_term_service
        self.last_long_term_error: str | None = None
        self._redis_loop: asyncio.AbstractEventLoop | None = None

    @staticmethod
    def key(org_id: str, agent_id: str, workflow_run_id: str) -> str:
        return f"local_memory:{org_id}:{agent_id}:{workflow_run_id}"

    async def append(
        self,
        *,
        org_id: str,
        agent_id: str,
        workflow_run_id: str,
        item: dict[str, Any],
        ttl_seconds: int = 86400,
    ) -> None:
        key = self.key(org_id, agent_id, workflow_run_id)
        values = await self._read(key)
        values.append(copy.deepcopy(item))
        await self._write(key, values, ttl_seconds)

    async def snapshot(
        self,
        *,
        org_id: str,
        agent_id: str,
        workflow_run_id: str,
    ) -> list[dict[str, Any]]:
        return copy.deepcopy(await self._read(self.key(org_id, agent_id, workflow_run_id)))

    async def list_shareable(
        self,
        *,
        org_id: str,
        agent_id: str,
        workflow_run_id: str,
    ) -> list[dict[str, Any]]:
        items = await self.snapshot(
            org_id=org_id,
            agent_id=agent_id,
            workflow_run_id=workflow_run_id,
        )
        shareable = [
            item
            for item in items
            if item.get("shareable") is True and item.get("status", "active") == "active"
        ]
        if self._long_term is not None:
            try:
                shareable.extend(
                    await self._long_term.list_shareable(agent_id=agent_id)
                )
                self.last_long_term_error = None
            except Exception as exc:
                self.last_long_term_error = str(exc)
                logger.exception(
                    "Failed to read agent long-term memory org_id=%s agent_id=%s",
                    org_id,
                    agent_id,
                )
        return shareable

    async def write_long_term(self, **payload: Any) -> dict[str, Any]:
        if self._long_term is None:
            raise RuntimeError("agent long-term memory service is not configured")
        return await self._long_term.write(**payload)

    async def cleanup(self, *, org_id: str, agent_id: str, workflow_run_id: str) -> None:
        key = self.key(org_id, agent_id, workflow_run_id)
        client = await self._client()
        if client is not None:
            try:
                await client.delete(key)
            except (RedisError, OSError, RuntimeError):
                self._fallback = True
        _LOCAL_FALLBACK.pop(key, None)

    async def _read(self, key: str) -> list[dict[str, Any]]:
        client = await self._client()
        if client is not None:
            try:
                raw = await client.get(key)
                value = json.loads(raw) if raw else []
                return [dict(item) for item in value if isinstance(item, dict)]
            except (RedisError, OSError, RuntimeError, json.JSONDecodeError):
                self._fallback = True
        stored = _LOCAL_FALLBACK.get(key)
        if not stored or stored[0] <= time.monotonic():
            _LOCAL_FALLBACK.pop(key, None)
            return []
        return copy.deepcopy(stored[1])

    async def _write(self, key: str, values: list[dict[str, Any]], ttl_seconds: int) -> None:
        client = await self._client()
        if client is not None:
            try:
                await client.set(
                    key,
                    json.dumps(values, ensure_ascii=False, default=str),
                    ex=max(1, ttl_seconds),
                )
                return
            except (RedisError, OSError, RuntimeError):
                self._fallback = True
        _LOCAL_FALLBACK[key] = (
            time.monotonic() + max(1, ttl_seconds),
            copy.deepcopy(values),
        )

    async def _client(self) -> Redis | None:
        if self._fallback:
            return None
        if self._redis is not None:
            current_loop = asyncio.get_running_loop()
            if self._redis_loop is not None and self._redis_loop is not current_loop:
                await self._drop_redis_client()
            else:
                return self._redis
        if self._redis is None:
            try:
                self._redis = Redis.from_url(
                    settings.redis_url,
                    decode_responses=True,
                    socket_connect_timeout=0.2,
                    socket_timeout=0.5,
                )
                self._redis_loop = asyncio.get_running_loop()
                await self._redis.ping()
            except (RedisError, OSError, RuntimeError):
                self._fallback = True
                return None
        return self._redis

    async def _drop_redis_client(self) -> None:
        client = self._redis
        self._redis = None
        self._redis_loop = None
        if client is None:
            return
        try:
            await client.aclose()
        except Exception:
            logger.debug("Agent local memory Redis client close skipped", exc_info=True)
