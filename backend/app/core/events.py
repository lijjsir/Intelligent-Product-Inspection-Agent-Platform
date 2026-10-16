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
        logger.warning("Neo4j startup check skipped: %s", exc)


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
    yield
