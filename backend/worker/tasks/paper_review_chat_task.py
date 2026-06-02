from __future__ import annotations

import logging
from typing import Any

from celery.signals import task_failure
from celery.exceptions import SoftTimeLimitExceeded

from app.core.config import settings
from app.repositories.chat_repo import ChatMessageRepository
from app.schemas.chat import ChatMessageSendRequest
from app.schemas.user import CurrentUser
from app.services.stream_service import chat_stream_broker
from infra.database.session import get_session
from worker.asyncio_runner import run_celery_async
from worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="worker.tasks.paper_review_chat_task.run_paper_review_chat_workflow",
    soft_time_limit=max(1, int(settings.paper_review_task_soft_time_limit_sec or 840)),
    time_limit=max(2, int(settings.paper_review_task_time_limit_sec or 900)),
)
def run_paper_review_chat_workflow(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    task_payload = dict(payload or {})
    try:
        return run_celery_async(_run_paper_review_chat_workflow(task_payload))
    except SoftTimeLimitExceeded as exc:
        run_celery_async(
            _persist_paper_review_failure(
                task_payload,
                exc,
                error_code="paper_review_worker_timeout",
            )
        )
        raise
    except Exception as exc:
        logger.exception(
            "paper review worker failed session_id=%s assistant_message_id=%s",
            task_payload.get("session_id"),
            task_payload.get("assistant_message_id"),
        )
        run_celery_async(_persist_paper_review_failure(task_payload, exc))
        raise


@task_failure.connect
def _persist_paper_review_worker_lost(
    sender: Any = None,
    task_id: str | None = None,
    exception: BaseException | None = None,
    args: tuple[Any, ...] | None = None,
    kwargs: dict[str, Any] | None = None,
    **_: Any,
) -> None:
    task_name = str(getattr(sender, "name", "") or "")
    if task_name != "worker.tasks.paper_review_chat_task.run_paper_review_chat_workflow":
        return
    if exception is None or exception.__class__.__name__ != "WorkerLostError":
        return
    payload: dict[str, Any] = {}
    if args and isinstance(args[0], dict):
        payload = dict(args[0])
    elif isinstance(kwargs, dict) and isinstance(kwargs.get("payload"), dict):
        payload = dict(kwargs["payload"])
    if not payload:
        return
    logger.error(
        "paper review worker process lost task_id=%s session_id=%s assistant_message_id=%s: %s",
        task_id,
        payload.get("session_id"),
        payload.get("assistant_message_id"),
        exception,
    )
    try:
        run_celery_async(
            _persist_paper_review_failure(
                payload,
                RuntimeError(str(exception) or "paper review worker process was killed"),
                error_code="paper_review_worker_lost",
            )
        )
    except Exception:
        logger.exception(
            "failed to persist paper review worker lost state task_id=%s assistant_message_id=%s",
            task_id,
            payload.get("assistant_message_id"),
        )


async def _run_paper_review_chat_workflow(payload: dict[str, Any]) -> dict[str, Any]:
    from app.services.chat_service import ChatService

    current = CurrentUser.model_validate(payload.get("current") or {})
    request = ChatMessageSendRequest.model_validate(payload.get("request") or {})
    service = ChatService(
        org_id=str(payload.get("org_id") or current.org_id),
        user_id=str(payload.get("user_id") or current.user_id),
        current=current,
    )
    await service._run_workflow(
        session_id=str(payload.get("session_id") or ""),
        assistant_message_id=str(payload.get("assistant_message_id") or ""),
        request=request,
        workflow_run_id=str(payload.get("workflow_run_id") or ""),
        current_user_seq_no=int(payload.get("current_user_seq_no") or 0),
        assistant_message_seq_no=int(payload.get("assistant_message_seq_no") or 0),
    )
    return {"status": "completed", "assistant_message_id": str(payload.get("assistant_message_id") or "")}


async def _persist_paper_review_failure(
    payload: dict[str, Any],
    exc: Exception,
    *,
    error_code: str = "paper_review_worker_failed",
) -> None:
    org_id = str(payload.get("org_id") or "")
    session_id = str(payload.get("session_id") or "")
    message_id = str(payload.get("assistant_message_id") or "")
    workflow_run_id = str(payload.get("workflow_run_id") or "")
    if not org_id or not message_id:
        return

    message = "Paper review failed before the final report was generated."
    detail = str(exc) or exc.__class__.__name__
    failure_payload = {
        "status": "failed",
        "message_type": "error",
        "ui_schema": "paper_review_error_v1",
        "workflow_run_id": workflow_run_id,
        "paper_review_status": {
            "phase": "failed",
            "status": "failed",
            "message": message,
        },
        "paper_review_error": {
            "error_code": error_code,
            "message": message,
            "detail": detail,
            "runtime_ready": False,
        },
    }
    async with get_session() as session:
        repo = ChatMessageRepository(session)
        await repo.update_assistant_message(
            org_id=org_id,
            message_id=message_id,
            content=message,
            message_type="error",
            payload=failure_payload,
        )
        await session.commit()
    await chat_stream_broker.publish(
        session_id,
        {
            "event": "run_failed",
            "session_id": session_id,
            "message_id": message_id,
            "workflow_run_id": workflow_run_id,
            "content": message,
            "payload": failure_payload,
        },
    )
