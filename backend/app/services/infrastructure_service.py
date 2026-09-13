from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from agent.llm.base_url_resolver import resolve_runtime_service_url
from app.core.config import settings
from app.repositories.model_config_repo import ModelConfigRepository
from app.schemas.infrastructure import InfrastructureComponentStatus, InfrastructureStatusResponse
from app.services.object_storage.factory import build_object_storage

logger = logging.getLogger(__name__)


class InfrastructureService:
    def __init__(self, session: AsyncSession, org_id: str | None = None):
        self._session = session
        self._org_id = org_id

    async def check_all(self) -> InfrastructureStatusResponse:
        checks = [
            self._check_mysql(),
            self._check_redis(),
            self._check_qdrant(),
            self._check_object_storage(),
        ]
        if self._org_id:
            checks.extend(
                [
                    self._check_chat_model(),
                    self._check_embedding_model(),
                    self._check_neo4j(),
                    self._check_celery(),
                ]
            )
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

    async def _check_chat_model(self) -> InfrastructureComponentStatus:
        return await self._check_model_group(
            name="Chat Model",
            kind="chat_model",
            model_types={"chat", "llm", "multimodal"},
            fallback_configured=bool(
                str(settings.deepseek_api_key or settings.volcengine_api_key or "").strip()
                and str(settings.deepseek_base_url or settings.volcengine_base_url or "").strip()
                and str(settings.deepseek_model_id or settings.volcengine_model_id or "").strip()
            ),
        )

    async def _check_embedding_model(self) -> InfrastructureComponentStatus:
        return await self._check_model_group(
            name="Embedding Model",
            kind="embedding_model",
            model_types={"embedding", "embed", "text_embedding"},
            fallback_configured=bool(
                str(settings.volcengine_api_key or "").strip()
                and str(settings.volcengine_base_url or "").strip()
                and str(settings.volcengine_embed_model or "").strip()
            ),
        )

    async def _check_model_group(
        self,
        *,
        name: str,
        kind: str,
        model_types: set[str],
        fallback_configured: bool,
    ) -> InfrastructureComponentStatus:
        checked_at = datetime.now(timezone.utc)
        try:
            repo = ModelConfigRepository(self._session)
            models = (
                await repo.list_active(self._org_id)
                if self._org_id
                else await repo.list_health_targets()
            )
            relevant = [
                item
                for item in models
                if str(getattr(item, "model_type", "") or "").strip().lower() in model_types
            ]
            if not relevant:
                if fallback_configured:
                    return InfrastructureComponentStatus(
                        name=name,
                        kind=kind,
                        status="degraded",
                        detail="仅配置了环境变量模型；尚未完成模型健康检查",
                        last_check_at=checked_at,
                    )
                return InfrastructureComponentStatus(
                    name=name,
                    kind=kind,
                    status="unhealthy",
                    detail="没有可用的活动模型配置",
                    last_check_at=checked_at,
                )

            statuses = [str(getattr(item, "health_status", "unknown") or "unknown").lower() for item in relevant]
            healthy = sum(status == "healthy" for status in statuses)
            unhealthy = sum(status == "unhealthy" for status in statuses)
            unknown = len(statuses) - healthy - unhealthy
            if healthy == len(statuses):
                status = "healthy"
            elif healthy > 0:
                status = "degraded"
            elif unhealthy == len(statuses):
                status = "unhealthy"
            else:
                status = "degraded"
            return InfrastructureComponentStatus(
                name=name,
                kind=kind,
                status=status,
                detail=(
                    f"active={len(statuses)}, healthy={healthy}, unhealthy={unhealthy}, "
                    f"pending={unknown}; run /api/v1/model-configs/health-check-all for a fresh probe"
                ),
                last_check_at=checked_at,
            )
        except Exception as exc:  # noqa: BLE001 - health checks must report dependency failures
            return InfrastructureComponentStatus(
                name=name,
                kind=kind,
                status="unhealthy",
                detail=str(exc),
                last_check_at=checked_at,
            )

    async def _check_neo4j(self) -> InfrastructureComponentStatus:
        checked_at = datetime.now(timezone.utc)
        started = time.perf_counter()
        graph_backend_requires_neo4j = (
            str(settings.memory_graph_read_backend or "").strip().lower() == "neo4j"
            or str(settings.memory_graph_write_backend or "").strip().lower() in {"neo4j", "dual"}
        )
        if not settings.neo4j_enabled:
            return InfrastructureComponentStatus(
                name="Neo4j",
                kind="graph_db",
                status="unhealthy" if graph_backend_requires_neo4j else "degraded",
                detail=(
                    "Neo4j is disabled but required by the configured memory graph backend"
                    if graph_backend_requires_neo4j
                    else "Neo4j is disabled by configuration; 当前配置的图数据库后端不要求启用 Neo4j (does not require it)"
                ),
                last_check_at=checked_at,
            )
        store = None
        try:
            from app.services.neo4j_memory_graph_store import Neo4jMemoryGraphStore

            store = Neo4jMemoryGraphStore(
                uri=settings.neo4j_uri,
                username=settings.neo4j_username,
                password=settings.neo4j_password,
                database=settings.neo4j_database,
            )
            await store.verify_connectivity()
            return InfrastructureComponentStatus(
                name="Neo4j",
                kind="graph_db",
                status="healthy",
                latency_ms=int((time.perf_counter() - started) * 1000),
                detail=f"database={settings.neo4j_database}",
                last_check_at=checked_at,
            )
        except Exception as exc:  # noqa: BLE001 - health checks must report dependency failures
            return InfrastructureComponentStatus(
                name="Neo4j",
                kind="graph_db",
                status="unhealthy",
                latency_ms=int((time.perf_counter() - started) * 1000),
                detail=str(exc),
                last_check_at=checked_at,
            )
        finally:
            driver = getattr(store, "_driver", None)
            close = getattr(driver, "close", None)
            if callable(close):
                try:
                    await close()
                except Exception:  # noqa: BLE001 - closing a failed probe must not mask its status
                    logger.debug("Neo4j driver close skipped", exc_info=True)

    async def _check_celery(self) -> InfrastructureComponentStatus:
        checked_at = datetime.now(timezone.utc)
        started = time.perf_counter()
        try:
            from app.services.task_execution_service import has_active_celery_worker

            active = await has_active_celery_worker()
            return InfrastructureComponentStatus(
                name="Celery",
                kind="queue",
                status="healthy" if active else "degraded",
                latency_ms=int((time.perf_counter() - started) * 1000),
                detail=(
                    "worker responded to ping"
                    if active
                    else "no active worker responded to ping; queued tasks may use local fallback"
                ),
                last_check_at=checked_at,
            )
        except Exception as exc:  # noqa: BLE001 - health checks must report dependency failures
            return InfrastructureComponentStatus(
                name="Celery",
                kind="queue",
                status="unhealthy",
                latency_ms=int((time.perf_counter() - started) * 1000),
                detail=str(exc),
                last_check_at=checked_at,
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
        qdrant_url = resolve_runtime_service_url(
            settings.qdrant_url,
            docker_base_url=settings.qdrant_docker_url,
        )
        url = f"{qdrant_url}/collections/{settings.qdrant_collection}"
        try:
            async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 404:
                    latency_ms = int((time.perf_counter() - started) * 1000)
                    return InfrastructureComponentStatus(
                        name="Qdrant",
                        kind="vector_db",
                        status="unhealthy",
                        latency_ms=latency_ms,
                        detail=(
                            f"endpoint={qdrant_url}, collection={settings.qdrant_collection}, "
                            "exists=False, error=collection_missing"
                        ),
                        last_check_at=checked_at,
                    )
                response.raise_for_status()
                payload = response.json().get("result") or {}
                status = payload.get("status") or "healthy"
                latency_ms = int((time.perf_counter() - started) * 1000)
                normalized_status = "healthy" if status in {"green", "ok", "healthy"} else "degraded"
                detail = f"endpoint={qdrant_url}, collection={settings.qdrant_collection}, status={status}"
                return InfrastructureComponentStatus(
                    name="Qdrant",
                    kind="vector_db",
                    status=normalized_status,
                    latency_ms=latency_ms,
                    detail=detail,
                    last_check_at=checked_at,
                )
        except httpx.ConnectError as exc:
            return InfrastructureComponentStatus(
                name="Qdrant",
                kind="vector_db",
                status="unhealthy",
                detail=_qdrant_connect_error_detail(qdrant_url, exc),
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
                await asyncio.to_thread(storage.ensure_bucket, settings.s3_bucket)
                latency_ms = int((time.perf_counter() - started) * 1000)
                return InfrastructureComponentStatus(
                    name="MinIO",
                    kind="storage",
                    status="healthy",
                    latency_ms=latency_ms,
                    detail=f"bucket={settings.s3_bucket}, endpoint={settings.s3_endpoint}",
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


def _qdrant_connect_error_detail(qdrant_url: str, exc: Exception) -> str:
    return (
        f"无法连接到 Qdrant 端点 {qdrant_url}。"
        "如果 backend 在宿主机运行且依赖 docker-compose 中的 Qdrant，请使用 http://127.0.0.1:63330；"
        "如果 backend 在 Docker 容器中运行，请使用 http://qdrant:6333。"
        f" 原始错误：{exc}"
    )
