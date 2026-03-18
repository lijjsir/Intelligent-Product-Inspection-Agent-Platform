from celery import Celery


celery_app = Celery("piap")
celery_app.conf.broker_url = "redis://localhost:6379/0"
celery_app.conf.result_backend = "redis://localhost:6379/0"
