from types import SimpleNamespace

import pytest

from app.services.tool_service import ToolService


class RecordingRepo:
    def __init__(self):
        self.list_kwargs = None
        self.count_kwargs = None

    async def list_executions(self, org_id, **kwargs):
        self.list_kwargs = {"org_id": org_id, **kwargs}
        return []

    async def count_executions(self, org_id, **kwargs):
        self.count_kwargs = {"org_id": org_id, **kwargs}
        return 0


@pytest.mark.asyncio
async def test_list_executions_forwards_agent_and_execution_type_filters():
    service = ToolService(session=SimpleNamespace(), org_id="org-1")
    repo = RecordingRepo()
    service._repo = repo

    result = await service.list_executions(
        {
            "page": 2,
            "size": 10,
            "tool_id": "tool-1",
            "agent_id": "agent-1",
            "status": "failed",
            "execution_type": "test",
        }
    )

    assert result == {"items": [], "total": 0, "page": 2, "size": 10}
    assert repo.list_kwargs == {
        "org_id": "org-1",
        "tool_id": "tool-1",
        "agent_id": "agent-1",
        "status": "failed",
        "execution_type": "test",
        "page": 2,
        "size": 10,
    }
    assert repo.count_kwargs == {
        "org_id": "org-1",
        "tool_id": "tool-1",
        "agent_id": "agent-1",
        "status": "failed",
        "execution_type": "test",
    }
