from __future__ import annotations

import logging

from app.repositories.chat_repo import ChatMessageRepository
from app.repositories.chat_score_repo import ChatMessageScoreRepository
from app.services.chat_trust_scoring_service import ChatTrustScoringService, trust_payload_from_score
from infra.database.session import get_session
from worker.celery_app import celery_app
from worker.asyncio_runner import run_celery_async

logger = logging.getLogger(__name__)


@celery_app.task(name="worker.tasks.chat_trust_scoring_task")
def score_chat_message(payload: dict | None = None) -> dict:
    return run_celery_async(_score_chat_message(payload or {}))


async def _resolve_review_config(org_id: str) -> dict:
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            async with get_session() as resolve_session:
                return await ChatTrustScoringService.resolve_review_model(resolve_session, org_id)
        except Exception as exc:
            last_error = exc
            logger.warning("review model resolution failed attempt=%s org_id=%s: %s", attempt + 1, org_id, exc)
    if last_error:
        logger.warning("review model resolution disabled org_id=%s: %s", org_id, last_error)
    return {}


async def _score_chat_message(payload: dict) -> dict:
    org_id = str(payload.get("org_id") or "")
    message_id = str(payload.get("assistant_message_id") or "")
    if not org_id or not message_id:
        return {"status": "skipped", "reason": "missing org_id or assistant_message_id"}

    review_config = await _resolve_review_config(org_id)

    score = await ChatTrustScoringService(**review_config).score_answer(
        org_id=org_id,
        session_id=str(payload.get("session_id") or ""),
        user_id=str(payload.get("user_id") or "") or None,
        assistant_message_id=message_id,
        input_text=str(payload.get("input_text") or ""),
        output_text=str(payload.get("output_text") or ""),
        citations=list(payload.get("citations") or []),
        trace_id=str(payload.get("trace_id") or "") or None,
        observation_id=str(payload.get("observation_id") or "") or None,
        model_key=str(payload.get("model_key") or "") or None,
    )
    async with get_session() as session:
        score_row = await ChatMessageScoreRepository(session).upsert_by_message_version(score)
        message_repo = ChatMessageRepository(session)
        message = await message_repo.get(org_id, message_id)
        if message:
            message_payload = dict(message.payload or {})
            message_payload["trust_scoring"] = trust_payload_from_score(score)
            await message_repo.update_assistant_message(
                org_id=org_id,
                message_id=message_id,
                content=str(message.content or ""),
                message_type=str(message.message_type or "assistant_text"),
                payload=message_payload,
            )
        await session.commit()
    return {"status": "scored", "score_id": str(score_row.id), "score_status": score["status"]}
