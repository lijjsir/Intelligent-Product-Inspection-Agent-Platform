import pytest
from copy import deepcopy
from app.api.v1.deps import apply_permission_identity
from app.schemas.user import CurrentUser

from app.api.v1 import agent, collab, meetings, tools
from app.core.exceptions import ForbiddenError
from app.core.permissions import require_role
from app.services import chat_service


def test_snapshot_preserves_enterprise_workspace_and_deep_copy():
    current = apply_permission_identity(CurrentUser(
        user_id="user-1", org_id="org-1", role="algorithm_engineer", plan_tier="enterprise",
    ), {"user_id": "user-1", "org_id": "org-1", "role": "algorithm_engineer", "effective": ["dataset"]})
    assert current.default_workspace == "governance"
    assert "governance" in current.workspaces
    require_role("dataset", deepcopy(current).role)


@pytest.mark.parametrize("module, dependency", [
    (agent, "get_current_user_for_sse"), (tools, "_get_current_user_for_sse"),
    (meetings, "_get_user_for_stream"), (collab, "_get_user_for_stream"),
    (chat_service, "get_current_user_for_stream"),
])
def test_stream_reconnect_uses_fresh_grants_and_database_role(module, dependency, monkeypatch):
    monkeypatch.setattr(module, "safe_decode_token", lambda _token: {
        "sub": "user-1", "org_id": "org-1", "role": "algorithm_engineer", "typ": "stream",
    })
    args = {"token": "old-token", "identity": {
        "user_id": "user-1", "org_id": "org-1", "role": "expert", "effective": ["chat", "collab"],
    }}
    if module in {agent, tools, chat_service}:
        args["authorization"] = ""
    current = getattr(module, dependency)(**args)
    assert current.role == "expert"
    require_role("chat", current.role)
    with pytest.raises(ForbiddenError):
        require_role("dataset", current.role)
