from worker.celery_app import celery_app
from agent.stability.analyzer import analyze


@celery_app.task
def run_stability(dimensions: dict) -> dict:
    return {"result": analyze(dimensions)}
