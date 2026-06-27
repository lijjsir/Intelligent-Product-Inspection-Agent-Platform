from types import SimpleNamespace

from agent.router.capabilities.quality_report_handler import QualityReportHandler


def test_task_collection_content_includes_real_task_and_result_facts():
    tasks = [
        SimpleNamespace(
            id="task-hazelnut",
            product_id="hazelnut",
            spec_code="STD-HAZELNUT",
            status="done",
            priority=5,
            created_at="2026-06-27 00:46:38",
            updated_at="2026-06-27 00:47:20",
        ),
        SimpleNamespace(
            id="task-screw",
            product_id="screw",
            spec_code="STD-SCREW",
            status="done",
            priority=5,
            created_at="2026-06-03 13:11:37",
            updated_at="2026-06-03 13:12:06",
        ),
    ]
    results = {
        "task-hazelnut": SimpleNamespace(
            id="result-hazelnut",
            task_id="task-hazelnut",
            verdict="通过",
            overall_score=0.95,
            created_at="2026/6/26 16:47:20",
        ),
        "task-screw": SimpleNamespace(
            id="result-screw",
            task_id="task-screw",
            verdict="不通过",
            overall_score=1.0,
            created_at="2026/6/3 05:12:06",
        ),
    }

    content = QualityReportHandler._task_collection_content(tasks, total=2, results_by_task_id=results)

    assert content["found"] is True
    assert content["total"] == 2
    assert "共找到 2 条质检任务" in content["summary"]
    assert "hazelnut" in content["summary"]
    assert "screw" in content["summary"]
    assert "通过" in content["summary"]
    assert "不通过" in content["summary"]
    assert "95.0" in content["summary"]
    assert "100.0" in content["summary"]
