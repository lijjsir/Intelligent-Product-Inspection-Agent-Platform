from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.tools import get_registry
from agent.tools.contracts import ToolContext
from agent.tools.invoker import ToolInvoker
from app.api.v1.deps import get_current_user, get_db
from app.api.v1.memory import router as memory_router
from app.core.error_handlers import register_error_handlers
from app.core.exceptions import MemoryToolContextError
from app.schemas.user import CurrentUser


VALID_ORG_ID = "00000000-0000-0000-0000-000000000001"
VALID_USER_ID = "00000000-0000-0000-0000-000000000002"


def _memory_test_app(current_user: CurrentUser | None = None) -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(memory_router, prefix="/api/v1/memory")
    app.dependency_overrides[get_current_user] = lambda: current_user or CurrentUser(
        user_id=VALID_USER_ID,
        org_id=VALID_ORG_ID,
        username="admin",
        role="admin",
    )
    app.dependency_overrides[get_db] = lambda: object()
    return app


def test_memory_errors_return_structured_fail_fast_envelope():
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/boom")
    async def boom():
        raise MemoryToolContextError(
            detail={"missing": ["trace_id"]},
            trace_id="trace-1",
        )

    response = TestClient(app).get("/boom")

    assert response.status_code == 400
    payload = response.json()
    assert payload["success"] is False
    assert payload["code"] == "MEMORY_TOOL_CONTEXT_MISSING"
    assert payload["data"] is None
    assert payload["error"] == {
        "code": "MEMORY_TOOL_CONTEXT_MISSING",
        "message": "共享记忆工具缺少必要上下文",
        "detail": {"missing": ["trace_id"]},
        "module": "memory",
        "trace_id": "trace-1",
        "suggestion": None,
    }

def test_memory_api_validation_errors_use_structured_envelope():
    app = _memory_test_app(CurrentUser(
        user_id="user-1",
        org_id="org-1",
        username="admin",
        role="admin",
    ))

    response = TestClient(app).post(
        "/api/v1/memory/candidates",
        json={
            "org_id": "other-org",
            "user_id": "user-1",
            "source": {"kind": "agent_message"},
            "memory_type": "task_episode",
            "scope": {"task_id": "task-1"},
            "content": {"summary": "stable inspection preference"},
            "trace_id": "trace-api-contract",
        },
    )

    assert response.status_code == 403
    payload = response.json()
    assert payload["success"] is False
    assert payload["data"] is None
    assert payload["code"] == "SHARED_MEMORY_SCOPE_FORBIDDEN"
    assert "detail" not in payload
    assert payload["error"]["trace_id"] == "trace-api-contract"
    assert payload["error"]["suggestion"] == "Use the current user's organization scope."


def test_memory_api_rejects_invalid_user_uuid_before_database_access():
    app = _memory_test_app(CurrentUser(
        user_id="user-1",
        org_id="org-1",
        username="admin",
        role="admin",
    ))

    response = TestClient(app).post(
        "/api/v1/memory/candidates",
        json={
            "org_id": "org-1",
            "user_id": "user-1",
            "source": {"kind": "agent_message"},
            "memory_type": "task_episode",
            "scope": {"task_id": "task-1"},
            "content": {"summary": "stable inspection preference"},
            "trace_id": "trace-invalid-user",
        },
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["success"] is False
    assert payload["code"] == "SHARED_MEMORY_INVALID_REQUEST"
    assert payload["error"]["detail"] == {"field": "current.user_id", "value": "user-1"}
    assert payload["error"]["trace_id"] == "trace-invalid-user"


def test_memory_rollback_rejects_invalid_operator_uuid_before_database_access():
    response = TestClient(_memory_test_app()).post(
        "/api/v1/memory/rollback",
        json={
            "org_id": VALID_ORG_ID,
            "operator_id": "operator-1",
            "trace_id": "trace-invalid-operator",
            "root_memory_id": "mem-root",
            "rollback_action": "isolate",
            "target_memory_ids": ["mem-root"],
            "reason": "bad memory",
        },
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["success"] is False
    assert payload["code"] == "SHARED_MEMORY_INVALID_REQUEST"
    assert payload["error"]["detail"] == {"field": "operator_id", "value": "operator-1"}
    assert payload["error"]["trace_id"] == "trace-invalid-operator"


def test_memory_conflict_resolution_rejects_invalid_reviewer_uuid_before_database_access():
    response = TestClient(_memory_test_app()).post(
        "/api/v1/memory/conflicts/mem-a/resolve",
        json={
            "action": "keep_A",
            "reviewer_id": "reviewer-1",
            "comment": "prefer A",
        },
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["success"] is False
    assert payload["code"] == "SHARED_MEMORY_INVALID_REQUEST"
    assert payload["error"]["detail"] == {"field": "reviewer_id", "value": "reviewer-1"}


@pytest.mark.asyncio
async def test_builtin_registry_exposes_memory_tools():
    registry = get_registry()
    names = {spec.name for spec in registry.list_all()}

    assert {
        "memory.search",
        "memory.write_candidate",
        "memory.report_conflict",
        "memory.build_propagation_graph",
        "memory.apply_rollback",
        "memory.replay_evaluation",
    }.issubset(names)


@pytest.mark.asyncio
async def test_memory_tool_missing_context_fails_instead_of_returning_empty_result():
    registry = get_registry()
    invoker = ToolInvoker(registry, db_session=object())

    result = await invoker.invoke(
        tool_name="memory.search",
        arguments={"query": "camera threshold"},
        context=ToolContext(
            org_id="org-1",
            request_id="req-1",
            user_id="user-1",
            trace_id=None,
            agent="chat",
            surface="chat",
        ),
    )

    assert result.status == "failed"
    assert "MEMORY_TOOL_CONTEXT_MISSING" in str(result.error)
