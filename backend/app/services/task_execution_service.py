from __future__ import annotations

import asyncio
from typing import Any

from app.services.inspection_pipeline_service import run_inspection_pipeline
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
    if await has_active_celery_worker():
        async_result = run_inspection.delay(payload)
        return {"mode": "celery", "job_id": async_result.id}

    asyncio.create_task(run_inspection_pipeline(task_id=task_id, org_id=org_id))
    return {"mode": "local_background", "job_id": None}
