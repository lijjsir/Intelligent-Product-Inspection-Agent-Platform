from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
import logging

from fastapi import FastAPI

from app.core.logging import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    await seed_paper_templates_on_startup()
    yield


async def seed_paper_templates_on_startup() -> None:
    """Ensure paper template files and clause index are ready on startup.

    Pipeline: local assets -> MinIO (idempotent) -> MySQL + Qdrant (idempotent).
    Safe to call repeatedly — skips already-seeded data.
    """
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
