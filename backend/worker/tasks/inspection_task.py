from worker.celery_app import celery_app
from worker.asyncio_runner import run_celery_async

from app.services.inspection_pipeline_service import run_inspection_pipeline


@celery_app.task
def run_inspection(task_payload: dict) -> dict:
    task_id = str(task_payload.get("task_id") or "")
    org_id = str(task_payload.get("org_id") or "")
    if not task_id or not org_id:
        raise ValueError("task_id and org_id are required")
    return run_celery_async(run_inspection_pipeline(task_id=task_id, org_id=org_id))
