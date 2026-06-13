from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.tools import get_registry
from agent.tools.contracts import ToolContext
from agent.tools.invoker import ToolInvoker
from app.core.error_handlers import register_error_handlers
from app.core.exceptions import MemoryToolContextError


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
