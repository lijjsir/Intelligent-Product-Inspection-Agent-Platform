"""Redis-backed task blackboard with a process-local development fallback."""
from __future__ import annotations

import asyncio
import copy
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable

from redis.asyncio import Redis
from redis.exceptions import RedisError, WatchError

from app.core.config import settings

logger = logging.getLogger(__name__)

_FALLBACK_DATA: dict[str, tuple[float, dict[str, Any]]] = {}
_FALLBACK_LOCK = asyncio.Lock()
_REDIS_RETRY_AFTER = 0.0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskBlackboardService:
    """Stores task-scoped orchestration state.

    Redis is the primary store. When Redis is unavailable, the service falls
    back to a shared in-process store so local development and unit tests keep
    working. The fallback preserves TTL semantics but is not multi-worker safe.
    """

    def __init__(
        self,
        redis_client: Redis | None = None,
        *,
        redis_url: str | None = None,
        allow_memory_fallback: bool = True,
    ) -> None:
        self._redis = redis_client
        self._redis_url = redis_url or settings.redis_url
        self._allow_memory_fallback = allow_memory_fallback
        self._force_fallback = False

    @staticmethod
    def key(org_id: str, workflow_run_id: str) -> str:
        return f"blackboard:{org_id}:{workflow_run_id}"

    async def init_blackboard(
        self,
        org_id: str,
        workflow_run_id: str,
        task_id: str | None,
        ttl_seconds: int,
    ) -> None:
        now = _utc_now()
        payload = {
            "workflow_run_id": workflow_run_id,
            "task_id": task_id,
            "org_id": org_id,
            "global_plan": {},
            "global_state": {
                "status": "initialized",
                "completed_steps": [],
                "failed_steps": [],
                "blocked_steps": [],
                "started_at": now,
                "updated_at": now,
            },
            "artifacts": [],
            "observations": [],
            "candidate_sources": [],
            "created_at": now,
            "updated_at": now,
            "ttl_seconds": max(1, int(ttl_seconds)),
        }
        await self._write(self.key(org_id, workflow_run_id), payload)

    async def set_global_plan(
        self,
        org_id: str,
        workflow_run_id: str,
        plan: dict,
    ) -> None:
        await self._mutate(
            self.key(org_id, workflow_run_id),
            lambda payload: payload.update(global_plan=copy.deepcopy(plan)),
        )

    async def update_global_state(
        self,
        org_id: str,
        workflow_run_id: str,
        patch: dict,
    ) -> None:
        def apply(payload: dict[str, Any]) -> None:
            state = dict(payload.get("global_state") or {})
            state.update(copy.deepcopy(patch))
            state["updated_at"] = _utc_now()
            payload["global_state"] = state

        await self._mutate(self.key(org_id, workflow_run_id), apply)

    async def append_artifact(
        self,
        org_id: str,
        workflow_run_id: str,
        artifact: dict,
    ) -> None:
        def apply(payload: dict[str, Any]) -> None:
            artifacts = list(payload.get("artifacts") or [])
            artifact_id = str(artifact.get("artifact_id") or "")
            if artifact_id and any(str(item.get("artifact_id") or "") == artifact_id for item in artifacts):
                return
            artifacts.append(copy.deepcopy(artifact))
            payload["artifacts"] = artifacts

        await self._mutate(self.key(org_id, workflow_run_id), apply)

    async def append_observation(
        self,
        org_id: str,
        workflow_run_id: str,
        observation: dict,
    ) -> None:
        def apply(payload: dict[str, Any]) -> None:
            observations = list(payload.get("observations") or [])
            observations.append(copy.deepcopy(observation))
            payload["observations"] = observations

        await self._mutate(self.key(org_id, workflow_run_id), apply)

    async def append_candidate_source(
        self,
        org_id: str,
        workflow_run_id: str,
        candidate_source: dict,
    ) -> None:
        def apply(payload: dict[str, Any]) -> None:
            sources = list(payload.get("candidate_sources") or [])
            source_id = str(candidate_source.get("source_artifact_id") or "")
            if source_id and any(str(item.get("source_artifact_id") or "") == source_id for item in sources):
                return
            sources.append(copy.deepcopy(candidate_source))
            payload["candidate_sources"] = sources

        await self._mutate(self.key(org_id, workflow_run_id), apply)

    async def list_artifacts(
        self,
        org_id: str,
        workflow_run_id: str,
        artifact_type: str | None = None,
    ) -> list[dict]:
        snapshot = await self.snapshot(org_id, workflow_run_id)
        artifacts = [dict(item) for item in snapshot.get("artifacts") or [] if isinstance(item, dict)]
        if artifact_type is None:
            return artifacts
        return [item for item in artifacts if item.get("type") == artifact_type]

    async def get_latest_artifact(
        self,
        org_id: str,
        workflow_run_id: str,
        artifact_type: str,
    ) -> dict | None:
        artifacts = await self.list_artifacts(org_id, workflow_run_id, artifact_type)
        return artifacts[-1] if artifacts else None

    async def snapshot(self, org_id: str, workflow_run_id: str) -> dict:
        payload = await self._read(self.key(org_id, workflow_run_id))
        return copy.deepcopy(payload or {})

    async def cleanup(self, org_id: str, workflow_run_id: str) -> None:
        key = self.key(org_id, workflow_run_id)
        if await self._redis_available():
            try:
                await self._redis.delete(key)
                return
            except (RedisError, OSError) as exc:
                self._mark_redis_unavailable(exc)
        async with _FALLBACK_LOCK:
            _FALLBACK_DATA.pop(key, None)

    async def _mutate(
        self,
        key: str,
        mutator: Callable[[dict[str, Any]], None],
    ) -> None:
        if await self._redis_available():
            try:
                for _attempt in range(4):
                    async with self._redis.pipeline(transaction=True) as pipe:
                        try:
                            await pipe.watch(key)
                            raw = await pipe.get(key)
                            payload = self._decode(raw) or {}
                            if not payload:
                                raise KeyError(f"task blackboard does not exist: {key}")
                            mutator(payload)
                            payload["updated_at"] = _utc_now()
                            ttl_seconds = max(1, int(payload.get("ttl_seconds") or 86400))
                            pipe.multi()
                            pipe.set(key, self._encode(payload), ex=ttl_seconds)
                            await pipe.execute()
                            return
                        except WatchError:
                            continue
                raise RuntimeError(f"task blackboard update conflict: {key}")
            except (RedisError, OSError) as exc:
                self._mark_redis_unavailable(exc)

        async with _FALLBACK_LOCK:
            self._purge_expired_fallback()
            stored = _FALLBACK_DATA.get(key)
            if stored is None:
                raise KeyError(f"task blackboard does not exist: {key}")
            _expires_at, existing = stored
            payload = copy.deepcopy(existing)
            mutator(payload)
            payload["updated_at"] = _utc_now()
            ttl_seconds = max(1, int(payload.get("ttl_seconds") or 86400))
            _FALLBACK_DATA[key] = (time.monotonic() + ttl_seconds, payload)

    async def _write(self, key: str, payload: dict[str, Any]) -> None:
        ttl_seconds = max(1, int(payload.get("ttl_seconds") or 86400))
        if await self._redis_available():
            try:
                await self._redis.set(key, self._encode(payload), ex=ttl_seconds)
                return
            except (RedisError, OSError) as exc:
                self._mark_redis_unavailable(exc)

        async with _FALLBACK_LOCK:
            self._purge_expired_fallback()
            _FALLBACK_DATA[key] = (
                time.monotonic() + ttl_seconds,
                copy.deepcopy(payload),
            )

    async def _read(self, key: str) -> dict[str, Any] | None:
        if await self._redis_available():
            try:
                return self._decode(await self._redis.get(key))
            except (RedisError, OSError) as exc:
                self._mark_redis_unavailable(exc)

        async with _FALLBACK_LOCK:
            self._purge_expired_fallback()
            stored = _FALLBACK_DATA.get(key)
            return copy.deepcopy(stored[1]) if stored else None

    async def _redis_available(self) -> bool:
        global _REDIS_RETRY_AFTER
        if self._force_fallback:
            return False
        if self._redis is not None:
            return True
        if time.monotonic() < _REDIS_RETRY_AFTER:
            return False
        try:
            self._redis = Redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=0.2,
                socket_timeout=0.5,
            )
            await self._redis.ping()
            return True
        except (RedisError, OSError) as exc:
            self._mark_redis_unavailable(exc)
            return False

    def _mark_redis_unavailable(self, exc: Exception) -> None:
        global _REDIS_RETRY_AFTER
        if not self._allow_memory_fallback:
            raise exc
        self._force_fallback = True
        _REDIS_RETRY_AFTER = time.monotonic() + 30.0
        logger.warning("Task blackboard Redis unavailable; using process-local fallback: %s", exc)

    @staticmethod
    def _encode(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)

    @staticmethod
    def _decode(raw: Any) -> dict[str, Any] | None:
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        value = json.loads(str(raw))
        return value if isinstance(value, dict) else None

    @staticmethod
    def _purge_expired_fallback() -> None:
        now = time.monotonic()
        expired = [key for key, (expires_at, _payload) in _FALLBACK_DATA.items() if expires_at <= now]
        for key in expired:
            _FALLBACK_DATA.pop(key, None)
