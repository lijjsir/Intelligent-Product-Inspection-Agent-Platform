from celery import Celery

from app.core.config import settings

celery_app = Celery("piap")
celery_app.conf.broker_url = settings.celery_broker_url
celery_app.conf.result_backend = settings.celery_result_backend
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.imports = (
    "worker.tasks.alert_dispatch_task",
    "worker.tasks.health_check_task",
    "worker.tasks.chat_trust_scoring_task",
    "worker.tasks.inspection_task",
    "worker.tasks.dataset_pipeline_task",
    "worker.tasks.algo_workspace_task",
    "worker.tasks.langfuse_sync_task",
    "worker.tasks.report_generate_task",
    "worker.tasks.stability_task",
    "worker.tasks.memory_sync_outbox_task",
    "worker.tasks.standard_auto_reindex_task",
)

celery_app.conf.beat_schedule = {
    "model-health-check": {
        "task": "worker.tasks.health_check_task.run_model_health_check",
        "schedule": 300.0,
    },
    "poll-gpu-jobs": {
        "task": "worker.tasks.algo_workspace_task.poll_gpu_jobs",
        "schedule": settings.gpu_job_poll_interval_sec,
    },
    "poll-gpu-nodes": {
        "task": "worker.tasks.algo_workspace_task.poll_gpu_nodes",
        "schedule": settings.gpu_metric_poll_interval_sec,
    },
    "memory-sync-outbox-dispatch": {
        "task": "worker.tasks.memory_sync_outbox_task.dispatch_memory_sync_outbox",
        "schedule": 60.0,
    },
    "standard-auto-reindex": {
        "task": "worker.tasks.standard_auto_reindex_task.run_standard_auto_reindex",
        "schedule": 43200.0,  # every 12 hours
    },
}

# Import task modules eagerly so the worker always registers named tasks.
from worker.tasks import (  # noqa: E402,F401
    alert_dispatch_task,
    algo_workspace_task,
    dataset_pipeline_task,
    chat_trust_scoring_task,
    health_check_task,
    inspection_task,
    langfuse_sync_task,
    memory_sync_outbox_task,
    report_generate_task,
    stability_task,
    standard_auto_reindex_task,
)
