from worker.celery_app import celery_app
from agent.llm.langfuse_tracer import LangfuseTracer


@celery_app.task(name="worker.tasks.langfuse_sync_task")
def sync_langfuse_score(payload: dict | None = None):
    score_payload = payload or {}
    return {
        "status": "synced",
        "payload": LangfuseTracer().score(**score_payload),
    }
