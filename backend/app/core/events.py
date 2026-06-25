from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
import logging

from fastapi import FastAPI

from app.core.config import settings
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)


async def check_neo4j_on_startup() -> None:
    try:
        from app.services.graph_health_service import GraphHealthService
        await GraphHealthService().assert_neo4j_ready()
        logger.info("Neo4j connectivity check passed")
    except Exception as exc:
        logger.critical("Neo4j startup check failed: %s", exc)
        raise


async def _ensure_minio_buckets_on_startup() -> None:
    backend = str(settings.object_storage_backend or "").strip().lower()
    if backend != "minio":
        return
    try:
        from app.services.object_storage.factory import build_object_storage

        storage = build_object_storage()
        import asyncio

        for bucket in (settings.s3_bucket, settings.rag_storage_bucket):
            if bucket:
                await asyncio.to_thread(storage.ensure_bucket, bucket)
                logger.info("MinIO bucket ensured: %s", bucket)
    except Exception as exc:
        logger.warning("MinIO bucket initialization skipped: %s", exc)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    await check_neo4j_on_startup()
    await _ensure_minio_buckets_on_startup()
    await seed_paper_templates_on_startup()
    await log_paper_review_runtime_status()
    yield


async def seed_paper_templates_on_startup() -> None:
    """Ensure paper template files and clause index are ready on startup.

    Pipeline: local assets -> MinIO (idempotent) -> MySQL + Qdrant (idempotent).
    Safe to call repeatedly — skips already-seeded data.
    """
    if not settings.paper_review_enabled:
        logger.info("paper template bootstrap skipped: paper review disabled")
        return

    try:
        from agent.tools.paper_template_storage import ensure_paper_templates_ready

        result = await ensure_paper_templates_ready()
        logger.info(
            "paper template bootstrap complete template_id=%s minio_files=%d index_status=%s",
            result.get("template_id"),
            len(result.get("files") or []),
            result.get("index_status", "unknown"),
        )
    except Exception as exc:
        logger.warning("paper template bootstrap skipped: %s", exc)


async def log_paper_review_runtime_status() -> None:
    if not settings.paper_review_enabled:
        logger.info("paper review runtime check skipped: paper review disabled")
        return

    try:
        from app.services.paper_review_runtime_service import PaperReviewRuntimeService

        result = await PaperReviewRuntimeService.diagnose()
        if result.get("ok"):
            logger.info("paper review runtime ready engines=%s", result.get("engines_used"))
            return
        logger.warning("paper review runtime not ready details=%s", result.get("engine_status"))
    except Exception as exc:
        logger.warning("paper review runtime health check failed: %s", exc)
