from agent.llm.health_checker import ModelHealthChecker
from app.repositories.model_config_repo import ModelConfigRepository
from app.services.model_config_service import ModelConfigService
from infra.database.session import get_session
from worker.celery_app import celery_app
from worker.asyncio_runner import run_celery_async


@celery_app.task(name="worker.tasks.health_check_task")
def run_model_health_check():
    return run_celery_async(_run_model_health_check())


async def _run_model_health_check() -> dict[str, int]:
    async with get_session() as session:
        repo = ModelConfigRepository(session)
        models = await repo.list_health_targets()
        runtime_models = [ModelConfigService.to_runtime_payload(item) for item in models]
        checked = await ModelHealthChecker().check(runtime_models)

        status_count = {"healthy": 0, "degraded": 0, "unhealthy": 0}
        index = {str(item.id): item for item in models}
        for item in checked:
            model = index.get(str(item.get("id") or ""))
            if not model:
                continue
            health_status = str(item.get("health_status") or "unknown")
            health_message = item.get("health_message")
            await repo.update_health(
                model,
                health_status=health_status,
                health_message=str(health_message) if health_message else None,
            )
            if health_status in status_count:
                status_count[health_status] += 1

        await session.commit()
        return {
            "checked": len(checked),
            "healthy": status_count["healthy"],
            "degraded": status_count["degraded"],
            "unhealthy": status_count["unhealthy"],
        }
