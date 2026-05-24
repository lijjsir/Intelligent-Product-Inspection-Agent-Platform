import logging
from time import perf_counter

from worker.celery_app import celery_app
from worker.asyncio_runner import run_celery_async

from app.services.inspection_pipeline_service import run_inspection_pipeline

_logger = logging.getLogger(__name__)


@celery_app.task
def run_inspection(task_payload: dict) -> dict:
    task_id = str(task_payload.get("task_id") or "")
    org_id = str(task_payload.get("org_id") or "")
    if not task_id or not org_id:
        raise ValueError("task_id and org_id are required")
    started_at = perf_counter()
    result = run_celery_async(run_inspection_pipeline(task_id=task_id, org_id=org_id))
    _record_metrics_sync(org_id, success=result.get("status") != "failed",
                         latency_ms=int(round((perf_counter() - started_at) * 1000)))
    return result


def _record_metrics_sync(org_id: str, *, success: bool, latency_ms: int) -> None:
    try:
        run_celery_async(_record_metrics(org_id, success=success, latency_ms=latency_ms))
    except Exception:
        _logger.exception("Failed to record inspection agent metrics")


async def _record_metrics(org_id: str, *, success: bool, latency_ms: int) -> None:
    from infra.database.session import get_session
    from app.repositories.agent_management_repo import AgentExecutionMetricsRepository
    from app.repositories.agent_ops_repo import AgentDefinitionRepository

    async with get_session() as session:
        agent_repo = AgentDefinitionRepository(session, org_id)
        agent = await agent_repo.get_by_subgraph_key("inspection_task")
        if agent:
            metrics_repo = AgentExecutionMetricsRepository(session, org_id)
            await metrics_repo.update_metrics(str(agent.id), success=success, latency_ms=latency_ms)
            await session.commit()
