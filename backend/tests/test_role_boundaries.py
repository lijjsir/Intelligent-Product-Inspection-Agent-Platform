import pytest

from app.core.claims import (
    CAPABILITY_GOVERNANCE,
    CAPABILITY_MODEL_CONTROL,
    WORKSPACE_GOVERNANCE,
    WORKSPACE_OPS,
    build_auth_claims,
)
from app.core.exceptions import ForbiddenError
from app.core.permissions import (
    ROLE_ADMIN,
    ROLE_ALGORITHM_ENGINEER,
    ROLE_APP_DEVELOPER,
    ROLE_EXPERT,
    ROLE_PLATFORM_OPERATOR,
    ROLE_USER,
    require_role,
)


def test_admin_is_limited_to_governance_claims():
    claims = build_auth_claims(ROLE_ADMIN)

    assert claims.workspaces == [WORKSPACE_GOVERNANCE]
    assert CAPABILITY_GOVERNANCE in claims.capabilities
    assert CAPABILITY_MODEL_CONTROL in claims.capabilities


def test_algorithm_engineer_owns_model_config_control():
    claims = build_auth_claims(ROLE_ALGORITHM_ENGINEER)

    assert claims.workspaces == [WORKSPACE_OPS]
    assert CAPABILITY_MODEL_CONTROL in claims.capabilities
    require_role("model_config", ROLE_ALGORITHM_ENGINEER)


def test_role_specific_resources_do_not_bleed_between_workspaces():
    require_role("tool", ROLE_APP_DEVELOPER)
    require_role("analytics", ROLE_ADMIN)
    require_role("analytics", ROLE_PLATFORM_OPERATOR)
    require_role("auth_log", ROLE_ADMIN)
    require_role("infrastructure", ROLE_ADMIN)
    require_role("memory_governance", ROLE_ADMIN)
    require_role("meeting", ROLE_EXPERT)
    require_role("meeting", ROLE_ADMIN)
    require_role("meeting", ROLE_APP_DEVELOPER)
    require_role("meeting", ROLE_PLATFORM_OPERATOR)
    require_role("meeting", ROLE_ALGORITHM_ENGINEER)
    require_role("collab", ROLE_EXPERT)
    require_role("collab", ROLE_ADMIN)
    require_role("collab", ROLE_APP_DEVELOPER)
    require_role("collab", ROLE_PLATFORM_OPERATOR)
    require_role("collab", ROLE_ALGORITHM_ENGINEER)
    require_role("agent_ops_read", ROLE_PLATFORM_OPERATOR)
    require_role("agent_ops", ROLE_APP_DEVELOPER)
    require_role("alert", ROLE_ADMIN)
    require_role("alert", ROLE_PLATFORM_OPERATOR)
    require_role("alert_rule_read", ROLE_PLATFORM_OPERATOR)
    require_role("alert_rule", ROLE_ADMIN)
    require_role("alert_rule", ROLE_PLATFORM_OPERATOR)
    require_role("quality_delete", ROLE_ADMIN)

    with pytest.raises(ForbiddenError):
        require_role("tool", ROLE_PLATFORM_OPERATOR)
    with pytest.raises(ForbiddenError):
        require_role("memory_governance", ROLE_PLATFORM_OPERATOR)
    with pytest.raises(ForbiddenError):
        require_role("auth_log", ROLE_PLATFORM_OPERATOR)
    with pytest.raises(ForbiddenError):
        require_role("infrastructure", ROLE_PLATFORM_OPERATOR)
    with pytest.raises(ForbiddenError):
        require_role("analytics", ROLE_APP_DEVELOPER)
    require_role("chat", ROLE_ADMIN)
    with pytest.raises(ForbiddenError):
        require_role("agent_ops", ROLE_PLATFORM_OPERATOR)
    with pytest.raises(ForbiddenError):
        require_role("quality_delete", ROLE_PLATFORM_OPERATOR)


@pytest.mark.parametrize("resource", ["meeting", "collab", "stability", "quality"])
def test_ordinary_user_has_no_collaboration_access(resource):
    with pytest.raises(ForbiddenError):
        require_role(resource, ROLE_USER)


def test_ordinary_user_cannot_manage_knowledge_from_task_results():
    from app.api.v1.tasks import _require_task_ingest_access
    with pytest.raises(ForbiddenError):
        _require_task_ingest_access(ROLE_USER)


@pytest.mark.asyncio
async def test_ordinary_user_cannot_open_supervision_apis():
    from app.api.v1.supervision import service
    from app.schemas.user import CurrentUser
    current = CurrentUser(user_id="user-1", org_id="org-1", role=ROLE_USER)
    with pytest.raises(ForbiddenError):
        await service(current=current, db=None)


def test_ordinary_user_can_read_knowledge_but_cannot_manage_it():
    from app.api.v1.rag_spaces import _require_rag_space_access
    from app.schemas.user import CurrentUser
    current = CurrentUser(user_id="user-1", org_id="org-1", role=ROLE_USER)
    _require_rag_space_access(current)
    with pytest.raises(ForbiddenError):
        _require_rag_space_access(current, write=True)


def test_ordinary_user_keeps_task_product_catalog_without_risk_console(monkeypatch):
    from app.api.v1 import quality_risk
    from app.schemas.user import CurrentUser
    current = CurrentUser(user_id="user-1", org_id="org-1", role=ROLE_USER)
    monkeypatch.setattr(quality_risk, "QualityRiskService", lambda _db, actor: actor)
    assert quality_risk.product_option_service(current=current, db=None) is current
    with pytest.raises(ForbiddenError):
        quality_risk.catalog_service(current=current, db=None)
    with pytest.raises(ForbiddenError):
        quality_risk.service(current=current, db=None)
