from worker.asyncio_runner import run_celery_async
from infra.cache.memory_cache import _celery_worker_cache


def test_run_celery_async_resets_database_pool_around_task(monkeypatch):
    calls: list[object] = []

    async def fake_reset(*, close: bool):
        calls.append(("reset", close))

    async def fake_task():
        calls.append("body")
        return {"status": "ok"}

    monkeypatch.setattr("worker.asyncio_runner.reset_async_engine_pool", fake_reset)

    result = run_celery_async(fake_task())

    assert result == {"status": "ok"}
    assert calls == [("reset", False), "body", ("reset", True)]


def test_has_active_celery_worker_uses_short_ttl_cache(monkeypatch):
    from app.services import task_execution_service

    _celery_worker_cache.clear()
    calls: list[str] = []

    def fake_inspect():
        calls.append("inspect")
        return True

    monkeypatch.setattr(task_execution_service, "_inspect_celery_workers", fake_inspect)

    first = run_celery_async(task_execution_service.has_active_celery_worker())
    second = run_celery_async(task_execution_service.has_active_celery_worker())

    assert first is True
    assert second is True
    assert calls == ["inspect"]
