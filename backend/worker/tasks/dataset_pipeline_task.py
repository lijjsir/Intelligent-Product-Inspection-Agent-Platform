from __future__ import annotations

from worker.asyncio_runner import run_celery_async
from worker.celery_app import celery_app


@celery_app.task(name="worker.tasks.dataset_pipeline_task.run_dataset_import")
def run_dataset_import(task_payload: dict) -> dict:
    from app.services.dataset_service import run_dataset_import_pipeline

    dataset_id = str(task_payload.get("dataset_id") or "")
    job_id = str(task_payload.get("job_id") or "")
    upload_session_id = str(task_payload.get("upload_session_id") or "")
    bucket = str(task_payload.get("bucket") or "")
    object_key = str(task_payload.get("object_key") or "")
    org_id = str(task_payload.get("org_id") or "")
    user_id = str(task_payload.get("user_id") or "")
    if not all([dataset_id, job_id, upload_session_id, bucket, object_key, org_id, user_id]):
        raise ValueError("dataset_id, job_id, upload_session_id, bucket, object_key, org_id and user_id are required")
    return run_celery_async(
        run_dataset_import_pipeline(
            dataset_id=dataset_id,
            job_id=job_id,
            upload_session_id=upload_session_id,
            bucket=bucket,
            object_key=object_key,
            org_id=org_id,
            user_id=user_id,
        )
    )
