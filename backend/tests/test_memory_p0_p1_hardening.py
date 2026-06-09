from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.schemas.memory import (
    MemoryContent,
    MemoryScope,
    MemorySource,
    MemoryType,
    MemoryWriteRequest,
    RollbackAction,
    Workspace,
)
from app.services.memory_governance_service import MemoryRollbackService
from app.services.memory_service import MemoryService
from app.services.memory_vector_service import MemoryVectorServiceError


class FakeEventRepo:
    def __init__(self):
        self.events = []

    async def create(self, event):
        self.events.append(event)
        return event


class FakePolicyRepo:
    async def get_active(self, policy_key: str, policy_type: str):
        return None


class FakeItemRepo:
    def __init__(self):
        self.created = []
        self.items = {}
        self.status_updates = []
        self.index_updates = []

    async def create(self, item):
        self.created.append(item)
        self.items[item.memory_id] = item
        return item

    async def get_by_idempotency_key(self, idempotency_key: str):
        for item in self.items.values():
            if getattr(item, "idempotency_key", None) == idempotency_key:
                return item
        return None

    async def get_by_memory_id(self, memory_id: str):
        return self.items.get(memory_id)

    async def update_status(self, memory_id: str, status: str):
        self.status_updates.append((memory_id, status))
        if memory_id in self.items:
            self.items[memory_id].status = status

    async def update_index_status(self, memory_id: str, status: str, error: str | None = None):
        self.index_updates.append((memory_id, status, error))
        if memory_id in self.items:
            self.items[memory_id].index_status = status
            self.items[memory_id].index_error = error

    async def list_active_by_scope(self, **kwargs):
        return list(self.items.values())


class FakeDependencyRepo:
    def __init__(self):
        self.edges = []

    async def create(self, edge):
        self.edges.append(edge)
        return edge

    async def soft_delete_by_memory(self, memory_id: str):
        return 0


class FakeRollbackRepo:
    def __init__(self):
        self.review_updates = []

    async def update_review_status(self, rollback_id: str, review_status: str):
        self.review_updates.append((rollback_id, review_status))


class FakeVectorService:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.upserts = []
        self.deletes = []

    async def upsert_memory(self, **kwargs):
        if self.fail:
            raise RuntimeError("qdrant unavailable")
        self.upserts.append(kwargs)

    async def delete_memory(self, memory_id: str):
        self.deletes.append(memory_id)


def _write_request(*, confidence: float = 0.9) -> MemoryWriteRequest:
    return MemoryWriteRequest(
        org_id="org-1",
        user_id="user-1",
        workspace=Workspace.APP,
        source=MemorySource(kind="agent_message", task_id="task-1", trace_id="trace-1"),
        memory_type=MemoryType.TASK_EPISODE,
        scope=MemoryScope(task_id="task-1"),
        content=MemoryContent(summary="stable inspection lesson", facts=["one useful fact"]),
        confidence=confidence,
        trace_id="trace-1",
    )


def _memory_service(vector_service) -> tuple[MemoryService, FakeItemRepo]:
    service = MemoryService(None, "org-1", vector_service=vector_service)
    item_repo = FakeItemRepo()
    service._item_repo = item_repo
    service._event_repo = FakeEventRepo()
    service._policy_repo = FakePolicyRepo()
    service._dep_repo = FakeDependencyRepo()
    return service, item_repo


@pytest.mark.asyncio
async def test_write_candidate_marks_active_memory_index_success_after_qdrant_upsert():
    service, item_repo = _memory_service(FakeVectorService())

    response = await service.write_candidate(_write_request())

    assert response.warnings == []
    assert item_repo.index_updates == [(response.memory_id, "success", None)]


@pytest.mark.asyncio
async def test_write_candidate_marks_index_failed_when_qdrant_upsert_fails():
    service, item_repo = _memory_service(FakeVectorService(fail=True))

    response = await service.write_candidate(_write_request())

    assert "qdrant_sync_failed" in response.warnings
    assert item_repo.index_updates
    memory_id, status, error = item_repo.index_updates[-1]
    assert memory_id == response.memory_id
    assert status == "failed"
    assert "qdrant unavailable" in error


@pytest.mark.asyncio
async def test_search_requires_vector_service_when_eligible_memories_exist():
    service, item_repo = _memory_service(None)
    item_repo.items["mem-1"] = SimpleNamespace(
        memory_id="mem-1",
        memory_type="task_episode",
        content_summary="stable inspection lesson",
        confidence=0.8,
        trust_score=0.8,
        trace_id="trace-1",
        scope_json={"task_id": "task-1"},
        usage_policy="context_only",
    )

    from app.schemas.memory import MemorySearchRequest

    with pytest.raises(MemoryVectorServiceError, match="vector service is required"):
        await service.search(
            MemorySearchRequest(
                org_id="org-1",
                user_id="user-1",
                workspace=Workspace.APP,
                query="stable inspection",
                top_k=5,
            )
        )


@pytest.mark.asyncio
async def test_rollback_branch_is_explicitly_unsupported():
    service = MemoryRollbackService(None, "org-1", None)

    with pytest.raises(ValueError, match="BRANCH rollback is not supported"):
        await service.plan_rollback(
            root_memory_id="mem-root",
            operator_id="user-1",
            operator_role="platform_operator",
            workspace="governance",
            trace_id="trace-1",
            action=RollbackAction.BRANCH,
            target_memory_ids=["mem-root"],
            reason="branch is out of scope",
            require_human_review=False,
        )


@pytest.mark.asyncio
async def test_patch_rollback_creates_new_memory_version_and_version_edge():
    service = MemoryRollbackService(None, "org-1", FakeVectorService())
    old_memory = SimpleNamespace(
        id="row-old",
        memory_id="mem-old",
        org_id="org-1",
        user_id="user-1",
        workspace="app",
        memory_type="task_episode",
        scope_json={"task_id": "task-1"},
        content_summary="old summary",
        content_json={"facts": ["old"]},
        source_event_ids=["trace-old"],
        evidence_pointers=None,
        confidence=0.8,
        trust_score=0.8,
        status="active",
        usage_policy="context_only",
        ttl_policy="90d",
        privacy_level="tenant_private",
        created_by=None,
        created_by_type="agent",
        trace_id="trace-old",
        expires_at=None,
    )
    item_repo = FakeItemRepo()
    item_repo.items["mem-old"] = old_memory
    dep_repo = FakeDependencyRepo()
    service._item_repo = item_repo
    service._dep_repo = dep_repo
    service._event_repo = FakeEventRepo()
    service._rollback_repo = FakeRollbackRepo()

    response = await service._apply_rollback(
        rollback_id="rb-1",
        root_memory_id="mem-old",
        operator_id="user-1",
        workspace="app",
        trace_id="trace-2",
        action=RollbackAction.PATCH,
        target_memory_ids=["mem-old"],
        reason="replace stale summary",
        propagation_graph={
            "patch": {
                "content_summary": "new summary",
                "content_json": {"facts": ["new"]},
            }
        },
    )

    assert response.affected_count == 1
    assert item_repo.status_updates == [("mem-old", "isolated")]
    assert len(item_repo.created) == 1
    new_memory = item_repo.created[0]
    assert new_memory.content_summary == "new summary"
    assert new_memory.version_parent_id == "mem-old"
    assert dep_repo.edges[0].source_memory_id == new_memory.memory_id
    assert dep_repo.edges[0].target_memory_id == "mem-old"
    assert dep_repo.edges[0].edge_type == "version_of"


@pytest.mark.asyncio
async def test_memory_tool_uses_plan_rollback_and_rejects_branch():
    from agent.tools.memory_tools import memory_apply_rollback

    branch_response = await memory_apply_rollback(
        root_memory_id="mem-root",
        org_id="org-1",
        operator_id="user-1",
        trace_id="trace-1",
        target_memory_ids=["mem-root"],
        action="branch",
        governance_service=SimpleNamespace(),
    )

    assert branch_response["error"] == "unsupported_rollback_action"

    class FakeRollbackService:
        def __init__(self):
            self.calls = []

        async def plan_rollback(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(model_dump=lambda: {"rollback_id": "rb-1"})

    rollback_service = FakeRollbackService()
    response = await memory_apply_rollback(
        root_memory_id="mem-root",
        org_id="org-1",
        operator_id="user-1",
        trace_id="trace-1",
        target_memory_ids=["mem-root"],
        action="isolate",
        reason="contain stale memory",
        governance_service=rollback_service,
    )

    assert response == {"rollback_id": "rb-1"}
    assert rollback_service.calls[0]["action"] == RollbackAction.ISOLATE
