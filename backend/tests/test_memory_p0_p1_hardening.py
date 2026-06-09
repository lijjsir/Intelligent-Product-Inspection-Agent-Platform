from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import mysql

from app.repositories.memory_repo import MemoryItemRepository
from app.schemas.memory import (
    CandidateSupportCreate,
    EdgeType,
    MemoryContent,
    MemoryScope,
    MemorySearchRequest,
    MemorySource,
    MemoryStatus,
    MemoryType,
    MemoryWriteRequest,
    RollbackAction,
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

    async def find_candidate_by_key(self, *, memory_type: str, candidate_key: str, user_id=None, scope=None):
        for item in self.items.values():
            if (
                getattr(item, "memory_type", None) == memory_type
                and getattr(item, "candidate_key", None) == candidate_key
                and getattr(item, "status", None) in {"candidate", "active"}
            ):
                return item
        return None

    async def update_status(self, memory_id: str, status: str):
        self.status_updates.append((memory_id, status))
        if memory_id in self.items:
            self.items[memory_id].status = status

    async def update_candidate_stats(self, memory_id: str, **values):
        item = self.items[memory_id]
        for key, value in values.items():
            if key.endswith("_delta"):
                attr = key[: -len("_delta")]
                setattr(item, attr, int(getattr(item, attr, 0) or 0) + int(value or 0))
            else:
                setattr(item, key, value)
        return item

    async def update_index_status(self, memory_id: str, status: str, error: str | None = None):
        self.index_updates.append((memory_id, status, error))
        if memory_id in self.items:
            self.items[memory_id].index_status = status
            self.items[memory_id].index_error = error

    async def list_active_by_scope(self, **kwargs):
        return list(self.items.values())

    async def list_retrievable_by_scope(self, **kwargs):
        return [
            item for item in self.items.values()
            if getattr(item, "status", None) == "active"
        ]

    async def list_promotion_candidates(self, **kwargs):
        return [
            item for item in self.items.values()
            if getattr(item, "status", None) == "candidate"
        ]


class FakeSupportRepo:
    def __init__(self):
        self.supports = []

    async def create(self, support):
        self.supports.append(support)
        return support

    async def list_by_candidate(self, candidate_memory_id: str):
        return [
            support for support in self.supports
            if support.candidate_memory_id == candidate_memory_id
        ]

    async def stats_for_candidate(self, candidate_memory_id: str):
        supports = await self.list_by_candidate(candidate_memory_id)
        return {
            "support_count": sum(1 for s in supports if s.support_type not in {"negative", "conflict"}),
            "negative_count": sum(1 for s in supports if s.support_type == "negative"),
            "conflict_count": sum(1 for s in supports if s.support_type == "conflict"),
            "rag_evidence_count": sum(1 for s in supports if s.support_type == "rag_evidence"),
            "agent_verifier_count": len({
                s.source_agent for s in supports
                if s.support_type == "agent_verifier" and s.source_agent
            }),
            "unique_task_count": len({s.task_id for s in supports if s.task_id}),
            "avg_confidence": (
                sum(float(s.confidence or 0) for s in supports) / len(supports)
                if supports else 0.0
            ),
        }


class FakeDependencyRepo:
    def __init__(self):
        self.edges = []

    async def create(self, edge):
        self.edges.append(edge)
        return edge

    async def get_active_edge(self, source_memory_id: str, target_memory_id: str, edge_type: str):
        for e in self.edges:
            if (getattr(e, 'source_memory_id', None) == source_memory_id
                    and getattr(e, 'target_memory_id', None) == target_memory_id
                    and getattr(e, 'edge_type', None) == edge_type):
                return e
        return None

    async def upsert_edge(self, **kwargs):
        existing = await self.get_active_edge(
            kwargs.get('source_memory_id', ''),
            kwargs.get('target_memory_id', ''),
            kwargs.get('edge_type', ''),
        )
        if existing:
            if kwargs.get('strength'):
                existing.strength = max(float(getattr(existing, 'strength', 0) or 0), kwargs['strength'])
            return existing
        edge = SimpleNamespace(**kwargs)
        self.edges.append(edge)
        return edge

    async def soft_delete_by_memory(self, memory_id: str):
        return 0

    async def list_by_edge_type(
        self, memory_id: str, edge_types: list[str], direction: str = "source"
    ):
        if direction == "source":
            return [
                edge for edge in self.edges
                if edge.source_memory_id == memory_id and edge.edge_type in edge_types
            ]
        return [
            edge for edge in self.edges
            if edge.target_memory_id == memory_id and edge.edge_type in edge_types
        ]


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


class FakeSearchVectorService(FakeVectorService):
    async def search(self, **kwargs):
        return [
            {"memory_id": "mem-a", "score": 0.95},
            {"memory_id": "mem-b", "score": 0.94},
        ]


class FakeFailingSearchVectorService(FakeVectorService):
    async def search(self, **kwargs):
        raise MemoryVectorServiceError("embedding unavailable")


class FakeCandidateSearchVectorService(FakeVectorService):
    def __init__(self, results):
        super().__init__()
        self.results = results
        self.searches = []

    async def search(self, **kwargs):
        self.searches.append(kwargs)
        return self.results


def _write_request(*, confidence: float = 0.9) -> MemoryWriteRequest:
    return MemoryWriteRequest(
        org_id="org-1",
        user_id="user-1",
        source=MemorySource(kind="agent_message", task_id="task-1", trace_id="trace-1"),
        memory_type=MemoryType.TASK_EPISODE,
        scope=MemoryScope(task_id="task-1"),
        content=MemoryContent(summary="stable inspection lesson", facts=["one useful fact"]),
        confidence=confidence,
        trace_id="trace-1",
    )


def _memory_service(vector_service, candidate_vector_service=None) -> tuple[MemoryService, FakeItemRepo, FakeSupportRepo]:
    service = MemoryService(
        None,
        "org-1",
        vector_service=vector_service,
        candidate_vector_service=candidate_vector_service,
    )
    item_repo = FakeItemRepo()
    support_repo = FakeSupportRepo()
    service._item_repo = item_repo
    service._support_repo = support_repo
    service._event_repo = FakeEventRepo()
    service._policy_repo = FakePolicyRepo()
    service._dep_repo = FakeDependencyRepo()
    return service, item_repo, support_repo


@pytest.mark.asyncio
async def test_write_candidate_always_creates_candidate_and_initial_support():
    shared_vector = FakeVectorService()
    candidate_vector = FakeVectorService()
    service, item_repo, support_repo = _memory_service(shared_vector, candidate_vector)

    response = await service.write_candidate(_write_request())

    item = item_repo.items[response.memory_id]
    assert response.status == MemoryStatus.CANDIDATE
    assert item.status == "candidate"
    assert item.candidate_key
    assert item.support_count == 1
    assert len(support_repo.supports) == 1
    assert support_repo.supports[0].candidate_memory_id == response.memory_id
    assert shared_vector.upserts == []
    assert candidate_vector.upserts
    assert response.warnings == []


def test_memory_idempotency_key_fits_database_column():
    request = _write_request().model_copy(update={
        "trace_id": "trace-" + ("x" * 200),
        "content": MemoryContent(summary="long summary " * 40, facts=["one useful fact"]),
    })

    key = MemoryService._make_idempotency_key(request)

    assert key.startswith("memory:")
    assert len(key) <= 128


def test_memory_scope_filter_uses_json_field_comparison_for_mysql():
    expression = MemoryItemRepository._scope_equals("product_line", "line-a")

    compiled = str(
        expression.compile(
            dialect=mysql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).upper()
    assert "JSON_CONTAINS" not in compiled
    assert "JSON_EXTRACT" in compiled


@pytest.mark.asyncio
async def test_write_candidate_ignores_non_uuid_agent_created_by():
    service, item_repo, support_repo = _memory_service(FakeVectorService(), FakeVectorService())
    request = _write_request()
    request.created_by = "agent-a"
    request.created_by_type = "agent"

    response = await service.write_candidate(request)

    item = item_repo.items[response.memory_id]
    assert item.created_by is None
    assert item.created_by_type == "agent"
    assert support_repo.supports[0].source_agent == "agent"


@pytest.mark.asyncio
async def test_repeated_candidate_key_adds_support_without_new_memory_item():
    service, item_repo, support_repo = _memory_service(FakeVectorService())

    first = await service.write_candidate(_write_request(confidence=0.5))
    second_req = _write_request(confidence=0.55).model_copy(update={"trace_id": "trace-2"})
    second_req.source.trace_id = "trace-2"
    second = await service.write_candidate(second_req)

    assert second.memory_id == first.memory_id
    assert len(item_repo.created) == 1
    assert len(support_repo.supports) == 2
    assert item_repo.items[first.memory_id].support_count == 2


@pytest.mark.asyncio
async def test_repeated_candidate_key_supports_existing_active_memory():
    service, item_repo, support_repo = _memory_service(FakeVectorService(), FakeVectorService())

    first = await service.write_candidate(_write_request(confidence=0.5))
    await service.approve_candidate(first.memory_id, reviewer_id="reviewer-1", trace_id="approve-1")
    active_support_count = item_repo.items[first.memory_id].support_count
    repeat = _write_request(confidence=0.55).model_copy(update={"trace_id": "trace-active-repeat"})
    repeat.source.trace_id = "trace-active-repeat"

    second = await service.write_candidate(repeat)

    assert second.memory_id == first.memory_id
    assert second.status == MemoryStatus.ACTIVE
    assert len(item_repo.created) == 1
    assert item_repo.items[first.memory_id].support_count == active_support_count + 1


@pytest.mark.asyncio
async def test_semantic_candidate_match_adds_support_without_new_item():
    candidate_vector = FakeCandidateSearchVectorService([
        {"memory_id": "mem-sem", "score": 0.9},
    ])
    service, item_repo, support_repo = _memory_service(FakeVectorService(), candidate_vector)
    item_repo.items["mem-sem"] = SimpleNamespace(
        memory_id="mem-sem",
        memory_type="task_episode",
        status="candidate",
        candidate_key="different-key",
        scope_json={"task_id": "task-1"},
        content_summary="inspection lesson from a prior task",
        confidence=0.5,
        trust_score=0.5,
        policy_key="write_gate",
        policy_version="default:v1",
        trace_id="trace-old",
        user_id="user-1",
        support_count=0,
        negative_count=0,
        conflict_count=0,
        rag_evidence_count=0,
        agent_verifier_count=0,
        human_approved=False,
        promotion_score=None,
    )

    response = await service.write_candidate(_write_request(confidence=0.45))

    assert response.memory_id == "mem-sem"
    assert response.status == MemoryStatus.CANDIDATE
    assert item_repo.created == []
    assert len(support_repo.supports) == 1
    assert float(support_repo.supports[0].similarity) == 0.9
    assert support_repo.supports[0].evidence_pointer["matched_by"] == "candidate_vector"
    assert candidate_vector.searches[0]["status"] == "candidate"


@pytest.mark.asyncio
async def test_semantic_candidate_slot_conflict_marks_contested():
    candidate_vector = FakeCandidateSearchVectorService([
        {"memory_id": "mem-conflict", "score": 0.91},
    ])
    service, item_repo, support_repo = _memory_service(FakeVectorService(), candidate_vector)
    item_repo.items["mem-conflict"] = SimpleNamespace(
        memory_id="mem-conflict",
        memory_type="task_episode",
        status="candidate",
        candidate_key="different-key",
        scope_json={"task_id": "task-2"},
        content_summary="similar lesson from another task",
        confidence=0.6,
        trust_score=0.6,
        policy_key="write_gate",
        policy_version="default:v1",
        trace_id="trace-old",
        user_id="user-1",
        support_count=0,
        negative_count=0,
        conflict_count=0,
        rag_evidence_count=0,
        agent_verifier_count=0,
        human_approved=False,
        promotion_score=None,
    )

    response = await service.write_candidate(_write_request(confidence=0.45))

    assert response.memory_id == "mem-conflict"
    assert response.status == MemoryStatus.CONTESTED
    assert item_repo.items["mem-conflict"].status == "contested"
    assert item_repo.created == []
    assert support_repo.supports[-1].support_type == "conflict"
    assert "candidate_slot_conflict:task_id" in response.warnings


@pytest.mark.asyncio
async def test_rag_evidence_candidate_promotes_to_active_and_marks_index_failure():
    service, item_repo, support_repo = _memory_service(FakeVectorService(fail=True))
    request = MemoryWriteRequest(
        org_id="org-1",
        user_id="user-1",
        source=MemorySource(kind="rag", task_id="task-1", trace_id="trace-rag"),
        memory_type=MemoryType.RAG_USAGE_MEMORY,
        scope=MemoryScope(rag_space_id="rag-1"),
        content=MemoryContent(summary="RAG standard A clause 3.2 is useful for scratch decisions"),
        evidence_pointers={"rag_space_id": "rag-1", "document_id": "doc-1", "chunk_id": "chunk-1"},
        confidence=0.8,
        trace_id="trace-rag",
    )

    response = await service.write_candidate(request)

    assert response.status == MemoryStatus.ACTIVE
    assert "qdrant_sync_failed" in response.warnings
    assert item_repo.index_updates
    memory_id, status, error = item_repo.index_updates[-1]
    assert memory_id == response.memory_id
    assert status == "failed"
    assert "qdrant unavailable" in error
    assert support_repo.supports[0].support_type == "rag_evidence"


@pytest.mark.asyncio
async def test_human_approval_promotes_candidate_in_place_and_removes_candidate_vector():
    shared_vector = FakeVectorService()
    candidate_vector = FakeVectorService()
    service, item_repo, support_repo = _memory_service(shared_vector, candidate_vector)
    response = await service.write_candidate(_write_request(confidence=0.5))

    promoted = await service.approve_candidate(
        response.memory_id,
        reviewer_id="reviewer-1",
        trace_id="trace-review",
    )

    assert promoted.status == MemoryStatus.ACTIVE
    assert item_repo.items[response.memory_id].status == "active"
    assert item_repo.items[response.memory_id].human_approved is True
    assert shared_vector.upserts[-1]["memory_id"] == response.memory_id
    assert candidate_vector.deletes == [response.memory_id]


@pytest.mark.asyncio
async def test_search_requires_vector_service_when_eligible_memories_exist():
    service, item_repo, _support_repo = _memory_service(None)
    item_repo.items["mem-1"] = SimpleNamespace(
        memory_id="mem-1",
        memory_type="task_episode",
        content_summary="stable inspection lesson",
        confidence=0.8,
        trust_score=0.8,
        status="active",
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
                query="stable inspection",
                top_k=5,
            )
        )


@pytest.mark.asyncio
async def test_search_falls_back_to_active_mysql_results_when_vector_runtime_fails():
    service, item_repo, _support_repo = _memory_service(FakeFailingSearchVectorService())
    item_repo.items["mem-1"] = SimpleNamespace(
        memory_id="mem-1",
        memory_type="task_episode",
        content_summary="codex memory verification reusable task lesson",
        confidence=0.8,
        trust_score=0.8,
        status="active",
        trace_id="trace-1",
        scope_json={"task_id": "task-1"},
        usage_policy="context_only",
    )
    item_repo.items["mem-2"] = SimpleNamespace(
        memory_id="mem-2",
        memory_type="task_episode",
        content_summary="codex memory verification candidate should not leak",
        confidence=0.9,
        trust_score=0.9,
        status="candidate",
        trace_id="trace-2",
        scope_json={"task_id": "task-1"},
        usage_policy="context_only",
    )

    response = await service.search(
        MemorySearchRequest(
            org_id="org-1",
            user_id="user-1",
            query="codex memory verification",
            top_k=5,
        )
    )

    assert [item.memory_id for item in response.items] == ["mem-1"]
    assert response.items[0].warnings == ["vector_search_failed_fallback"]


@pytest.mark.asyncio
async def test_search_reuses_existing_conflict_edges_and_skips_llm_detection(monkeypatch):
    service, item_repo, _support_repo = _memory_service(FakeSearchVectorService())
    service._dep_repo.edges.extend([
        SimpleNamespace(
            source_memory_id="mem-a",
            target_memory_id="mem-b",
            edge_type=EdgeType.CONFLICTS_WITH.value,
            strength=0.91,
        ),
        SimpleNamespace(
            source_memory_id="mem-b",
            target_memory_id="mem-a",
            edge_type=EdgeType.CONFLICTS_WITH.value,
            strength=0.91,
        ),
    ])
    item_repo.items["mem-a"] = SimpleNamespace(
        memory_id="mem-a",
        memory_type="task_episode",
        content_summary="camera threshold must be 0.8",
        confidence=0.8,
        trust_score=0.8,
        status="active",
        trace_id="trace-a",
        scope_json={"task_id": "task-1"},
        usage_policy="context_only",
    )
    item_repo.items["mem-b"] = SimpleNamespace(
        memory_id="mem-b",
        memory_type="task_episode",
        content_summary="camera threshold must be 0.4",
        confidence=0.8,
        trust_score=0.8,
        status="active",
        trace_id="trace-b",
        scope_json={"task_id": "task-1"},
        usage_policy="context_only",
    )

    class DetectorShouldNotRun:
        def __init__(self, **kwargs):
            pass

        async def detect(self, items):
            raise AssertionError("LLM conflict detection should be skipped for known conflicts")

    import app.services.memory_conflict_service as conflict_mod
    monkeypatch.setattr(conflict_mod, "ConflictDetectionService", DetectorShouldNotRun)

    response = await service.search(
        MemorySearchRequest(
            org_id="org-1",
            user_id="user-1",
            query="camera threshold",
            top_k=2,
            trace_id="trace-search",
        )
    )

    assert response.conflict_info == {
        "contested_count": 2,
        "relations": [
            {
                "source_memory_id": "mem-a",
                "target_memory_id": "mem-b",
                "relation": "conflicts_with",
                "strength": 0.91,
                "source": "existing_edge",
            },
            {
                "source_memory_id": "mem-b",
                "target_memory_id": "mem-a",
                "relation": "conflicts_with",
                "strength": 0.91,
                "source": "existing_edge",
            },
        ],
    }
    assert all("has_conflict_edges" in item.warnings for item in response.items)


@pytest.mark.asyncio
async def test_rollback_branch_is_explicitly_unsupported():
    service = MemoryRollbackService(None, "org-1", None)

    with pytest.raises(ValueError, match="BRANCH rollback is not supported"):
        await service.plan_rollback(
            root_memory_id="mem-root",
            operator_id="user-1",
            operator_role="platform_operator",
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
