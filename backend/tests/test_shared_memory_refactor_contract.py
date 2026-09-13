from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"


def test_session_vector_memory_is_removed_from_codebase():
    assert not (BACKEND_ROOT / "app" / "services" / "session_memory_vector_service.py").exists()

    for relative in (
        "app/services/chat_service.py",
        "app/services/short_term_memory_service.py",
    ):
        text = (BACKEND_ROOT / relative).read_text(encoding="utf-8")
        assert "SessionMemoryVectorService" not in text
        assert "_index_session_message" not in text
        assert "piap_session_memory" not in text


def test_prompt_builder_injects_shared_and_short_term_memory():
    from agent.prompts.prompt_builder import PromptBuilder

    _system, user_message, _temperature, meta = PromptBuilder.build(
        agent="chat",
        sub_route="quality_qa",
        query="How should we inspect edge burrs?",
        history=[{"role": "user", "content": "previous visible turn"}],
        shared_memory_context={
            "items": [
                {
                    "memory_id": "mem_edge_burr",
                    "memory_type": "inspection_pattern",
                    "summary": "Edge burrs often need manual recheck.",
                    "confidence": 0.81,
                    "trust_score": 0.9,
                    "warnings": ["verify current standard version"],
                }
            ],
            "conflict_guard": {"suppressed_memory_ids": [], "downranked_memory_ids": []},
        },
        short_term_context={
            "conversation_summary": "The user is preparing an EU market inspection.",
            "session_facts": {"target_market": "EU", "standard_version": "2024"},
            "short_term_memory": {
                "recent_dialogue": [{"role": "assistant", "content": "remember latest product line", "seq_no": 2}],
                "working_state": {"pending_action": "confirm_task"},
            },
        },
    )

    assert "mem_edge_burr" in user_message
    assert "Edge burrs often need manual recheck." in user_message
    assert "target_market" in user_message
    assert "EU" in user_message
    assert "The user is preparing an EU market inspection." in user_message
    assert meta["shared_memory_injected_count"] == 1
    assert meta["short_term_summary_injected"] is True
    assert meta["session_facts_injected_keys"] == ["standard_version", "target_market"]


def test_legacy_quality_chat_graph_is_not_registered():
    from agent.router.manager_dispatcher import ManagerDispatcher

    assert "quality_chat" not in ManagerDispatcher()._executors


def test_graph_factory_requires_neo4j_even_when_strict_sync_disabled(monkeypatch):
    from app.errors.memory_errors import GraphMemoryError
    from app.services import memory_graph_factory as factory_mod

    monkeypatch.setattr(factory_mod.settings, "memory_strict_sync", False)
    monkeypatch.setattr(factory_mod.settings, "neo4j_enabled", False)
    monkeypatch.setattr(factory_mod.settings, "memory_graph_write_backend", "neo4j")
    monkeypatch.setattr(factory_mod.settings, "memory_graph_read_backend", "neo4j")

    with pytest.raises(GraphMemoryError, match="neo4j_enabled=True"):
        factory_mod.build_memory_graph_store(object(), "org-1")


def test_memory_vector_point_id_is_org_scoped():
    from app.services.memory_vector_service import MemoryVectorService

    a = MemoryVectorService._point_id("org-a", "mem-1")
    b = MemoryVectorService._point_id("org-b", "mem-1")
    again = MemoryVectorService._point_id("org-a", "mem-1")

    assert a != b
    assert a == again


def test_memory_item_has_split_sync_status_and_structured_scope_fields():
    from app.models.memory import MemoryItem

    for name in (
        "vector_status",
        "graph_status",
        "last_vector_sync_at",
        "last_graph_sync_at",
        "vector_error",
        "graph_error",
        "task_id",
        "product_line",
        "rag_space_id",
        "standard_code",
        "standard_version",
        "production_date",
        "target_market",
        "product_category",
    ):
        assert hasattr(MemoryItem, name)


def test_retrieval_requires_successful_vector_sync_and_structured_filters():
    source = (BACKEND_ROOT / "app/repositories/memory_repo.py").read_text(encoding="utf-8")

    assert 'MemoryItem.vector_status == "success"' in source
    assert "MemoryItem.task_id == task_id" in source
    assert "MemoryItem.product_line == product_line" in source
    assert "MemoryItem.rag_space_id == rag_space_id" in source
    assert "MemoryScopeBinding.scope_type == \"meeting_room\"" in source


def test_outbox_worker_supports_canonical_uppercase_actions():
    source = (BACKEND_ROOT / "worker/tasks/memory_sync_outbox_task.py").read_text(encoding="utf-8")

    for action in (
        "UPSERT_ACTIVE_VECTOR",
        "DELETE_ACTIVE_VECTOR",
        "UPSERT_CANDIDATE_VECTOR",
        "DELETE_CANDIDATE_VECTOR",
        "UPSERT_MEMORY_NODE",
        "UPSERT_MEMORY_EDGE",
        "SOFT_DELETE_MEMORY_EDGES",
        "UPDATE_MEMORY_NODE_STATUS",
    ):
        assert action in source


def test_neo4j_graph_supports_conflict_case_and_domain_nodes():
    source = (BACKEND_ROOT / "app/services/neo4j_memory_graph_store.py").read_text(encoding="utf-8")

    for token in (
        "ConflictCase",
        "ProductLine",
        "StandardVersion",
        "InspectionTask",
        "InspectionBatch",
        "DefectType",
        "PARTICIPATES_IN",
    ):
        assert token in source


def test_legacy_memory_manager_graph_is_not_registered():
    from agent.router.manager_dispatcher import ManagerDispatcher

    assert "memory_manager" not in ManagerDispatcher()._executors


def test_readiness_thresholds_use_evidence_type_specific_confidence():
    from app.services.memory_governance_domain import calculate_readiness

    agent_ready = calculate_readiness(
        {
            "origin_evidence_count": 1,
            "agent_verifier_count": 2,
            "avg_confidence": 0.20,
            "agent_avg_confidence": 0.80,
        },
        review_status="candidate",
    )
    assert agent_ready.status == "ready"
    assert agent_ready.reason == "two_agent_verifications"

    rag_collecting = calculate_readiness(
        {
            "origin_evidence_count": 1,
            "rag_evidence_count": 1,
            "avg_confidence": 0.95,
            "rag_avg_confidence": 0.60,
        },
        review_status="candidate",
    )
    assert rag_collecting.status == "collecting"


def test_ai_chat_source_defaults_to_current_user_home_scope():
    from app.services.memory_governance_domain import default_home_scope

    assert default_home_scope(
        source_kind="user",
        org_id="org-1",
        user_id="user-1",
    ) == ("user", "user-1")


@pytest.mark.asyncio
async def test_state_transition_writes_status_event_and_sync_outbox(monkeypatch):
    from app.services import memory_state_transition_service as module

    item = SimpleNamespace(
        memory_id="mem-1",
        status="candidate",
        user_id="user-1",
        trace_id="trace-old",
        memory_type="inspection_pattern",
        trust_score=0.7,
        confidence=0.8,
    )
    status_updates = []
    events = []
    outbox_rows = []

    class FakeItemRepo:
        def __init__(self, _session, _org_id):
            pass

        async def get_by_memory_id(self, memory_id):
            assert memory_id == "mem-1"
            return item

        async def update_status(self, memory_id, status):
            status_updates.append((memory_id, status))
            item.status = status

    class FakeEventRepo:
        def __init__(self, _session, _org_id):
            pass

        async def create(self, event):
            events.append(event)
            return event

    class FakeOutboxRepo:
        def __init__(self, _session, _org_id):
            pass

        async def create_pending(self, **kwargs):
            outbox_rows.append(kwargs)

    monkeypatch.setattr(module, "MemoryItemRepository", FakeItemRepo)
    monkeypatch.setattr(module, "MemoryEventRepository", FakeEventRepo)
    monkeypatch.setattr(module, "MemorySyncOutboxRepository", FakeOutboxRepo)

    service = module.MemoryStateTransitionService(object(), "org-1")
    await service.transition(
        "mem-1",
        action="isolate",
        target_status="isolated",
        actor_id="reviewer-1",
        trace_id="trace-1",
        reason="conflict",
    )

    assert status_updates == [("mem-1", "isolated")]
    assert events[0].event_type == "memory_isolate"
    actions = [row["action"] for row in outbox_rows]
    assert "DELETE_CANDIDATE_VECTOR" in actions
    assert "UPDATE_MEMORY_NODE_STATUS" in actions
    assert "SOFT_DELETE_MEMORY_EDGES" in actions


@pytest.mark.asyncio
async def test_activation_outbox_contains_complete_vector_payload(monkeypatch):
    from app.services import memory_state_transition_service as module

    item = SimpleNamespace(
        memory_id="mem-org-1",
        status="confirmed",
        user_id="user-1",
        trace_id="trace-old",
        memory_type="quality_pattern",
        content_summary="螺钉边缘识别在弱光条件下容易失真",
        scope_json={"scope_type": "org_space", "scope_id": "org-1"},
        trust_score=0.65,
        confidence=0.8,
        expires_at=None,
        product_line="fastener",
        rag_space_id=None,
        task_id=None,
        source_task_id="task-1",
    )
    outbox_rows = []

    class FakeItemRepo:
        def __init__(self, _session, _org_id):
            pass

        async def get_by_memory_id(self, memory_id):
            return item if memory_id == item.memory_id else None

        async def update_status(self, memory_id, status):
            item.status = status

    class FakeEventRepo:
        def __init__(self, _session, _org_id):
            pass

        async def create(self, event):
            return event

    class FakeOutboxRepo:
        def __init__(self, _session, _org_id):
            pass

        async def create_pending(self, **kwargs):
            outbox_rows.append(kwargs)

    monkeypatch.setattr(module, "MemoryItemRepository", FakeItemRepo)
    monkeypatch.setattr(module, "MemoryEventRepository", FakeEventRepo)
    monkeypatch.setattr(module, "MemorySyncOutboxRepository", FakeOutboxRepo)

    service = module.MemoryStateTransitionService(object(), "org-1")
    await service.transition(
        item.memory_id,
        action="activate",
        target_status="active",
        actor_id="admin-1",
        trace_id="trace-approve",
        reason="organization_share_approved",
        payload={"trust_score": 0.9, "promotion_score": 1.4},
    )

    vector_row = next(row for row in outbox_rows if row["action"] == "UPSERT_ACTIVE_VECTOR")
    payload = vector_row["payload"]
    assert payload["memory_id"] == item.memory_id
    assert payload["org_id"] == "org-1"
    assert payload["user_id"] == "user-1"
    assert payload["memory_type"] == "quality_pattern"
    assert payload["status"] == "active"
    assert payload["summary"] == item.content_summary
    assert payload["trust_score"] == pytest.approx(0.9)
    assert payload["confidence"] == pytest.approx(0.8)
    assert payload["product_line"] == "fastener"
    assert payload["task_id"] == "task-1"
    assert payload["extra_payload"]["scope_type"] == "org_space"
    assert payload["extra_payload"]["promotion_score"] == pytest.approx(1.4)
