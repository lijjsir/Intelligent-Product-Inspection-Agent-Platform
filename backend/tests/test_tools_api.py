import pytest
from fastapi import HTTPException

from app.api.v1 import tools as tools_api
from app.core.exceptions import ForbiddenError
from app.schemas.user import CurrentUser


def current_user(role: str = "app_developer") -> CurrentUser:
    return CurrentUser(user_id=f"{role}-1", org_id="org-1", role=role, roles=[role])


@pytest.mark.asyncio
async def test_list_tools_returns_paged_response(monkeypatch):
    class FakeToolService:
        def __init__(self, db, org_id):
            self.db = db
            self.org_id = org_id

        async def list_tools(self, payload):
            assert payload["page"] == 2
            return {
                "items": [
                    {
                        "id": "tool-1",
                        "tool_key": "rag.standard_search",
                        "display_name": "标准知识库检索",
                        "description": "desc",
                        "category": "RAG",
                        "tool_type": "rag",
                        "status": "active",
                        "risk_level": "low",
                        "is_readonly": True,
                        "source_type": "manual",
                        "health_status": "healthy",
                        "active_version": "1.0.0",
                        "bound_agent_names": [],
                        "today_calls": 0,
                        "success_rate": 0.0,
                        "avg_latency_ms": 0,
                    }
                ],
                "total": 1,
                "page": 2,
                "size": 5,
            }

    monkeypatch.setattr(tools_api, "ToolService", FakeToolService)

    response = await tools_api.list_tools(
        page=2,
        size=5,
        status_filter=None,
        current=current_user(),
        db=object(),
    )

    assert response.data.total == 1
    assert response.data.page == 2
    assert response.data.items[0].tool_key == "rag.standard_search"


@pytest.mark.asyncio
async def test_tool_overview_route_returns_summary(monkeypatch):
    class FakeToolService:
        def __init__(self, db, org_id):
            pass

        async def get_overview(self):
            return {
                "total_tools": 3,
                "active_tools": 2,
                "error_tools": 1,
                "today_calls": 8,
                "avg_latency_ms": 120,
                "high_risk_tools": 0,
                "call_trend": [],
                "health_distribution": {"healthy": 2, "degraded": 1, "unhealthy": 0, "unknown": 0},
                "error_trend": [],
                "top_failing": [],
                "high_latency": [],
                "pending_risk_tools": [],
                "critical_dependencies": [],
            }

    monkeypatch.setattr(tools_api, "ToolService", FakeToolService)

    response = await tools_api.get_tool_overview(current=current_user(), db=object())

    assert response.data["total_tools"] == 3
    assert response.data["avg_latency_ms"] == 120


@pytest.mark.asyncio
async def test_get_tool_detail_uses_service(monkeypatch):
    class FakeToolService:
        def __init__(self, db, org_id):
            pass

        async def get_tool_detail(self, tool_id):
            assert tool_id == "tool-1"
            return {
                "id": "tool-1",
                "tool_key": "rag.standard_search",
                "display_name": "标准知识库检索",
                "description": "desc",
                "category": "RAG",
                "tool_type": "rag",
                "status": "active",
                "risk_level": "low",
                "is_readonly": True,
                "source_type": "manual",
                "health_status": "healthy",
                "active_version": "1.0.0",
                "bound_agent_names": [],
                "today_calls": 5,
                "success_rate": 1.0,
                "avg_latency_ms": 100,
                "active_version_id": "tool-1:1.0.0",
                "versions": [],
                "executions": [],
                "bindings": [],
                "parameters_schema": {},
                "returns_schema": {},
                "audit_logs": [],
            }

    monkeypatch.setattr(tools_api, "ToolService", FakeToolService)

    response = await tools_api.get_tool_detail("tool-1", current=current_user(), db=object())

    assert response.data["id"] == "tool-1"
    assert response.data["active_version_id"] == "tool-1:1.0.0"


@pytest.mark.asyncio
async def test_test_tool_returns_test_result(monkeypatch):
    class FakeToolService:
        def __init__(self, db, org_id):
            pass

        async def test_tool(self, tool_id, params):
            assert tool_id == "tool-2"
            assert params == {"query": "hello"}
            return {
                "status": "success",
                "duration_ms": 12,
                "output": {"mode": "dry_run"},
                "error": None,
                "trace_id": "trace-1",
            }

    monkeypatch.setattr(tools_api, "ToolService", FakeToolService)

    response = await tools_api.test_tool(
        "tool-2",
        payload=tools_api.ToolTestRequest(params={"query": "hello"}),
        current=current_user(),
        db=object(),
    )

    assert response.data["status"] == "success"
    assert response.data["trace_id"] == "trace-1"


@pytest.mark.asyncio
async def test_list_executions_forwards_agent_and_execution_type(monkeypatch):
    class FakeToolService:
        def __init__(self, db, org_id):
            pass

        async def list_executions(self, payload):
            assert payload["agent_id"] == "agent-1"
            assert payload["execution_type"] == "test"
            assert payload["status"] == "failed"
            return {"items": [], "total": 0, "page": 1, "size": 20}

    monkeypatch.setattr(tools_api, "ToolService", FakeToolService)

    response = await tools_api.list_executions(
        page=1,
        size=20,
        tool_id=None,
        agent_id="agent-1",
        status_filter="failed",
        execution_type="test",
        current=current_user(),
        db=object(),
    )

    assert response.data.total == 0
    assert response.data.page == 1


@pytest.mark.asyncio
async def test_binding_crud_routes_use_binding_service(monkeypatch):
    recorded: dict = {}

    class FakeBindingService:
        def __init__(self, db, org_id):
            pass
        async def list_bindings(self, tool_id=None):
            return [{"id": "b1", "agent_id": "agent-1", "tool_id": "tool-1"}]
        async def create_binding(self, payload):
            recorded["created"] = payload
            return {"id": "b1", "agent_id": payload["agent_id"], "binding_status": "active"}
        async def delete_binding(self, binding_id):
            recorded["deleted"] = binding_id
            return {"deleted": True}

    monkeypatch.setattr(tools_api, "ToolBindingService", FakeBindingService)

    list_resp = await tools_api.get_bindings(current=current_user(), db=object())
    assert len(list_resp.data) == 1

    create_resp = await tools_api.create_binding(
        payload=tools_api.BindingCreate(agent_id="agent-1", tool_id="tool-1"),
        current=current_user(),
        db=object(),
    )
    assert create_resp.data["agent_id"] == "agent-1"
    assert recorded["created"]["agent_id"] == "agent-1"

    delete_resp = await tools_api.delete_binding("b1", current=current_user(), db=object())
    assert delete_resp.data["deleted"] is True


@pytest.mark.asyncio
async def test_version_routes_use_version_service(monkeypatch):
    class FakeVersionService:
        def __init__(self, db, org_id):
            pass
        async def list_versions(self, tool_id):
            return [{"id": "v1", "tool_id": tool_id, "version": "1.0.0", "status": "active"}]

    monkeypatch.setattr(tools_api, "ToolVersionService", FakeVersionService)

    list_resp = await tools_api.list_tool_versions("tool-1", current=current_user(), db=object())
    assert len(list_resp.data) == 1
    assert list_resp.data[0]["version"] == "1.0.0"


@pytest.mark.asyncio
async def test_user_role_cannot_access_tool_routes():
    with pytest.raises(ForbiddenError):
        await tools_api.get_tool_overview(current=current_user("user"), db=object())
