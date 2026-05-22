from __future__ import annotations

from worker.asyncio_runner import run_celery_async
from worker.celery_app import celery_app


@celery_app.task(name="worker.tasks.algo_workspace_task.run_processing")
def run_processing(task_payload: dict) -> dict:
    from app.services.algo_workspace_service import run_algo_processing_pipeline

    return run_celery_async(
        run_algo_processing_pipeline(
            org_id=str(task_payload.get("org_id") or ""),
            user_id=str(task_payload.get("user_id") or ""),
            dataset_id=str(task_payload.get("dataset_id") or ""),
            processing_type=str(task_payload.get("processing_type") or ""),
            resource_id=str(task_payload.get("resource_id") or ""),
            job_id=str(task_payload.get("job_id") or ""),
            mode=str(task_payload.get("mode") or "local_background"),
        )
    )


@celery_app.task(name="worker.tasks.algo_workspace_task.run_resource")
def run_resource(task_payload: dict) -> dict:
    from app.services.algo_workspace_service import run_algo_resource_pipeline

    return run_celery_async(
        run_algo_resource_pipeline(
            org_id=str(task_payload.get("org_id") or ""),
            user_id=str(task_payload.get("user_id") or ""),
            resource_type=str(task_payload.get("resource_type") or ""),
            resource_id=str(task_payload.get("resource_id") or ""),
            mode=str(task_payload.get("mode") or "local_background"),
        )
    )


@celery_app.task(name="worker.tasks.algo_workspace_task.poll_gpu_jobs")
def poll_gpu_jobs(task_payload: dict | None = None) -> dict:
    from app.services.algo_workspace_service import poll_running_gpu_jobs_pipeline

    payload = task_payload or {}
    return run_celery_async(
        poll_running_gpu_jobs_pipeline(
            org_id=str(payload.get("org_id") or ""),
            user_id=str(payload.get("user_id") or ""),
        )
    )
