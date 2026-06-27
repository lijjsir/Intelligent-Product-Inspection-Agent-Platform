from worker.tasks import inspection_task


def test_run_inspection_normalizes_missing_pipeline_result(monkeypatch):
    async def fake_pipeline(*, task_id: str, org_id: str):
        return None

    def fake_run_celery_async(awaitable):
        awaitable.close()
        return None

    recorded: list[dict] = []
    monkeypatch.setattr(inspection_task, "run_inspection_pipeline", fake_pipeline)
    monkeypatch.setattr(inspection_task, "run_celery_async", fake_run_celery_async)
    monkeypatch.setattr(
        inspection_task,
        "_record_metrics_sync",
        lambda org_id, **kwargs: recorded.append({"org_id": org_id, **kwargs}),
    )

    result = inspection_task.run_inspection({"task_id": "task-1", "org_id": "org-1"})

    assert result == {
        "task_id": "task-1",
        "status": "failed",
        "error": "inspection pipeline returned no result",
    }
    assert recorded[0]["success"] is False
