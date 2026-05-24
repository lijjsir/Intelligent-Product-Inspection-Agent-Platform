from fastapi.routing import APIRoute
from types import SimpleNamespace
from datetime import datetime, timezone

import pytest

from app.api.v1.agent_ops import router
from app.services import agent_ops_service as agent_ops_mod
from app.api.v1 import agent_ops as agent_ops_api_mod


def test_agents_topology_route_is_registered_before_dynamic_agent_route():
    route_paths = [
        route.path
        for route in router.routes
        if isinstance(route, APIRoute) and "GET" in route.methods
    ]

    assert "/agent-ops/agents/topology" in route_paths
    assert "/agent-ops/agents/{id}" in route_paths
    assert route_paths.index("/agent-ops/agents/topology") < route_paths.index("/agent-ops/agents/{id}")


def test_routing_strategy_route_is_registered():
    route_entries = [
        (route.path, route.methods)
        for route in router.routes
        if isinstance(route, APIRoute)
    ]
    route_paths = [path for path, _methods in route_entries]
    route_methods = {path: methods for path, methods in route_entries}

    assert "/agent-ops/routing/strategy" in route_paths
    assert route_methods["/agent-ops/routing/strategy"] == {"GET"}


def test_rag_trace_detail_route_is_registered():
    route_entries = [
        (route.path, route.methods)
        for route in router.routes
        if isinstance(route, APIRoute)
    ]
    route_paths = [path for path, _methods in route_entries]
    route_methods = {path: methods for path, methods in route_entries}

    assert "/agent-ops/rag-analysis/traces/{trace_id}" in route_paths
    assert route_methods["/agent-ops/rag-analysis/traces/{trace_id}"] == {"GET"}


def test_agent_ops_admin_scope_is_global_for_rag_analysis():
    admin = SimpleNamespace(role="admin", roles=["admin"], org_id="org-admin")
    user = SimpleNamespace(role="user", roles=["user"], org_id="org-user")

    assert agent_ops_api_mod._use_global_scope(admin) is True
    assert agent_ops_api_mod._use_global_scope(user) is False


def test_chat_rag_effectiveness_requires_answer_citation_marker():
    item = {
        "source_graph": "chat",
        "sub_route": "rag_qa",
        "hit_count": 1,
        "top_score": 0.72,
        "metadata": {
            "evidence_used": True,
            "answer": "This answer did not include the retrieved citation marker.",
            "used_citations": [{"id": "rag-1", "ref": "RAG-1"}],
        },
    }

    found, used, impacted = agent_ops_mod.AgentOpsService._derive_rag_effectiveness(item)

    assert found is True
    assert used is False
    assert impacted is False


def test_chat_rag_effectiveness_counts_real_answer_citation_marker():
    item = {
        "source_graph": "chat",
        "sub_route": "rag_qa",
        "hit_count": 1,
        "top_score": 0.72,
        "metadata": {
            "answer": "This answer cites the retrieved evidence. [RAG-1]",
            "used_citations": [{"id": "rag-1", "ref": "RAG-1"}],
        },
    }

    found, used, _impacted = agent_ops_mod.AgentOpsService._derive_rag_effectiveness(item)

    assert found is True
    assert used is True


def test_rag_effectiveness_treats_low_score_log_as_not_found(monkeypatch):
    monkeypatch.setattr("app.services.agent_ops_service.settings.rag_score_threshold", 0.55)
    item = {
        "source_graph": "chat",
        "sub_route": "rag_qa",
        "hit_count": 1,
        "top_score": 0.31,
        "metadata": {
            "evidence_found": True,
            "answer": "This answer cites [RAG-1], but retrieval was below threshold.",
            "used_citations": [{"id": "rag-1", "ref": "RAG-1"}],
        },
    }

    found, used, _impacted = agent_ops_mod.AgentOpsService._derive_rag_effectiveness(item)

    assert found is False
    assert used is False


def test_effective_rag_metrics_zero_low_score_rows_for_charts(monkeypatch):
    monkeypatch.setattr("app.services.agent_ops_service.settings.rag_score_threshold", 0.55)
    item = {
        "hit_count": 2,
        "hit_rate": 0.4,
        "citation_coverage": 1.0,
        "top_score": 0.31,
        "metadata": {"score_threshold": 0.55},
    }

    assert agent_ops_mod.AgentOpsService._effective_rag_metrics(item, evidence_used=True) == (0, 0.0, 0.0)


def test_effective_rag_metrics_zero_coverage_when_answer_did_not_use_rag():
    item = {
        "hit_count": 2,
        "hit_rate": 0.4,
        "citation_coverage": 1.0,
        "top_score": 0.72,
        "metadata": {"score_threshold": 0.55},
    }

    assert agent_ops_mod.AgentOpsService._effective_rag_metrics(item, evidence_used=False) == (2, 0.4, 0.0)


def test_inspection_rag_effectiveness_keeps_structured_citations():
    item = {
        "source_graph": "inspection_task",
        "sub_route": "inspection_execute",
        "hit_count": 1,
        "top_score": 0.72,
        "metadata": {
            "answer": "Structured inspection result may not use chat citation markers.",
            "used_citations": [{"id": "rag-1", "kind": "rag"}],
        },
    }

    found, used, _impacted = agent_ops_mod.AgentOpsService._derive_rag_effectiveness(item)

    assert found is True
    assert used is True


@pytest.mark.asyncio
async def test_set_runtime_status_dedupes_runtime_key_before_stop():
    class FakeRuntimeRepo:
        def __init__(self):
            self.dedupe_calls = []
            self.set_runtime_status_calls = []
            self.runtime = SimpleNamespace(
                runtime_key="Legacy Quality:quality_judgement",
                agent_id="agent-1",
                subgraph_key="quality_judgement",
                status="running",
                runtime_status="running",
                supports_start_stop=True,
                last_started_at=None,
                last_stopped_at=None,
                last_error_message=None,
                maintenance_reason=None,
            )

        async def dedupe_by_runtime_key(self, runtime_key: str):
            self.dedupe_calls.append(runtime_key)
            return self.runtime

        async def get_by_runtime_key(self, runtime_key: str):
            raise AssertionError("set_runtime_status should not call get_by_runtime_key directly")

        async def set_runtime_status(self, runtime_key: str, status: str, *, updated_by: str | None = None):
            self.set_runtime_status_calls.append((runtime_key, status, updated_by))
            self.runtime.runtime_status = status
            return self.runtime

        async def create_event(self, _payload: dict):
            return None

    class FakeAgentRepo:
        async def get(self, agent_id: str):
            return SimpleNamespace(
                id=agent_id,
                name="Legacy Quality",
                is_active=True,
                lifecycle_status="active",
                group_key="core",
                route_enabled=True,
                supports_route_toggle=True,
                customer_visible_description="",
            )

    class FakeMetricsRepo:
        def __init__(self, _session, _org_id):
            pass

        async def get_metrics(self, agent_id: str):
            return {
                "execution_count": 3,
                "success_rate": 1.0,
                "avg_latency_ms": 12.5,
                "last_executed_at": None,
            }

    svc = agent_ops_mod.AgentOpsService(session=None, org_id="org-1", actor_id="user-1")
    svc._runtime_repo = FakeRuntimeRepo()
    svc._agent_repo = FakeAgentRepo()
    sync_calls = []

    async def fake_sync():
        sync_calls.append(True)

    svc._sync_registered_agents = fake_sync

    original_metrics_repo = agent_ops_mod.AgentExecutionMetricsRepository
    agent_ops_mod.AgentExecutionMetricsRepository = FakeMetricsRepo
    try:
        data = await svc.set_runtime_status("Legacy Quality:quality_judgement", status="stopped")
    finally:
        agent_ops_mod.AgentExecutionMetricsRepository = original_metrics_repo

    assert sync_calls == [True]
    assert svc._runtime_repo.dedupe_calls == ["Legacy Quality:quality_judgement"]
    assert svc._runtime_repo.set_runtime_status_calls == [
        ("Legacy Quality:quality_judgement", "stopped", "user-1")
    ]
    assert data.runtime_key == "Legacy Quality:quality_judgement"
    assert data.status == "stopped"
    assert data.runtime_status == "stopped"


@pytest.mark.asyncio
async def test_list_runtime_agents_excludes_planned_and_deprecated():
    class FakeRuntimeRepo:
        async def list_with_agents(self):
            return [
                (
                    SimpleNamespace(
                        runtime_key="active:chat",
                        agent_id="agent-1",
                        subgraph_key="chat",
                        status="running",
                        runtime_status="running",
                        supports_start_stop=True,
                        last_started_at=None,
                        last_stopped_at=None,
                        last_error_message=None,
                        maintenance_reason=None,
                    ),
                    SimpleNamespace(
                        id="agent-1",
                        name="Quality Chat",
                        is_active=True,
                        lifecycle_status="active",
                        group_key="core",
                        route_enabled=True,
                        supports_route_toggle=True,
                        customer_visible_description="chat",
                    ),
                ),
                (
                    SimpleNamespace(
                        runtime_key="planned:market_monitor",
                        agent_id="agent-2",
                        subgraph_key="market_monitor",
                        status="stopped",
                        runtime_status="stopped",
                        supports_start_stop=False,
                        last_started_at=None,
                        last_stopped_at=None,
                        last_error_message=None,
                        maintenance_reason=None,
                    ),
                    SimpleNamespace(
                        id="agent-2",
                        name="Market Monitor",
                        is_active=False,
                        lifecycle_status="planned",
                        group_key="planned",
                        route_enabled=False,
                        supports_route_toggle=False,
                        customer_visible_description="planned",
                    ),
                ),
                (
                    SimpleNamespace(
                        runtime_key="deprecated:legacy",
                        agent_id="agent-3",
                        subgraph_key="legacy",
                        status="stopped",
                        runtime_status="stopped",
                        supports_start_stop=False,
                        last_started_at=None,
                        last_stopped_at=None,
                        last_error_message=None,
                        maintenance_reason=None,
                    ),
                    SimpleNamespace(
                        id="agent-3",
                        name="Legacy Agent",
                        is_active=False,
                        lifecycle_status="deprecated",
                        group_key="legacy",
                        route_enabled=False,
                        supports_route_toggle=False,
                        customer_visible_description="deprecated",
                    ),
                ),
            ]

    class FakeMetricsRepo:
        def __init__(self, _session, _org_id):
            pass

        async def get_metrics(self, agent_id: str):
            return {"execution_count": 1, "success_rate": 1.0, "avg_latency_ms": 10.0, "last_executed_at": None}

    svc = agent_ops_mod.AgentOpsService(session=None, org_id="org-1", actor_id="user-1")
    svc._runtime_repo = FakeRuntimeRepo()

    async def fake_sync():
        return None

    svc._sync_registered_agents = fake_sync
    original_metrics_repo = agent_ops_mod.AgentExecutionMetricsRepository
    agent_ops_mod.AgentExecutionMetricsRepository = FakeMetricsRepo
    try:
        items = await svc.list_runtime_agents()
    finally:
        agent_ops_mod.AgentExecutionMetricsRepository = original_metrics_repo

    assert [item.agent_name for item in items] == ["Quality Chat"]


@pytest.mark.asyncio
async def test_get_agents_topology_runtime_hides_planned_and_deprecated_nodes():
    class FakeRuntimeRepo:
        async def list_with_agents(self):
            return [
                (
                    SimpleNamespace(
                        runtime_key="quality:quality_judgement",
                        agent_id="agent-1",
                        subgraph_key="quality_judgement",
                        status="running",
                        runtime_status="running",
                    ),
                    SimpleNamespace(
                        id="agent-1",
                        name="Quality Judgement",
                        subgraph_key="quality_judgement",
                        lifecycle_status="active",
                        route_enabled=True,
                    ),
                ),
                (
                    SimpleNamespace(
                        runtime_key="market_monitor:market_monitor",
                        agent_id="agent-2",
                        subgraph_key="market_monitor",
                        status="stopped",
                        runtime_status="stopped",
                    ),
                    SimpleNamespace(
                        id="agent-2",
                        name="Market Monitor",
                        subgraph_key="market_monitor",
                        lifecycle_status="planned",
                        route_enabled=False,
                    ),
                ),
                (
                    SimpleNamespace(
                        runtime_key="legacy:legacy",
                        agent_id="agent-3",
                        subgraph_key="legacy_quality",
                        status="stopped",
                        runtime_status="stopped",
                    ),
                    SimpleNamespace(
                        id="agent-3",
                        name="Legacy Agent",
                        subgraph_key="legacy_quality",
                        lifecycle_status="deprecated",
                        route_enabled=False,
                    ),
                ),
            ]

    class FakeMetricsRepo:
        def __init__(self, _session, _org_id):
            pass

        async def get_metrics(self, agent_id: str):
            return {"execution_count": 2, "success_rate": 1.0, "avg_latency_ms": 20.0, "last_executed_at": None}

    svc = agent_ops_mod.AgentOpsService(session=None, org_id="org-1", actor_id="user-1")
    svc._runtime_repo = FakeRuntimeRepo()

    async def fake_sync():
        return None

    svc._sync_registered_agents = fake_sync
    original_metrics_repo = agent_ops_mod.AgentExecutionMetricsRepository
    agent_ops_mod.AgentExecutionMetricsRepository = FakeMetricsRepo
    try:
        topology = await svc.get_agents_topology("all", mode="runtime", include_planned=False)
    finally:
        agent_ops_mod.AgentExecutionMetricsRepository = original_metrics_repo

    node_ids = {node.id for node in topology.nodes}
    assert "request_intake" in node_ids
    assert "agent:quality_judgement" in node_ids
    assert "agent:market_monitor" not in node_ids
    assert "agent:legacy_quality" not in node_ids


@pytest.mark.asyncio
async def test_pause_and_resume_route_also_updates_runtime_status():
    class FakeRuntimeRepo:
        def __init__(self):
            self.runtime = SimpleNamespace(
                runtime_key="quality:quality_judgement",
                agent_id="agent-1",
                subgraph_key="quality_judgement",
                status="running",
                runtime_status="running",
                supports_start_stop=True,
                last_started_at=None,
                last_stopped_at=None,
                last_error_message=None,
                maintenance_reason=None,
            )
            self.runtime_status_calls = []
            self.events = []

        async def dedupe_by_runtime_key(self, runtime_key: str):
            assert runtime_key == "quality:quality_judgement"
            return self.runtime

        async def set_runtime_status(self, runtime_key: str, status: str, *, updated_by: str | None = None):
            self.runtime_status_calls.append((runtime_key, status, updated_by))
            self.runtime.status = status
            self.runtime.runtime_status = status
            return self.runtime

        async def create_event(self, payload: dict):
            self.events.append(payload)
            return None

    class FakeAgentRepo:
        def __init__(self):
            self.agent = SimpleNamespace(
                id="agent-1",
                name="Quality Judgement",
                is_active=True,
                lifecycle_status="active",
                group_key="core",
                route_enabled=True,
                supports_route_toggle=True,
                customer_visible_description="quality",
            )

        async def get(self, agent_id: str):
            assert agent_id == "agent-1"
            return self.agent

    class FakeMetricsRepo:
        def __init__(self, _session, _org_id):
            pass

        async def get_metrics(self, agent_id: str):
            return {"execution_count": 0, "success_rate": 0.0, "avg_latency_ms": 0.0, "last_executed_at": None}

    class FakeSession:
        async def flush(self):
            return None

    svc = agent_ops_mod.AgentOpsService(session=FakeSession(), org_id="org-1", actor_id="user-1")
    svc._runtime_repo = FakeRuntimeRepo()
    svc._agent_repo = FakeAgentRepo()

    async def fake_sync():
        return None

    svc._sync_registered_agents = fake_sync
    original_metrics_repo = agent_ops_mod.AgentExecutionMetricsRepository
    agent_ops_mod.AgentExecutionMetricsRepository = FakeMetricsRepo
    try:
        paused = await svc.pause_route("quality:quality_judgement", "maintenance")
        resumed = await svc.resume_route("quality:quality_judgement")
    finally:
        agent_ops_mod.AgentExecutionMetricsRepository = original_metrics_repo

    assert svc._runtime_repo.runtime_status_calls == [
        ("quality:quality_judgement", "stopped", "user-1"),
        ("quality:quality_judgement", "running", "user-1"),
    ]
    assert paused.route_enabled is False
    assert paused.runtime_status == "stopped"
    assert resumed.route_enabled is True
    assert resumed.runtime_status == "running"


@pytest.mark.asyncio
async def test_get_agents_topology_specific_agent_returns_agent_overview_slice():
    class FakeRuntimeRepo:
        async def list_with_agents(self):
            return [
                (
                    SimpleNamespace(
                        runtime_key="chat:chat",
                        agent_id="agent-1",
                        subgraph_key="chat",
                        status="running",
                        runtime_status="running",
                        last_started_at=None,
                    ),
                    SimpleNamespace(
                        id="agent-1",
                        name="Quality Chat",
                        subgraph_key="chat",
                        lifecycle_status="active",
                        route_enabled=True,
                    ),
                ),
                (
                    SimpleNamespace(
                        runtime_key="quality:quality_judgement",
                        agent_id="agent-2",
                        subgraph_key="quality_judgement",
                        status="running",
                        runtime_status="running",
                        last_started_at=None,
                    ),
                    SimpleNamespace(
                        id="agent-2",
                        name="Quality Judgement",
                        subgraph_key="quality_judgement",
                        lifecycle_status="active",
                        route_enabled=True,
                    ),
                ),
            ]

    class FakeMetricsRepo:
        def __init__(self, _session, _org_id):
            pass

        async def get_metrics(self, agent_id: str):
            return {"execution_count": 1, "success_rate": 1.0, "avg_latency_ms": 8.0, "last_executed_at": None}

    svc = agent_ops_mod.AgentOpsService(session=None, org_id="org-1", actor_id="user-1")
    svc._runtime_repo = FakeRuntimeRepo()

    async def fake_sync():
        return None

    svc._sync_registered_agents = fake_sync
    original_metrics_repo = agent_ops_mod.AgentExecutionMetricsRepository
    agent_ops_mod.AgentExecutionMetricsRepository = FakeMetricsRepo
    try:
        topology = await svc.get_agents_topology("chat", mode="design", include_planned=False)
    finally:
        agent_ops_mod.AgentExecutionMetricsRepository = original_metrics_repo

    node_ids = {node.id for node in topology.nodes}
    assert node_ids >= {
        "request_intake",
        "memory_context_loader",
        "manager_route_policy",
        "subgraph_runner",
        "result_synthesizer",
        "agent:chat",
    }
    assert "agent:quality_judgement" not in node_ids


@pytest.mark.asyncio
async def test_get_routing_strategy_returns_root_graph_and_priority_rules():
    class FakeRouteRepo:
        async def list_paged(self, filters: dict, page: int, size: int):
            assert filters == {}
            assert page == 1
            assert size == 6
            return [
                SimpleNamespace(intent_name="chat"),
                SimpleNamespace(intent_name="quality_task_create"),
            ], 2

    svc = agent_ops_mod.AgentOpsService(session=None, org_id="org-1", actor_id="user-1")
    svc._route_repo = FakeRouteRepo()

    data = await svc.get_routing_strategy()

    assert data.default_target == "chat"
    assert data.root_graph.agent_name == "MemoryManagerGraph"
    assert {node.id for node in data.root_graph.nodes} >= {
        "request_intake",
        "memory_context_loader",
        "manager_route_policy",
        "subgraph_runner",
        "result_synthesizer",
        "quality_judgement",
    }
    from agent.router.route_policy import AgentRoutePolicy

    engine_rules = AgentRoutePolicy.get_rules()
    assert len(data.priority_rules) == len(engine_rules)
    assert data.priority_rules[0].order == 1
    assert data.priority_rules[0].target_subgraph == "inspection_task"
    assert [item.order for item in data.priority_rules] == [rule["priority"] for rule in engine_rules]
    assert {item.target_subgraph for item in data.priority_rules} >= {"inspection_task", "chat"}
    # decision_cards derived from engine rules
    assert len(data.decision_cards) >= 1
    # subgraphs now iterate all registered subgraphs
    assert len(data.subgraphs) >= 1
    assert data.registered_route_count == 2
    assert data.registered_intents == ["chat", "quality_task_create"]


@pytest.mark.asyncio
async def test_get_rag_analysis_returns_breakdowns_and_evidence_impact():
    class FakeRagRepo:
        async def get_rag_stats(self, days: int = 7):
            assert days == 7
            return {
                "total_queries": 3,
                "avg_hit_rate": 0.75,
                "citation_coverage": 0.66,
                "empty_recall_count": 0,
                "avg_latency_ms": 18.0,
            }

        async def get_recent_rag_items(self, limit: int = 200):
            assert limit == 200
            now = datetime.now(timezone.utc)
            return [
                {
                    "task_id": "task-1",
                    "session_id": "session-1",
                    "query": "food quality standard",
                    "rag_space_id": "rag-food",
                    "hit_count": 2,
                    "hit_rate": 1.0,
                    "citation_coverage": 1.0,
                    "latency_ms": 12,
                    "source_graph": "quality_judgement",
                    "agent_name": "Inspection Task Agent",
                    "sub_route": "task_create",
                    "trace_id": "trace-1",
                    "top_score": 0.93,
                    "created_at": now,
                    "metadata": {
                        "product_id": "FOOD-001",
                        "verdict": "pass",
                        "expectation_matched": True,
                        "top_sources": ["food-standard.txt"],
                        "rule_hits": ["food.traceability.qr_code_required"],
                    },
                },
                {
                    "task_id": "task-2",
                    "session_id": "session-2",
                    "query": "food packaging seal integrity",
                    "rag_space_id": "rag-food",
                    "hit_count": 1,
                    "hit_rate": 0.5,
                    "citation_coverage": 0.4,
                    "latency_ms": 24,
                    "source_graph": "quality_judgement",
                    "agent_name": "",
                    "sub_route": "task_review",
                    "trace_id": "trace-2",
                    "top_score": 0.67,
                    "created_at": now,
                    "metadata": {
                        "rag_space_name": "food",
                        "product_id": "FOOD-003",
                        "verdict": "fail",
                        "expectation_matched": True,
                        "top_sources": ["food-standard.txt", "food-packaging.txt"],
                        "rule_hits": ["food.packaging.seal_integrity"],
                    },
                },
                {
                    "task_id": "task-3",
                    "session_id": "session-3",
                    "query": "stale unknown row",
                    "rag_space_id": "unknown",
                    "hit_count": 0,
                    "hit_rate": 0.0,
                    "citation_coverage": 0.0,
                    "latency_ms": 32,
                    "source_graph": "quality_judgement",
                    "agent_name": "Inspection Task Agent",
                    "sub_route": "task_create",
                    "trace_id": "trace-3",
                    "top_score": 0.0,
                    "created_at": now,
                    "metadata": {
                        "rag_space_name": "unknown",
                        "verdict": "warning",
                        "expectation_matched": False,
                        "top_sources": [],
                        "rule_hits": [],
                    },
                },
            ]

    class FakeSpaceRepo:
        def __init__(self, _session):
            pass

        async def list_for_org(self, *, org_id: str, owner_user_id: str | None = None, limit: int = 200):
            assert org_id == "org-1"
            assert owner_user_id is None
            assert limit == 500
            return [
                SimpleNamespace(id="rag-food", name="食品知识库"),
                SimpleNamespace(id="rag-drink", name="饮料知识库"),
            ]

    class FakeAgentRepo:
        async def list_all_active(self):
            return [
                SimpleNamespace(name="Inspection Task Agent", subgraph_key="quality_judgement"),
                SimpleNamespace(name="Quality Chat", subgraph_key="chat"),
            ]

    original_repo = agent_ops_mod.RagAnalysisRepository
    original_space_repo = agent_ops_mod.RagSpaceRepository
    agent_ops_mod.RagAnalysisRepository = lambda session, org_id: FakeRagRepo()
    agent_ops_mod.RagSpaceRepository = FakeSpaceRepo
    try:
        svc = agent_ops_mod.AgentOpsService(session=None, org_id="org-1", actor_id="user-1")
        svc._agent_repo = FakeAgentRepo()
        data = await svc.get_rag_analysis()
    finally:
        agent_ops_mod.RagAnalysisRepository = original_repo
        agent_ops_mod.RagSpaceRepository = original_space_repo

    assert data.stats.total_queries == 3
    assert [(item.key, item.label) for item in data.space_options] == [("rag-food", "食品知识库"), ("rag-drink", "饮料知识库")]
    assert [(item.key, item.label) for item in data.source_agent_options] == [
        ("Inspection Task Agent", "Inspection Task Agent"),
        ("Quality Chat", "Quality Chat"),
    ]
    assert data.recent_items[0].rag_space_name == "食品知识库"
    assert data.recent_items[0].source_agent == "Inspection Task Agent"
    assert data.recent_items[1].source_agent == "Inspection Task Agent"
    assert data.recent_items[1].sub_route == "task_review"
    assert data.recent_items[1].trace_id == "trace-2"
    assert data.space_breakdown[0].key == "rag-food"
    assert data.space_breakdown[0].label == "食品知识库"
    assert [item.key for item in data.space_breakdown] == ["rag-food"]
    assert data.source_agent_breakdown[0].key == "Inspection Task Agent"
    assert {item.rule_key for item in data.evidence_impact} == {
        "food.traceability.qr_code_required",
        "food.packaging.seal_integrity",
    }


@pytest.mark.asyncio
async def test_get_rag_analysis_uses_global_scope_when_requested():
    captured_org_ids: list[str | None] = []

    class FakeRagRepo:
        def __init__(self, _session, org_id):
            captured_org_ids.append(org_id)

        async def get_rag_stats(self, days: int = 7):
            return {
                "total_queries": 1,
                "avg_hit_rate": 1.0,
                "citation_coverage": 1.0,
                "empty_recall_count": 0,
                "avg_latency_ms": 12.0,
            }

        async def get_recent_rag_items(self, limit: int = 200):
            return []

    class FakeSpaceRepo:
        def __init__(self, _session):
            pass

        async def list_for_org(self, *, org_id: str, owner_user_id: str | None = None, limit: int = 200):
            assert org_id == "org-1"
            assert owner_user_id is None
            assert limit == 500
            return []

    class FakeAgentRepo:
        async def list_all_active(self):
            return []

    original_repo = agent_ops_mod.RagAnalysisRepository
    original_space_repo = agent_ops_mod.RagSpaceRepository
    agent_ops_mod.RagAnalysisRepository = FakeRagRepo
    agent_ops_mod.RagSpaceRepository = FakeSpaceRepo
    try:
        svc = agent_ops_mod.AgentOpsService(session=None, org_id="org-1", actor_id="user-1")
        svc._agent_repo = FakeAgentRepo()
        await svc.get_rag_analysis(global_scope=True)
        await svc.get_rag_analysis(global_scope=False)
    finally:
        agent_ops_mod.RagAnalysisRepository = original_repo
        agent_ops_mod.RagSpaceRepository = original_space_repo

    assert captured_org_ids == [None, "org-1"]


@pytest.mark.asyncio
async def test_get_rag_analysis_normalizes_legacy_quality_rows_to_chat_agent():
    class FakeRagRepo:
        async def get_rag_stats(self, days: int = 7):
            return {
                "total_queries": 1,
                "avg_hit_rate": 0.25,
                "citation_coverage": 1.0,
                "empty_recall_count": 0,
                "avg_latency_ms": 18.0,
            }

        async def get_recent_rag_items(self, limit: int = 200):
            now = datetime.now(timezone.utc)
            return [
                {
                    "task_id": "",
                    "session_id": "session-1",
                    "query": "legacy rag question",
                    "rag_space_id": "rag-food",
                    "top_k": 4,
                    "hit_count": 1,
                    "hit_rate": 0.25,
                    "citation_coverage": 1.0,
                    "latency_ms": 18,
                    "source_graph": "quality_judgement",
                    "agent_name": "",
                    "sub_route": "",
                    "trace_id": None,
                    "top_score": 0.69,
                    "created_at": now,
                    "metadata": {
                        "intent": "rag_qa",
                        "retrieved_chunks": [{"chunk_id": "chunk-1"}],
                        "used_citations": [{"id": "rag-1"}],
                        "rule_hits": [],
                    },
                }
            ]

    class FakeSpaceRepo:
        def __init__(self, _session):
            pass

        async def list_for_org(self, *, org_id: str, owner_user_id: str | None = None, limit: int = 200):
            return [SimpleNamespace(id="rag-food", name="食品知识库")]

    class FakeAgentRepo:
        async def list_all_active(self):
            return [
                SimpleNamespace(name="Quality Chat", subgraph_key="chat"),
                SimpleNamespace(name="Inspection Task Agent", subgraph_key="inspection_task"),
                SimpleNamespace(name="Quality Judgement", subgraph_key="quality_judgement"),
            ]

    original_repo = agent_ops_mod.RagAnalysisRepository
    original_space_repo = agent_ops_mod.RagSpaceRepository
    agent_ops_mod.RagAnalysisRepository = lambda session, org_id: FakeRagRepo()
    agent_ops_mod.RagSpaceRepository = FakeSpaceRepo
    try:
        svc = agent_ops_mod.AgentOpsService(session=None, org_id="org-1", actor_id="user-1")
        svc._agent_repo = FakeAgentRepo()
        data = await svc.get_rag_analysis()
    finally:
        agent_ops_mod.RagAnalysisRepository = original_repo
        agent_ops_mod.RagSpaceRepository = original_space_repo

    assert data.recent_items[0].source_graph == "chat"
    assert data.recent_items[0].source_agent == "Quality Chat"
    assert data.recent_items[0].sub_route == "rag_qa"
    assert data.recent_items[0].evidence_found is True
    assert data.recent_items[0].evidence_used is False
    assert data.recent_items[0].hit_rate == 0.25
    assert data.recent_items[0].citation_coverage == 0.0
    assert data.recent_items[0].verdict_impacted is False


@pytest.mark.asyncio
async def test_get_rag_trace_detail_returns_database_backed_payload():
    captured_org_ids: list[str | None] = []

    class FakeRagRepo:
        def __init__(self, _session, org_id):
            captured_org_ids.append(org_id)

        async def get_trace_detail(self, trace_id: str):
            assert trace_id == "trace-1"
            now = datetime.now(timezone.utc)
            return {
                "query": "苹果划痕怎么判定",
                "rag_space_id": "rag-food",
                "source_graph": "quality_judgement",
                "agent_name": "Inspection Task Agent",
                "sub_route": "inspection_execute",
                "top_k": 4,
                "hit_count": 2,
                "hit_rate": 0.5,
                "citation_coverage": 1.0,
                "latency_ms": 126,
                "trace_id": "trace-1",
                "top_score": 0.91,
                "metadata": {
                    "rag_space_name": "食品知识库",
                    "top_sources": ["apple-spec.pdf"],
                    "rule_hits": ["apple.surface.scratch_limit"],
                    "verdict": "pass",
                    "product_family": "food",
                    "expectation_matched": True,
                    "evidence_found": True,
                    "evidence_used": True,
                    "verdict_impacted": True,
                    "retrieval_config": {"top_k": 4, "scope_node_ids": ["n-1"]},
                    "retrieved_chunks": [{"chunk_id": "chunk-1", "source": "apple-spec.pdf"}],
                    "used_citations": [{"id": "rag-1"}],
                    "answer": "超过 3mm 的划痕通常判定为不合格。",
                    "result": {"verdict": "pass"},
                },
                "created_at": now,
            }

    class FakeSpaceRepo:
        def __init__(self, _session):
            pass

        async def list_for_org(self, *, org_id: str, owner_user_id: str | None = None, limit: int = 200):
            assert org_id == "org-1"
            assert owner_user_id is None
            assert limit == 500
            return [SimpleNamespace(id="rag-food", name="食品知识库")]

    class FakeAgentRepo:
        async def list_all_active(self):
            return [
                SimpleNamespace(name="Inspection Task Agent", subgraph_key="quality_judgement"),
                SimpleNamespace(name="Quality Chat", subgraph_key="chat"),
            ]

    original_repo = agent_ops_mod.RagAnalysisRepository
    original_space_repo = agent_ops_mod.RagSpaceRepository
    agent_ops_mod.RagAnalysisRepository = FakeRagRepo
    agent_ops_mod.RagSpaceRepository = FakeSpaceRepo
    try:
        svc = agent_ops_mod.AgentOpsService(session=None, org_id="org-1", actor_id="user-1")
        svc._agent_repo = FakeAgentRepo()
        data = await svc.get_rag_trace_detail("trace-1")
    finally:
        agent_ops_mod.RagAnalysisRepository = original_repo
        agent_ops_mod.RagSpaceRepository = original_space_repo

    assert captured_org_ids == ["org-1"]
    assert data.query == "苹果划痕怎么判定"
    assert data.rag_space_name == "食品知识库"
    assert data.source_agent == "Inspection Task Agent"
    assert data.top_k == 4
    assert data.retrieval_config["scope_node_ids"] == ["n-1"]
    assert data.retrieved_chunks[0]["chunk_id"] == "chunk-1"
    assert data.used_citations[0]["id"] == "rag-1"
    assert data.rule_hits == ["apple.surface.scratch_limit"]
    assert data.verdict == "pass"
    assert data.evidence_found is True
    assert data.evidence_used is True
    assert data.verdict_impacted is True
    assert data.answer == "超过 3mm 的划痕通常判定为不合格。"
    assert data.result == {"verdict": "pass"}
