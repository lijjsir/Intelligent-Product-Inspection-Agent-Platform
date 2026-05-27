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
    try:
        from agent.tools.paper_template_storage import seed_builtin_paper_templates

        result = seed_builtin_paper_templates()
        logger.info(
            "paper template seed completed template_id=%s file_count=%s",
            result.get("template_id"),
            len(result.get("files") or []),
        )
    except Exception as exc:
        logger.warning("paper template seed skipped: %s", exc)
