import uuid

import httpx
import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import DefaultClause, MetaData, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1 import deps, roles, users
from app.core.exceptions import AppError, ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.permission_catalog import LABELS
from app.core.permissions import PERMISSIONS, PermissionRole, ROLE_DISPLAY_ORDER, assignable_permissions, require_role
from app.models.audit import AuditOutbox
from app.models.organization import Organization
from app.models.permission import RolePermission, UserPermission
from app.models.user import User
from app.schemas.permission import RolePermissionUpdate, UserPermissionUpdate
from app.schemas.user import CurrentUser
from app.services.permission_service import PermissionService, default_permissions, effective_permissions
from app.services.user_service import UserService


@pytest.mark.asyncio
async def test_ordinary_user_standard_policy_is_reflected_in_defaults_overrides_and_editor_validation(session):
    session.add(User(id=str(uuid.uuid4()), org_id=ORG, username="ordinary", email="ordinary@example.com", role="user", is_active=True))
    from app.core.permissions import ROLE_RESTRICTED_PERMISSIONS
    blocked = ROLE_RESTRICTED_PERMISSIONS["user"]
    session.add(RolePermission(org_id=ORG, role="user", resources=["task", "inspection_standard_library_read"], version=1))
    await session.flush()
    service = PermissionService(session, ORG)
    assert (await service.matrix())["matrix"]["user"] == ["task"]
    with pytest.raises(ValidationError):
        await service.save_role("user", RolePermissionUpdate(resources=["inspection_spec_read"], version=1), ACTOR)
    with pytest.raises(ValidationError):
        await service.save_user(ENGINEER, UserPermissionUpdate(role="user", expected_role="algorithm_engineer", version=0,
                               overrides={"inspection_standard_library_read": "grant"}), ACTOR)

ORG, OTHER_ORG, ADMIN, ENGINEER, OTHER_USER = [str(uuid.uuid4()) for _ in range(5)]
ACTOR = CurrentUser(user_id=ADMIN, org_id=ORG, role="admin")


@pytest.mark.asyncio
async def test_algorithm_engineer_cannot_regain_business_tasks_from_saved_role_or_user_grants(session):
    session.add(RolePermission(org_id=ORG, role="algorithm_engineer", resources=["task", "dataset", "algo_workspace"], version=1))
    session.add(UserPermission(org_id=ORG, user_id=ENGINEER, overrides={"task":"grant"}, version=1))
    await session.flush()
    service = PermissionService(session, ORG)
    identity = await service.user_permissions(ENGINEER)
    assert "task" not in identity["effective"]
    assert {"dataset", "algo_workspace"} <= set(identity["effective"])
    assert "task" not in (await service.matrix())["matrix"]["algorithm_engineer"]
    with pytest.raises(ValidationError, match="算法工程师"):
        await service.save_role("algorithm_engineer", RolePermissionUpdate(resources=["task"], version=1), ACTOR)
    with pytest.raises(ValidationError, match="算法工程师"):
        await service.save_user(ENGINEER, UserPermissionUpdate(role="algorithm_engineer", expected_role="algorithm_engineer", version=1, overrides={"task":"grant"}), ACTOR)
    with pytest.raises(ForbiddenError):
        require_role("task", PermissionRole("algorithm_engineer", ["task"]))


def test_algorithm_engineer_sample_ingestion_uses_dataset_permission_instead_of_task_permission():
    from app.api.v1.tasks import _require_task_ingest_access
    _require_task_ingest_access(PermissionRole("algorithm_engineer", ["dataset"]))
    with pytest.raises(ForbiddenError):
        _require_task_ingest_access(PermissionRole("algorithm_engineer", ["task"]))
    require_role("dataset", "algorithm_engineer")
    require_role("algo_workspace", "algorithm_engineer")


@pytest.mark.asyncio
async def test_algorithm_engineer_cannot_bypass_task_boundary_through_report_exports():
    from app.services.export_job_service import ExportJobService
    service=ExportJobService(None,ORG,actor_user_id=ENGINEER,actor_role=PermissionRole('algorithm_engineer',['feedback','task','result']))
    with pytest.raises(ForbiddenError):
        await service.list_jobs(1,20)
    with pytest.raises(ForbiddenError):
        await service.get_detail(str(uuid.uuid4()))
    with pytest.raises(ForbiddenError):
        await service.create_job(ENGINEER,{'report_type':'single_task'})


@pytest.mark.asyncio
@pytest.mark.parametrize('authorized',[False,True])
async def test_engineer_needs_explicit_sample_enrollment_even_for_normal_tasks(monkeypatch, authorized):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.services import task_result_ingest_service as ingest
    from app.schemas.task import TaskResultIngestRequest
    task_id, dataset_id, session_id = [str(uuid.uuid4()) for _ in range(3)]
    enrollment = SimpleNamespace(data={'dataset_owner_id':ENGINEER,'session_id':session_id,'session_version':2}) if authorized else None
    source = SimpleNamespace(version=2,data={'knowledge_status':'approved'})
    db = SimpleNamespace(scalar=AsyncMock(side_effect=[enrollment,source]))
    monkeypatch.setattr(ingest,'build_object_storage',lambda:object())
    service = ingest.TaskResultIngestService(db,ORG,actor_user_id=ENGINEER,actor_role='algorithm_engineer')
    service._tasks.get_for_user = AsyncMock(return_value=SimpleNamespace(id=task_id,org_id=ORG,status='done',meta_data={}))
    service._results.get_by_task = AsyncMock(return_value=SimpleNamespace())
    service._stability.get_by_task = AsyncMock(return_value=None)
    service._resolve_dataset_target = AsyncMock(return_value=(dataset_id,'授权样本数据集'))
    service._ingest_to_dataset_candidates = AsyncMock(return_value=(1,0,[]))
    payload = TaskResultIngestRequest(target='dataset',dataset_id=dataset_id)
    if not authorized:
        with pytest.raises(ForbiddenError,match='明确授权'):
            await service.ingest_task_result(task_id=task_id,payload=payload)
        service._results.get_by_task.assert_not_awaited()
    else:
        result=await service.ingest_task_result(task_id=task_id,payload=payload)
        assert result.created_sample_count==1


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    metadata = MetaData()
    for model in [Organization, User, RolePermission, UserPermission, AuditOutbox]:
        table = model.__table__.to_metadata(metadata)
        for column in table.columns:
            if column.name in {"created_at", "updated_at"}:
                column.server_default = DefaultClause(func.current_timestamp())
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        db.add_all([
            Organization(id=ORG, name="测试组织", slug="test", plan="standard", is_active=True),
            Organization(id=OTHER_ORG, name="其他组织", slug="other", plan="standard", is_active=True),
            User(id=ADMIN, org_id=ORG, username="admin", email="admin@example.com", role="admin", is_active=True),
            User(id=ENGINEER, org_id=ORG, username="张三", email="engineer@example.com", role="algorithm_engineer", is_active=True),
            User(id=OTHER_USER, org_id=OTHER_ORG, username="其他用户", email="other@example.com", role="user", is_active=True),
        ])
        await db.commit()
        yield db
    await engine.dispose()


def test_catalog_covers_every_executable_permission():
    assert set(LABELS) == set(PERMISSIONS)


def test_effective_permissions_add_grant_remove_deny_and_fail_closed_on_unknown():
    assert effective_permissions(["model_config", "model_config_read"], {
        "model_config": "deny", "dataset": "grant", "made_up": "grant",
    }) == ["dataset", "model_config_read"]


def test_authorization_uses_snapshot_including_empty_permissions():
    require_role("dataset", PermissionRole("algorithm_engineer", ["dataset"]))
    with pytest.raises(ForbiddenError):
        require_role("dataset", PermissionRole("user", ["dataset"]))
    with pytest.raises(ForbiddenError):
        require_role("dataset", PermissionRole("algorithm_engineer", []))
    require_role("dataset", "algorithm_engineer")


def test_admin_governance_access_does_not_grant_professional_standard_review():
    for resource in PERMISSIONS:
        if resource in {"standard_admission_review","knowledge_review","inspection_execution_review"}:
            with pytest.raises(ForbiddenError): require_role(resource, "admin")
            with pytest.raises(ForbiddenError): require_role(resource, PermissionRole("admin", [resource]))
            continue
        require_role(resource, "admin")
        require_role(resource, PermissionRole("admin", []))
    with pytest.raises(ForbiddenError):
        require_role("made_up", "admin")


@pytest.mark.parametrize("role,resource", [
    ("expert", "user"), ("expert", "organization"), ("expert", "role_read"),
    ("expert", "dataset"), ("expert", "infrastructure"),
    ("algorithm_engineer", "user"), ("app_developer", "billing"),
    ("platform_operator", "model_config"), ("user", "model_config_read"),
])
def test_role_ceiling_blocks_legacy_or_forged_grants(role, resource):
    assert resource not in assignable_permissions(role)
    with pytest.raises(ForbiddenError):
        require_role(resource, PermissionRole(role, [resource]))


@pytest.mark.asyncio
async def test_expert_cannot_receive_user_management_through_role_or_personal_grants(session):
    expert_id = str(uuid.uuid4())
    session.add(User(id=expert_id, org_id=ORG, username="expert", email="expert@example.com", role="expert", is_active=True))
    session.add(RolePermission(org_id=ORG, role="expert", resources=["task", "user", "organization"], version=1))
    session.add(UserPermission(org_id=ORG, user_id=expert_id, overrides={"user": "grant", "task": "deny"}, version=1))
    await session.flush()
    service = PermissionService(session, ORG)
    matrix = await service.matrix()
    assert matrix["matrix"]["expert"] == ["task"]
    assert "user" not in matrix["role_capabilities"]["expert"]
    assert "task" in matrix["role_capabilities"]["expert"]
    state = await service.user_permissions(expert_id)
    assert state["role_default"] == ["task"] and state["effective"] == []
    assert state["overrides"] == {"task": "deny"}
    with pytest.raises(ValidationError):
        await service.save_role("expert", RolePermissionUpdate(resources=["user"], version=1), ACTOR)
    with pytest.raises(ValidationError):
        await service.save_user(expert_id, UserPermissionUpdate(role="expert", expected_role="expert", overrides={"user": "grant"}, version=1), ACTOR)
    # Revoking defaults does not narrow the fixed role ceiling: legitimate
    # personal grants can still restore an eligible feature.
    await service.save_role("expert", RolePermissionUpdate(resources=[], version=1), ACTOR)
    restored = await service.save_user(expert_id, UserPermissionUpdate(role="expert", expected_role="expert", overrides={"task": "grant"}, version=1), ACTOR)
    assert restored["role_default"] == [] and restored["effective"] == ["task"]


@pytest.mark.asyncio
async def test_personal_grant_revoke_and_restore_changes_actual_chat_api_access_without_changing_peers(session, monkeypatch):
    from app.api.v1 import chat as chat_api
    from app.services.chat_service import ChatService
    from unittest.mock import AsyncMock
    first, peer = str(uuid.uuid4()), str(uuid.uuid4())
    session.add_all([User(id=first, org_id=ORG, username="personal", email="personal@example.com", role="user", is_active=True),
                     User(id=peer, org_id=ORG, username="peer", email="peer@example.com", role="user", is_active=True)])
    await session.flush()
    service = PermissionService(session, ORG)
    await service.save_role("user", RolePermissionUpdate(resources=["task", "result"], version=0), ACTOR)
    app = FastAPI()
    app.include_router(chat_api.router)
    async def database():
        yield session
    async def errors(_request, error):
        return JSONResponse({"message": error.message}, status_code=error.status_code)
    app.dependency_overrides[deps.get_db] = database
    app.add_exception_handler(AppError, errors)
    monkeypatch.setattr(deps, "safe_decode_token", lambda token: {"sub": token, "org_id": ORG, "role": "user"})
    monkeypatch.setattr(ChatService, "list_sessions", AsyncMock(return_value=[]))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        async def status(user_id):
            return (await client.get("/chat/sessions", headers={"Authorization": f"Bearer {user_id}"})).status_code
        assert await status(first) == 403 and await status(peer) == 403
        await service.save_user(first, UserPermissionUpdate(role="user", expected_role="user", overrides={"chat": "grant"}, version=0), ACTOR)
        assert await status(first) == 200 and await status(peer) == 403
        await service.save_user(first, UserPermissionUpdate(role="user", expected_role="user", overrides={"chat": "deny"}, version=1), ACTOR)
        await service.save_role("user", RolePermissionUpdate(resources=["task", "result", "chat"], version=1), ACTOR)
        assert await status(first) == 403 and await status(peer) == 200
        await service.save_user(first, UserPermissionUpdate(role="user", expected_role="user", overrides={}, version=2), ACTOR)
        assert await status(first) == 200


@pytest.mark.asyncio
async def test_admin_matrix_and_identity_ignore_legacy_restrictions(session):
    session.add(RolePermission(org_id=ORG, role="admin", resources=[], version=1))
    session.add(UserPermission(org_id=ORG, user_id=ADMIN, overrides={"dataset": "deny"}, version=1))
    await session.flush()
    service = PermissionService(session, ORG)
    expected=sorted(set(PERMISSIONS)-{"standard_admission_review","knowledge_review","inspection_execution_review"})
    assert (await service.matrix())["matrix"]["admin"] == expected
    identity = await service.identity(ADMIN)
    assert identity["effective"] == expected
    assert identity["overrides"] == {}
    with pytest.raises(NotFoundError):
        await service.user_permissions(OTHER_USER)


@pytest.mark.asyncio
async def test_permission_directory_groups_before_pagination_and_preserves_search_and_tenant_scope(session):
    for role in ROLE_DISPLAY_ORDER:
        for index in range(2):
            session.add(User(id=str(uuid.uuid4()), org_id=ORG, username=f"directory-{role}-{index}",
                             email=f"{role}-{index}@example.com", role=role, is_active=True))
    await session.flush()
    service = UserService(session, ORG)
    sequence = []
    for page in range(1, 5):
        members, total, counts = await service.permission_directory(page, 4)
        assert total == 14
        assert sum(counts.values()) == 14
        sequence.extend(members)
    assert len({user.id for user in sequence}) == 14
    ranks = [ROLE_DISPLAY_ORDER.index(user.role) for user in sequence]
    assert ranks == sorted(ranks)
    assert all(user.org_id == ORG for user in sequence)
    experts, total, counts = await service.permission_directory(1, 20, role="expert")
    assert total == 2 and len(experts) == 2
    assert counts["admin"] == 3
    matches, total, counts = await service.permission_directory(1, 20, keyword="directory-expert")
    assert total == 2 and counts == {"expert": 2}
    assert all("directory-expert" in user.username for user in matches)


@pytest.mark.asyncio
async def test_unconfigured_roles_keep_existing_defaults_and_tenant_isolation(session):
    service = PermissionService(session, ORG)
    matrix = await service.matrix()
    for role, resources in matrix["matrix"].items():
        assert resources == default_permissions(role)
    await service.save_role("algorithm_engineer", RolePermissionUpdate(resources=[], version=0), ACTOR)
    assert (await service.user_permissions(ENGINEER))["effective"] == []
    assert (await PermissionService(session, OTHER_ORG).matrix())["matrix"]["algorithm_engineer"] == default_permissions("algorithm_engineer")
    with pytest.raises(NotFoundError):
        await service.user_permissions(OTHER_USER)


@pytest.mark.asyncio
async def test_personal_adjustments_survive_role_edits_and_restore_inheritance(session):
    service = PermissionService(session, ORG)
    changed = await service.save_user(ENGINEER, UserPermissionUpdate(
        role="algorithm_engineer", expected_role="algorithm_engineer", version=0,
        overrides={"model_config": "deny", "dataset": "grant"},
    ), ACTOR)
    assert "model_config" in changed["role_default"]
    assert "model_config" not in changed["effective"]
    assert "dataset" in changed["effective"]
    await service.save_role("algorithm_engineer", RolePermissionUpdate(resources=["model_config"], version=0), ACTOR)
    changed = await service.user_permissions(ENGINEER)
    assert changed["effective"] == ["dataset"]
    inherited = await service.save_user(ENGINEER, UserPermissionUpdate(
        role="algorithm_engineer", expected_role="algorithm_engineer", version=1, overrides={},
    ), ACTOR)
    assert inherited["effective"] == ["model_config"]
    assert len((await session.execute(select(AuditOutbox))).scalars().all()) == 3


@pytest.mark.asyncio
async def test_empty_role_permissions_are_persisted_and_stale_versions_rejected(session):
    service = PermissionService(session, ORG)
    result = await service.save_role("user", RolePermissionUpdate(resources=[], version=0), ACTOR)
    assert result["matrix"]["user"] == []
    assert result["versions"]["user"] == 1
    with pytest.raises(ConflictError):
        await service.save_role("user", RolePermissionUpdate(resources=["chat"], version=0), ACTOR)


@pytest.mark.asyncio
async def test_user_role_and_overrides_save_together_and_detect_external_role_change(session):
    service = PermissionService(session, ORG)
    await service.save_role("user", RolePermissionUpdate(resources=[], version=0), ACTOR)
    result = await service.save_user(ENGINEER, UserPermissionUpdate(
        role="user", expected_role="algorithm_engineer", version=0, overrides={"feedback": "grant"},
    ), ACTOR)
    assert result["role"] == "user"
    assert result["effective"] == ["feedback"]
    with pytest.raises(ConflictError):
        await service.save_user(ENGINEER, UserPermissionUpdate(
            role="expert", expected_role="algorithm_engineer", version=1,
        ), ACTOR)


@pytest.mark.asyncio
async def test_admin_protection_invalid_keys_and_nonadmin_modification(session):
    service = PermissionService(session, ORG)
    with pytest.raises(ForbiddenError):
        await service.save_role("admin", RolePermissionUpdate(resources=[], version=0), ACTOR)
    with pytest.raises(ForbiddenError):
        await service.save_user(ADMIN, UserPermissionUpdate(role="user", expected_role="admin", version=0), ACTOR)
    with pytest.raises(ValidationError):
        await service.save_role("user", RolePermissionUpdate(resources=["made_up"], version=0), ACTOR)
    with pytest.raises(ForbiddenError):
        await service.save_role("user", RolePermissionUpdate(resources=[], version=0),
                                CurrentUser(user_id=ENGINEER, org_id=ORG, role="algorithm_engineer"))
    with pytest.raises(NotFoundError):
        await service.save_user(OTHER_USER, UserPermissionUpdate(role="user", expected_role="user", version=0), ACTOR)


@pytest.mark.asyncio
async def test_fresh_request_identity_revokes_old_token_access_and_disabled_accounts(session, monkeypatch):
    application = FastAPI()
    application.include_router(roles.router, prefix="/roles")
    application.include_router(users.router, prefix="/users")

    async def database():
        yield session

    async def errors(_request, error):
        return JSONResponse({"message": error.message}, status_code=error.status_code)

    @application.get("/feedback-check")
    async def feedback_check(current=Depends(deps.get_current_user)):
        require_role("feedback", current.role)
        return {"role": str(current.role)}

    application.dependency_overrides[deps.get_db] = database
    application.add_exception_handler(AppError, errors)
    monkeypatch.setattr(deps, "safe_decode_token", lambda _token: {
        "sub": ENGINEER, "org_id": ORG, "role": "algorithm_engineer",
    })
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://test",
                                 headers={"Authorization": "Bearer old-token"}) as client:
        assert (await client.get("/feedback-check")).status_code == 200
        service = PermissionService(session, ORG)
        await service.save_user(ENGINEER, UserPermissionUpdate(
            role="user", expected_role="algorithm_engineer", version=0, overrides={"feedback": "grant"},
        ), ACTOR)
        assert (await client.get("/feedback-check")).json()["role"] == "user"
        assert "feedback" in (await client.get("/users/me")).json()["data"]["effective_permissions"]
        await service.save_user(ENGINEER, UserPermissionUpdate(
            role="user", expected_role="user", version=1, overrides={"feedback": "deny"},
        ), ACTOR)
        assert (await client.get("/feedback-check")).status_code == 403
        user = await session.get(User, ENGINEER)
        user.is_active = False
        await session.flush()
        assert (await client.get("/users/me")).status_code == 403
