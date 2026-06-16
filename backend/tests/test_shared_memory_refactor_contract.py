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


def test_quality_chat_no_longer_defines_answer_fallbacks():
    source = (BACKEND_ROOT / "agent/subgraphs/quality_chat/graph.py").read_text(encoding="utf-8")

    assert "_general_answer_fallback" not in source
    assert "_fallback_answer" not in source
    assert "_rag_answer_fallback" not in source


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


def test_checkpoint_writes_are_not_silent_noop():
    source = (BACKEND_ROOT / "agent/graphs/memory_manager/checkpointer.py").read_text(encoding="utf-8")

    assert "async def aput_writes" in source
    assert "raise NotImplementedError" in source


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
