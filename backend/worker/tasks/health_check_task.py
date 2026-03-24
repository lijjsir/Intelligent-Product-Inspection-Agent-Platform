from worker.celery_app import celery_app


@celery_app.task(name="worker.tasks.health_check_task")
def run_model_health_check():
    return {"status": "queued"}

