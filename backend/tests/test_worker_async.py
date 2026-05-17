from worker.asyncio_runner import run_celery_async


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
