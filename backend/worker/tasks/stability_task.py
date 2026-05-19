from worker.celery_app import celery_app
from agent.stability.analyzer import analyze
from worker.asyncio_runner import run_celery_async


@celery_app.task
def run_stability(dimensions: dict) -> dict:
    return {"result": run_celery_async(analyze(dimensions))}
