from worker.celery_app import celery_app


@celery_app.task
def generate_report(result_id: str) -> str:
    return ""
