from celery import Celery

from app.core.config import settings

celery_app = Celery("piap")
celery_app.conf.broker_url = settings.celery_broker_url
celery_app.conf.result_backend = settings.celery_result_backend
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
