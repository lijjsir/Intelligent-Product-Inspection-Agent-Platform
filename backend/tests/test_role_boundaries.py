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
    require_role("meeting", ROLE_USER)
    require_role("meeting", ROLE_EXPERT)
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
    with pytest.raises(ForbiddenError):
        require_role("chat", ROLE_ADMIN)
    with pytest.raises(ForbiddenError):
        require_role("agent_ops", ROLE_PLATFORM_OPERATOR)
    with pytest.raises(ForbiddenError):
        require_role("quality_delete", ROLE_PLATFORM_OPERATOR)
