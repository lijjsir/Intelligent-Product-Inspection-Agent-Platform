from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from app.core.datetime import utcnow_iso
from app.services.inspection_pipeline_service import run_inspection_pipeline
from app.repositories.task_repo import TaskRepository
from infra.database.session import get_session
from worker.celery_app import celery_app
from worker.tasks.inspection_task import run_inspection


def _inspect_celery_workers() -> bool:
    try:
        inspector = celery_app.control.inspect(timeout=0.5)
        if inspector is None:
            return False
        return bool(inspector.ping())
    except Exception:
        return False


async def has_active_celery_worker() -> bool:
    return await asyncio.to_thread(_inspect_celery_workers)


async def launch_task_execution(task_id: str, org_id: str) -> dict[str, Any]:
    payload = {"task_id": task_id, "org_id": org_id}
    use_celery = await has_active_celery_worker()
    mode = "celery" if use_celery else "local_background"

    async with get_session() as session:
        repo = TaskRepository(session)
        await repo.update_status(org_id, task_id, "queued")
        task = await repo.get(org_id, task_id)
        metadata = dict(task.meta_data or {}) if task else {}
        metadata["execution"] = {
            **dict(metadata.get("execution") or {}),
            "mode": mode,
            "job_id": None,
            "queued_at": utcnow_iso(),
        }
        await repo.patch_metadata(org_id, task_id, metadata)
        await session.commit()

    if use_celery:
        async_result = run_inspection.delay(payload)
        result = {"mode": "celery", "job_id": async_result.id, "status": "queued"}
        async with get_session() as session:
            repo = TaskRepository(session)
            task = await repo.get(org_id, task_id)
            metadata = dict(task.meta_data or {}) if task else {}
            metadata["execution"] = {
                **dict(metadata.get("execution") or {}),
                "job_id": async_result.id,
            }
            await repo.patch_metadata(org_id, task_id, metadata)
            await session.commit()
    else:
        asyncio.create_task(run_inspection_pipeline(task_id=task_id, org_id=org_id))
        result = {"mode": "local_background", "job_id": None, "status": "queued"}

    return result
