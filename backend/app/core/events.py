from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
import logging

from fastapi import FastAPI

from app.core.logging import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    await recover_interrupted_chat_workflows_on_startup()
    await seed_paper_templates_on_startup()
    await log_paper_review_runtime_status()
    yield


async def recover_interrupted_chat_workflows_on_startup() -> None:
    try:
        from app.services.chat_service import mark_interrupted_chat_workflows_on_startup

        recovered = await mark_interrupted_chat_workflows_on_startup()
        if recovered:
            logger.warning("recovered %d interrupted chat workflow message(s) on startup", recovered)
    except Exception as exc:
        logger.warning("chat workflow recovery skipped: %s", exc)


async def seed_paper_templates_on_startup() -> None:
    """Ensure paper template files and clause index are ready on startup.

    Pipeline: local assets -> MinIO (idempotent) -> MySQL + Qdrant (idempotent).
    Safe to call repeatedly — skips already-seeded data.
    """
    try:
        from agent.tools.paper_template_storage import ensure_paper_templates_ready

        org_id = await resolve_paper_template_embedding_org_id()
        result = await ensure_paper_templates_ready(org_id=org_id)
        logger.info(
            "paper template bootstrap complete template_id=%s minio_files=%d index_status=%s",
            result.get("template_id"),
            len(result.get("files") or []),
            result.get("index_status", "unknown"),
        )
    except Exception as exc:
        logger.warning("paper template bootstrap skipped: %s", exc)


async def resolve_paper_template_embedding_org_id() -> str | None:
    try:
        from sqlalchemy import select

        from app.models.model_config import ModelConfig
        from infra.database.session import get_session

        async with get_session() as session:
            result = await session.execute(
                select(ModelConfig.org_id)
                .where(
                    ModelConfig.is_active.is_(True),
                    ModelConfig.model_type.in_(["embedding", "embed", "text_embedding"]),
                    ModelConfig.org_id.is_not(None),
                )
                .order_by(ModelConfig.priority.asc(), ModelConfig.updated_at.desc())
                .limit(1)
            )
            org_id = result.scalar_one_or_none()
            if org_id:
                logger.info("paper template bootstrap using embedding org_id=%s", org_id)
            return str(org_id) if org_id else None
    except Exception as exc:
        logger.warning("paper template embedding org resolve skipped: %s", exc)
        return None


async def log_paper_review_runtime_status() -> None:
    try:
        from app.services.paper_review_runtime_service import PaperReviewRuntimeService

        result = await PaperReviewRuntimeService.diagnose()
        if result.get("ok"):
            logger.info("paper review runtime ready engines=%s", result.get("engines_used"))
            return
        logger.warning("paper review runtime not ready details=%s", result.get("engine_status"))
    except Exception as exc:
        logger.warning("paper review runtime health check failed: %s", exc)
