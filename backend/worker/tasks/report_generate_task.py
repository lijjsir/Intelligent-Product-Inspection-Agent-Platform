from __future__ import annotations

import logging

from app.repositories.export_job_repo import ExportJobRepository
from app.services.report_generation_service import generate_report
from infra.database.session import get_session
from worker.asyncio_runner import run_celery_async
from worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="worker.tasks.report_generate_task")
def generate_report_task(payload: dict) -> dict:
    return run_celery_async(_run(payload))


async def _run(payload: dict) -> dict:
    job_id = str(payload.get("job_id") or "")
    org_id = str(payload.get("org_id") or "")
    if not job_id or not org_id:
        return {"status": "skipped", "reason": "missing job_id or org_id"}

    try:
        await generate_report(job_id=job_id, org_id=org_id)
        return {"status": "success", "job_id": job_id}
    except Exception as exc:
        logger.exception("Report generation failed: job_id=%s", job_id)
        error_message = str(exc)
        async with get_session() as session:
            repo = ExportJobRepository(session)
            await repo.update_status(job_id, "failed", error_message=error_message)
            await session.commit()
        return {"status": "failed", "job_id": job_id, "error": error_message}
