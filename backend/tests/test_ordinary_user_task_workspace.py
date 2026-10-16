import json
import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy import DefaultClause, MetaData, func

from app.api.v1.tasks import task_creation_options
from app.core.exceptions import ForbiddenError, ValidationError
from app.core.permissions import ROLE_RESTRICTED_PERMISSIONS, PermissionRole, require_role
from app.models.export_job import ExportJob
from app.repositories.export_job_repo import ExportJobRepository
from app.schemas.user import CurrentUser
from app.services.inspection_standard_library_service import InspectionStandardLibraryService
from app.api.v1 import quality_risk


@pytest.mark.parametrize("resource", sorted(ROLE_RESTRICTED_PERMISSIONS["user"]))
def test_user_cannot_browse_or_maintain_standards_even_with_old_grants(resource):
    with pytest.raises(ForbiddenError):
        require_role(resource, "user")
    with pytest.raises(ForbiddenError):
        require_role(resource, PermissionRole("user", [resource]))


@pytest.mark.asyncio
async def test_task_choices_only_include_active_bound_standards_and_input_requirements():
    service = InspectionStandardLibraryService(None, "org-1")
    library = SimpleNamespace(id="standard-1", name="已发布标准", is_active=True, inspection_spec_id="spec-1", spec_code="CODE")
    inactive = SimpleNamespace(id="inactive", is_active=False)
    unbound = SimpleNamespace(id="unbound", name="无执行规则", is_active=True, inspection_spec_id=None, spec_code=None)
    spec = SimpleNamespace(is_active=True, spec_code="CODE", required_image_count=2, required_views=["正面", "背面"], ai_gate_confidence_threshold=.9)
    service._repo.list_all = AsyncMock(return_value=[library, inactive, unbound])
    service._spec_repo.get = AsyncMock(return_value=spec)
    choices = await service.list_task_choices()
    assert choices == [{"id": "standard-1", "name": "已发布标准", "spec_code": "CODE", "is_active": True,
                        "required_image_count": 2, "required_views": ["正面", "背面"]}]
    assert "ai_gate_confidence_threshold" not in choices[0]
    service._repo.list_all.assert_awaited_once_with("org-1")


@pytest.mark.asyncio
async def test_task_options_use_task_access_instead_of_full_standard_browser_access(monkeypatch):
    mocked = AsyncMock(return_value=[{"id": "standard-1"}])
    monkeypatch.setattr(InspectionStandardLibraryService, "list_task_choices", mocked)
    current = CurrentUser(user_id="user-1", org_id="org-1", role="user")
    response = await task_creation_options(current=current, db=None)
    assert response.data == {"standards": [{"id": "standard-1"}]}


@pytest.mark.asyncio
async def test_product_options_are_minimal_and_do_not_expose_product_directory_details():
    catalog = {"categories": [{"id": "category-1", "org_id": "org-1", "code": "C1", "name": "类别", "is_active": True, "classification_basis": "内部资料"}],
        "products": [{"id": "product-1", "org_id": "org-1", "category_id": "category-1", "name": "产品", "model": "M1", "brand": "品牌", "is_active": True,
                      "attributes": {"private": "secret"}, "identifiers": [{"source_id": "secret"}], "manufacturer_enterprise_name": "内部企业详情"}]}
    service = SimpleNamespace(product_catalog=AsyncMock(return_value=catalog))
    response = await quality_risk.product_form_options(svc=service)
    assert set(response.data["products"][0]) == {"id", "org_id", "category_id", "name", "model", "brand", "is_active"}
    assert "attributes" not in response.data["products"][0]
    assert "classification_basis" not in response.data["categories"][0]
    service.product_catalog.assert_awaited_once_with(include_inactive=False)


@pytest.mark.parametrize("role", ["user", "expert", "algorithm_engineer", "platform_operator"])
def test_full_product_directory_is_administrator_only_even_with_legacy_grants(role):
    with pytest.raises(ForbiddenError):
        require_role("product_master_read", PermissionRole(role, ["product_master_read"]))


def test_user_catalog_access_is_not_a_task_input_permission(monkeypatch):
    actor = CurrentUser(user_id="user-1", org_id="org-1", role="user")
    monkeypatch.setattr(quality_risk, "QualityRiskService", lambda _db, user: user)
    assert quality_risk.product_option_service(current=actor, db=None) is actor
    with pytest.raises(ForbiddenError):
        quality_risk.catalog_service(current=actor, db=None)
    with pytest.raises(ForbiddenError):
        quality_risk.product_maintenance_service(current=actor, db=None)


@pytest.mark.asyncio
async def test_report_history_filters_by_task_and_owner_without_leaking_other_records():
    engine = create_async_engine("sqlite+aiosqlite://")
    org, other_org, owner, other_owner = [str(uuid.uuid4()) for _ in range(4)]
    metadata = MetaData()
    table = ExportJob.__table__.to_metadata(metadata)
    for column in table.columns:
        if column.name in {"created_at", "updated_at"}:
            column.server_default = DefaultClause(func.current_timestamp())
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        expected = str(uuid.uuid4())
        for index, (org_id, actor_id, config) in enumerate([
            (org, owner, json.dumps({"task_id": "task-1"})),
            (org, owner, json.dumps({"task_id": "task-2"})),
            (org, other_owner, json.dumps({"task_id": "task-1"})),
            (other_org, owner, json.dumps({"task_id": "task-1"})),
            (org, owner, "legacy non-json configuration"),
        ]):
            session.add(ExportJob(id=expected if index == 0 else str(uuid.uuid4()), org_id=org_id, actor_id=actor_id,
                report_name="报告", report_type="single_task", format="pdf", template="standard", config_json=config,
                status="success", created_at=datetime.now(), updated_at=datetime.now()))
        await session.commit()
        count, reports = await ExportJobRepository(session).list_jobs(org, 1, 20, actor_id=owner, task_id="task-1")
        assert count == 1 and [report.id for report in reports] == [expected]
    await engine.dispose()
