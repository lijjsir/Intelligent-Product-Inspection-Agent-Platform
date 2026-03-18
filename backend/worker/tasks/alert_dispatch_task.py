from worker.celery_app import celery_app


@celery_app.task
def dispatch_alert(alert_id: str) -> None:
    return None
