from fastapi.routing import APIRoute
from types import SimpleNamespace
from datetime import datetime, timezone

import pytest

from app.api.v1.agent_ops import router
from app.services import agent_ops_service as agent_ops_mod
from agent.topology_catalog import get_dspy_graph_context, get_dspy_optimization_targets
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


def test_prompt_optimization_routes_are_registered_before_dynamic_target_route():
    route_entries = [
        (route.path, route.methods)
        for route in router.routes
        if isinstance(route, APIRoute)
    ]
    route_paths = [path for path, _methods in route_entries]
    route_methods = {path: methods for path, methods in route_entries}

    assert "/agent-ops/prompt-optimization/targets/{target_key}/runs" in route_paths
    assert "/agent-ops/prompt-optimization/targets/{target_key}/config" in route_paths
    assert "/agent-ops/prompt-optimization/targets/{target_key}/compile" in route_paths
    assert "/agent-ops/prompt-optimization/targets/{target_key}/rollback" in route_paths
    assert "/agent-ops/prompt-optimization/targets/{target_key}" in route_paths
    assert route_methods["/agent-ops/prompt-optimization/targets/{target_key}/config"] == {"PUT"}
    assert route_methods["/agent-ops/prompt-optimization/targets/{target_key}/runs"] == {"GET"}
    assert route_methods["/agent-ops/prompt-optimization/targets/{target_key}/compile"] == {"POST"}
    assert route_methods["/agent-ops/prompt-optimization/targets/{target_key}/rollback"] == {"POST"}
    assert route_methods["/agent-ops/prompt-optimization/targets/{target_key}"] == {"GET"}
    assert route_paths.index("/agent-ops/prompt-optimization/targets/{target_key}/runs") < route_paths.index("/agent-ops/prompt-optimization/targets/{target_key}")
    assert route_paths.index("/agent-ops/prompt-optimization/targets/{target_key}/config") < route_paths.index("/agent-ops/prompt-optimization/targets/{target_key}")
    assert route_paths.index("/agent-ops/prompt-optimization/targets/{target_key}/compile") < route_paths.index("/agent-ops/prompt-optimization/targets/{target_key}")
    assert route_paths.index("/agent-ops/prompt-optimization/targets/{target_key}/rollback") < route_paths.index("/agent-ops/prompt-optimization/targets/{target_key}")


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


def test_agent_ops_admin_scope_is_global_for_rag_analysis():
    admin = SimpleNamespace(role="admin", roles=["admin"], org_id="org-admin")
    user = SimpleNamespace(role="user", roles=["user"], org_id="org-user")

    assert agent_ops_api_mod._use_global_scope(admin) is True
    assert agent_ops_api_mod._use_global_scope(user) is False


@pytest.mark.asyncio
async def test_set_runtime_status_dedupes_runtime_key_before_stop():
    class FakeRuntimeRepo:
        def __init__(self):
            self.dedupe_calls = []
            self.set_status_calls = []
            self.runtime = SimpleNamespace(
                runtime_key="Legacy Quality:quality_judgement",
                agent_id="agent-1",
                subgraph_key="quality_judgement",
                status="running",
                supports_start_stop=True,
                last_started_at=None,
                last_stopped_at=None,
            )

        async def dedupe_by_runtime_key(self, runtime_key: str):
            self.dedupe_calls.append(runtime_key)
            return self.runtime

        async def get_by_runtime_key(self, runtime_key: str):
            raise AssertionError("set_runtime_status should not call get_by_runtime_key directly")

        async def set_status(self, runtime_key: str, status: str):
            self.set_status_calls.append((runtime_key, status))
            self.runtime.status = status
            return self.runtime

    class FakeAgentRepo:
        async def get(self, agent_id: str):
            return SimpleNamespace(
                id=agent_id,
                name="Legacy Quality",
                is_active=True,
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
    assert svc._runtime_repo.set_status_calls == [("Legacy Quality:quality_judgement", "stopped")]
    assert data.runtime_key == "Legacy Quality:quality_judgement"
    assert data.status == "stopped"


def test_dspy_optimization_catalog_exposes_expected_targets_and_graph_context():
    targets = get_dspy_optimization_targets()
    target_keys = {item["target_key"] for item in targets}

    assert len(targets) == 5
    assert "quality_judgement.planner" in target_keys
    assert "quality_judgement.contract_inferencer" in target_keys

    graph = get_dspy_graph_context("quality_judgement.review_gate")
    assert graph is not None
    assert graph["focus_node_id"] == "quality_judgement.review_gate"
    assert "quality_judgement.evidence_synthesizer" in graph["upstream_nodes"]
    assert "quality_judgement.task_executor" in graph["downstream_nodes"]


@pytest.mark.asyncio
async def test_compile_prompt_optimization_target_creates_pending_run_and_schedules_job(monkeypatch):
    class FakeOptimizationRepo:
        async def get_by_target_key(self, target_key: str):
            return SimpleNamespace(
                id="cfg-1",
                target_key=target_key,
                supports_compile=True,
                compiler_version="dspy-2.0",
                module_name="ReviewGateModule",
                optimizer_strategy="bootstrap-fewshot",
                metric_names=["faithfulness", "traceability"],
            )

    class FakeRunRepo:
        def __init__(self):
            self.created_payload = None

        async def create(self, payload: dict):
            now = datetime.now(timezone.utc)
            self.created_payload = payload
            return SimpleNamespace(
                id="run-1",
                target_key=payload["target_key"],
                run_type=payload["run_type"],
                status=payload["status"],
                compiler_version=payload["compiler_version"],
                artifact_version=None,
                prompt_version_id=None,
                metrics_snapshot=None,
                error_message=None,
                started_at=None,
                finished_at=None,
                created_at=now,
                updated_at=now,
            )

    scheduled = {}

    def fake_create_task(coro):
        scheduled["created"] = True
        coro.close()
        return SimpleNamespace(cancel=lambda: None)

    svc = agent_ops_mod.AgentOpsService(session=None, org_id="org-1", actor_id="user-1")
    svc._optimization_repo = FakeOptimizationRepo()
    svc._optimization_run_repo = FakeRunRepo()

    async def fake_sync():
        return None

    async def fake_log(*_args, **_kwargs):
        return None

    svc._sync_prompt_optimization_targets = fake_sync
    svc._log_audit = fake_log

    monkeypatch.setattr(agent_ops_mod.asyncio, "create_task", fake_create_task)

    run = await svc.compile_prompt_optimization_target("quality_judgement.review_gate")

    assert svc._optimization_run_repo.created_payload == {
        "target_key": "quality_judgement.review_gate",
        "run_type": "compile",
        "status": "pending",
        "compiler_version": "dspy-2.0",
        "payload_json": {
            "module_name": "ReviewGateModule",
            "optimizer_strategy": "bootstrap-fewshot",
            "metric_names": ["faithfulness", "traceability"],
        },
    }
    assert scheduled == {"created": True}
    assert run.id == "run-1"
    assert run.status == "pending"


@pytest.mark.asyncio
async def test_get_routing_strategy_returns_root_graph_and_priority_rules():
    class FakeRouteRepo:
        async def list_paged(self, filters: dict, page: int, size: int):
            assert filters == {}
            assert page == 1
            assert size == 6
            return [
                SimpleNamespace(intent_name="quality_chat"),
                SimpleNamespace(intent_name="quality_task_create"),
            ], 2

    svc = agent_ops_mod.AgentOpsService(session=None, org_id="org-1", actor_id="user-1")
    svc._route_repo = FakeRouteRepo()

    data = await svc.get_routing_strategy()

    assert data.default_target == "quality_judgement"
    assert data.root_graph.agent_name == "MemoryManagerGraph"
    assert {node.id for node in data.root_graph.nodes} >= {
        "request_intake",
        "memory_context_loader",
        "manager_route_policy",
        "subgraph_runner",
        "result_synthesizer",
        "quality_judgement",
    }
    assert [rule.target_subgraph for rule in data.priority_rules] == [
        "quality_judgement",
        "quality_judgement",
        "quality_judgement",
    ]
    assert [rule.order for rule in data.priority_rules] == [1, 2, 3]
    assert data.decision_cards[0].matched_signals == ["has_task_keyword"]
    assert data.decision_cards[1].matched_signals == ["has_images"]
    assert data.decision_cards[2].matched_signals == ["has_file_attachments", "request_kind"]
    assert {item.subgraph_key for item in data.subgraphs} == {"quality_judgement", "quality_judgement"}
    assert data.registered_route_count == 2
    assert data.registered_intents == ["quality_chat", "quality_task_create"]


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
                    "created_at": now,
                    "metadata": {
                        "rag_space_name": "food",
                        "product_family": "food",
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
                    "created_at": now,
                    "metadata": {
                        "rag_space_name": "food",
                        "product_family": "food",
                        "product_id": "FOOD-003",
                        "verdict": "fail",
                        "expectation_matched": True,
                        "top_sources": ["food-standard.txt", "food-packaging.txt"],
                        "rule_hits": ["food.packaging.seal_integrity"],
                    },
                },
            ]

    original_repo = agent_ops_mod.RagAnalysisRepository
    agent_ops_mod.RagAnalysisRepository = lambda session, org_id: FakeRagRepo()
    try:
        svc = agent_ops_mod.AgentOpsService(session=None, org_id="org-1", actor_id="user-1")
        data = await svc.get_rag_analysis()
    finally:
        agent_ops_mod.RagAnalysisRepository = original_repo

    assert data.stats.total_queries == 3
    assert data.recent_items[0].rag_space_name == "food"
    assert data.recent_items[0].product_family == "food"
    assert data.space_breakdown[0].key == "rag-food"
    assert data.source_graph_breakdown[0].key == "quality_judgement"
    assert data.product_family_breakdown[0].key == "food"
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

    original_repo = agent_ops_mod.RagAnalysisRepository
    agent_ops_mod.RagAnalysisRepository = FakeRagRepo
    try:
        svc = agent_ops_mod.AgentOpsService(session=None, org_id="org-1", actor_id="user-1")
        await svc.get_rag_analysis(global_scope=True)
        await svc.get_rag_analysis(global_scope=False)
    finally:
        agent_ops_mod.RagAnalysisRepository = original_repo

    assert captured_org_ids == [None, "org-1"]
