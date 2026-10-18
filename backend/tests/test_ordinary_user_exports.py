from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.services.export_job_service import ExportJobService
from app.services.result_service import ResultService
from app.core.permissions import PermissionRole


def user_export_service():
    return ExportJobService(SimpleNamespace(commit=AsyncMock()), "org-1", actor_user_id="user-1", actor_role="user")


@pytest.mark.asyncio
async def test_report_download_can_be_allowed_without_generation_or_feedback():
    service = ExportJobService(None, "org-1", actor_user_id="user-1", actor_role=PermissionRole("user", ["task", "result", "report_read"]))
    service._repo.list_jobs = AsyncMock(return_value=(0, []))
    service._repo.create = AsyncMock()
    assert await service.list_jobs(1, 20) == (0, [])
    with pytest.raises(ForbiddenError):
        await service.create_job("user-1", {"report_type": "single_task"})
    service._repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_feedback_access_does_not_grant_report_download():
    service = ExportJobService(None, "org-1", actor_user_id="user-1", actor_role=PermissionRole("user", ["task", "result", "feedback"]))
    service._repo.list_jobs = AsyncMock()
    with pytest.raises(ForbiddenError):
        await service.list_jobs(1, 20)
    service._repo.list_jobs.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["org/job/report.pdf", "org/./job/report.pdf", "other-name.pdf"])
async def test_report_bucket_never_serves_anonymous_files_even_with_alternative_key_shapes(monkeypatch, key):
    from app.api.v1 import files
    monkeypatch.setattr(files.settings, "report_export_bucket", "reports")
    with pytest.raises(ForbiddenError):
        await files.serve_file("reports", key, authorization="", db=None)


@pytest.mark.asyncio
@pytest.mark.parametrize("job", [
    SimpleNamespace(org_id="org-1", actor_id="other-user"),
    SimpleNamespace(org_id="other-org", actor_id="user-1"),
])
async def test_user_cannot_read_or_delete_another_users_export(job):
    service = user_export_service()
    service._repo.get_by_id = AsyncMock(return_value=job)
    service._repo.soft_delete = AsyncMock()
    with pytest.raises(NotFoundError):
        await service.get_detail("job-1")
    with pytest.raises(NotFoundError):
        await service.delete_job("job-1")
    service._repo.soft_delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_export_history_is_scoped_to_the_current_user():
    service = user_export_service()
    service._repo.list_jobs = AsyncMock(return_value=(0, []))
    await service.list_jobs(1, 20)
    service._repo.list_jobs.assert_awaited_once_with("org-1", 1, 20, None, None, actor_id="user-1")


@pytest.mark.asyncio
async def test_expert_export_history_remains_organization_scoped():
    service = ExportJobService(None, "org-1", actor_user_id="expert-1", actor_role="expert")
    service._repo.list_jobs = AsyncMock(return_value=(0, []))
    await service.list_jobs(1, 20)
    service._repo.list_jobs.assert_awaited_once_with("org-1", 1, 20, None, None, actor_id=None, risk_actor_id="expert-1")


@pytest.mark.asyncio
@pytest.mark.parametrize("report_type", ["batch_summary", "quality_analysis", "feedback_report", "evidence_trace"])
async def test_user_cannot_generate_organization_reports(report_type):
    service = user_export_service()
    service._repo.create = AsyncMock()
    with pytest.raises(ForbiddenError):
        await service.create_job("user-1", {"report_type": report_type})
    service._repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_user_cannot_export_an_unowned_task(monkeypatch):
    lookup = AsyncMock(return_value=None)
    monkeypatch.setattr("app.repositories.task_repo.TaskRepository.get_for_user", lookup)
    service = user_export_service()
    service._repo.create = AsyncMock()
    with pytest.raises(NotFoundError):
        await service.create_job("user-1", {
            "report_type": "single_task", "config_json": {"task_id": "foreign-task"},
        })
    lookup.assert_awaited_once_with("org-1", "foreign-task", owner_user_id="user-1")
    service._repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_user_report_uses_safe_task_configuration(monkeypatch):
    lookup = AsyncMock(return_value=SimpleNamespace(id="task-1"))
    monkeypatch.setattr("app.repositories.task_repo.TaskRepository.get_for_user", lookup)
    monkeypatch.setattr("worker.tasks.report_generate_task.generate_report_task.delay", lambda _payload: None)
    freeze=AsyncMock(return_value={'task':{'id':'task-1'},'scope':{'stage':'auxiliary_record','product_verdict':'not_assessed'},
        'selection':{'execution_run_id':None,'legacy_only':False},'result_token':'server-resolved'})
    monkeypatch.setattr('app.services.task_result_bundle_service.TaskResultBundleService.freeze',freeze)
    service = user_export_service()
    service._repo.create = AsyncMock(return_value=SimpleNamespace(id="job-1"))
    await service.create_job("user-1", {
        "report_name": "报告", "report_type": "single_task", "format": "pdf",
        "template": "audit", "config_json": {"task_id": "task-1", "include_reasoning": True},
    })
    import json
    saved = service._repo.create.call_args.args[0]
    assert saved["actor_id"] == "user-1"
    assert saved["template"] == "standard"
    assert json.loads(saved["config_json"])["include_reasoning"] is False
    assert json.loads(saved['config_json'])['report_snapshot']['result_token']=='server-resolved'
    service._session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_user_cannot_request_a_raw_data_export():
    with pytest.raises(ValidationError):
        await user_export_service().create_job("user-1", {"report_type": "single_task", "format": "json"})


@pytest.mark.asyncio
async def test_result_page_cannot_read_a_different_users_task(monkeypatch):
    lookup = AsyncMock(return_value=None)
    monkeypatch.setattr("app.repositories.task_repo.TaskRepository.get_for_user", lookup)
    service = ResultService(None, "org-1", owner_user_id="user-1")
    service._repo.get_by_task = AsyncMock()
    assert await service.get_response_by_task("foreign-task") is None
    service._repo.get_by_task.assert_not_awaited()
