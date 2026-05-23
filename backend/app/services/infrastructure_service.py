from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.schemas.infrastructure import InfrastructureComponentStatus, InfrastructureStatusResponse
from app.services.object_storage.factory import build_object_storage


class InfrastructureService:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def check_all(self) -> InfrastructureStatusResponse:
        checks = [
            self._check_mysql(),
            self._check_redis(),
            self._check_qdrant(),
            self._check_object_storage(),
        ]
        results = await asyncio.gather(*checks, return_exceptions=True)
        checked_at = datetime.now(timezone.utc)
        components: list[InfrastructureComponentStatus] = []
        for item in results:
            if isinstance(item, InfrastructureComponentStatus):
                components.append(item)
            else:
                components.append(
                    InfrastructureComponentStatus(
                        name="Unknown",
                        kind="unknown",
                        status="unhealthy",
                        detail=str(item),
                        last_check_at=checked_at,
                    )
                )
        return InfrastructureStatusResponse(
            components=components,
            overall_status=self._resolve_overall_status(components),
            checked_at=checked_at,
        )

    def _resolve_overall_status(self, components: list[InfrastructureComponentStatus]) -> str:
        states = {component.status for component in components}
        if "unhealthy" in states:
            return "unhealthy"
        if "degraded" in states:
            return "degraded"
        if "healthy" in states:
            return "healthy"
        return "unknown"

    async def _check_mysql(self) -> InfrastructureComponentStatus:
        started = time.perf_counter()
        checked_at = datetime.now(timezone.utc)
        try:
            await self._session.execute(text("SELECT 1"))
            latency_ms = int((time.perf_counter() - started) * 1000)
            return InfrastructureComponentStatus(
                name="MySQL",
                kind="database",
                status="healthy",
                latency_ms=latency_ms,
                detail="primary database reachable",
                last_check_at=checked_at,
            )
        except Exception as exc:
            return InfrastructureComponentStatus(
                name="MySQL",
                kind="database",
                status="unhealthy",
                detail=str(exc),
                last_check_at=checked_at,
            )

    async def _check_redis(self) -> InfrastructureComponentStatus:
        started = time.perf_counter()
        checked_at = datetime.now(timezone.utc)
        client = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            pong = await client.ping()
            info = await client.info(section="memory")
            latency_ms = int((time.perf_counter() - started) * 1000)
            detail = f"ping={pong}, used_memory={info.get('used_memory_human', 'unknown')}"
            return InfrastructureComponentStatus(
                name="Redis",
                kind="cache",
                status="healthy",
                latency_ms=latency_ms,
                detail=detail,
                last_check_at=checked_at,
            )
        except Exception as exc:
            return InfrastructureComponentStatus(
                name="Redis",
                kind="cache",
                status="unhealthy",
                detail=str(exc),
                last_check_at=checked_at,
            )
        finally:
            await client.aclose()

    async def _check_qdrant(self) -> InfrastructureComponentStatus:
        started = time.perf_counter()
        checked_at = datetime.now(timezone.utc)
        headers = {"api-key": settings.qdrant_api_key} if settings.qdrant_api_key else None
        url = f"{settings.qdrant_url.rstrip('/')}/collections/{settings.qdrant_collection}"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                payload = response.json().get("result") or {}
                status = payload.get("status") or "healthy"
                latency_ms = int((time.perf_counter() - started) * 1000)
                normalized_status = "healthy" if status in {"green", "ok", "healthy"} else "degraded"
                detail = f"collection={settings.qdrant_collection}, status={status}"
                return InfrastructureComponentStatus(
                    name="Qdrant",
                    kind="vector_db",
                    status=normalized_status,
                    latency_ms=latency_ms,
                    detail=detail,
                    last_check_at=checked_at,
                )
        except Exception as exc:
            return InfrastructureComponentStatus(
                name="Qdrant",
                kind="vector_db",
                status="unhealthy",
                detail=str(exc),
                last_check_at=checked_at,
            )

    async def _check_object_storage(self) -> InfrastructureComponentStatus:
        started = time.perf_counter()
        checked_at = datetime.now(timezone.utc)
        backend = str(settings.object_storage_backend or "local").strip().lower()
        try:
            storage = build_object_storage()
            if backend == "minio":
                bucket_exists = await asyncio.to_thread(storage.bucket_exists, settings.s3_bucket)
                latency_ms = int((time.perf_counter() - started) * 1000)
                return InfrastructureComponentStatus(
                    name="MinIO",
                    kind="storage",
                    status="healthy" if bucket_exists else "degraded",
                    latency_ms=latency_ms,
                    detail=f"bucket={settings.s3_bucket}, exists={bucket_exists}",
                    last_check_at=checked_at,
                )
            upload_dir = Path(settings.local_upload_dir)
            exists = upload_dir.exists()
            writable = exists and upload_dir.is_dir()
            latency_ms = int((time.perf_counter() - started) * 1000)
            return InfrastructureComponentStatus(
                name="Local Storage",
                kind="storage",
                status="healthy" if writable else "degraded",
                latency_ms=latency_ms,
                detail=f"path={upload_dir}, exists={exists}",
                last_check_at=checked_at,
            )
        except Exception as exc:
            return InfrastructureComponentStatus(
                name="MinIO" if backend == "minio" else "Local Storage",
                kind="storage",
                status="unhealthy",
                detail=str(exc),
                last_check_at=checked_at,
            )
