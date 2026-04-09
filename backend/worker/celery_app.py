from celery import Celery

from app.core.config import settings

celery_app = Celery("piap")
celery_app.conf.broker_url = settings.celery_broker_url
celery_app.conf.result_backend = settings.celery_result_backend
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.imports = (
    "worker.tasks.inspection_task",
    "worker.tasks.stability_task",
    "worker.tasks.alert_dispatch_task",
    "worker.tasks.report_generate_task",
    "worker.tasks.health_check_task",
    "worker.tasks.langfuse_sync_task",
)
