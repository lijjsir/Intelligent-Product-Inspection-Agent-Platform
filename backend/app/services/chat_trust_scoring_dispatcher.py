from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.services.task_execution_service import has_active_celery_worker


async def enqueue_chat_trust_scoring(payload: dict[str, Any] | None, *, logger: logging.Logger) -> str | None:
    if not payload:
        return None

    assistant_message_id = payload.get("assistant_message_id")
    trace_id = payload.get("trace_id")

    if await has_active_celery_worker():
        try:
            from worker.tasks.chat_trust_scoring_task import score_chat_message

            score_chat_message.apply_async(args=(payload,), ignore_result=True)
            return "celery"
        except Exception as exc:
            logger.warning(
                "trust scoring celery dispatch failed assistant_message_id=%s trace_id=%s: %s",
                assistant_message_id,
                trace_id,
                exc,
                exc_info=True,
            )

    try:
        from worker.tasks.chat_trust_scoring_task import _score_chat_message

        asyncio.create_task(_score_chat_message(payload))
        return "local_background"
    except Exception as exc:
        logger.warning(
            "trust scoring enqueue failed assistant_message_id=%s trace_id=%s: %s",
            assistant_message_id,
            trace_id,
            exc,
            exc_info=True,
        )
        return None
