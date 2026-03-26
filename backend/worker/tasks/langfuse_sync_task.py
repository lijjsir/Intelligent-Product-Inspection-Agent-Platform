from worker.celery_app import celery_app
from agent.llm.langfuse_tracer import LangfuseTracer


@celery_app.task(name="worker.tasks.langfuse_sync_task")
def sync_langfuse_score(payload: dict | None = None):
    score_payload = payload or {}
    synced = LangfuseTracer().sync_score(score_payload)
    return {
        "status": "synced" if synced.get("synced") else "skipped",
        "payload": synced,
    }
