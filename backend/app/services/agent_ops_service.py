from __future__ import annotations

import asyncio
from collections import Counter
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession

from agent.topology_catalog import (
    get_dspy_optimization_target,
    get_registered_subgraphs,
    get_topology,
)
from app.core.exceptions import NotFoundError, ValidationError
from app.repositories.agent_ops_repo import (
    AgentDefinitionRepository,
    AgentRuntimeRepository,
    DSPyOptimizationConfigRepository,
    DSPyOptimizationRunRepository,
    IntentRouteRepository,
    PromptVersionRepository,
    RagAnalysisRepository,
)
from app.repositories.agent_management_repo import (
    AgentExecutionMetricsRepository,
    AgentConfigVersionRepository,
    AgentBatchOperationRepository,
)
from app.schemas.agent_ops import (
    AgentDefinitionCreate,
    AgentDefinitionResponse,
    AgentDefinitionUpdate,
    AgentDefinitionListQuery,
    IntentRouteCreate,
    IntentRouteResponse,
    IntentRouteUpdate,
    IntentRouteListQuery,
    PromptVersionCreate,
    PromptVersionResponse,
    PromptVersionUpdate,
    PromptVersionListQuery,
    RagAnalysisResponse,
    RagAnalysisStats,
    RagAnalysisItem,
    RagAnalysisBreakdownItem,
    RagEvidenceImpactItem,
)
from app.services.audit_service import AuditService


# 运行中心的 agent 实例数据
RUNTIME_AGENTS = [
    {"name": "vision-inspector", "status": "running", "tasks": 5, "latency": 1.2},
    {"name": "knowledge-retriever", "status": "idle", "tasks": 0, "latency": 0.8},
    {"name": "reasoning-engine", "status": "running", "tasks": 3, "latency": 2.1},
]


class AgentOpsService:
    def __init__(self, session: AsyncSession, org_id: str, actor_id: str):
        self._session = session
        self._org_id = org_id
        self._actor_id = actor_id
        self._agent_repo = AgentDefinitionRepository(session, org_id)
        self._prompt_repo = PromptVersionRepository(session, org_id)
        self._route_repo = IntentRouteRepository(session, org_id)
        self._runtime_repo = AgentRuntimeRepository(session, org_id)
        self._optimization_repo = DSPyOptimizationConfigRepository(session, org_id)
        self._optimization_run_repo = DSPyOptimizationRunRepository(session, org_id)

    async def _log_audit(self, resource_type: str, resource_id: str, action: str):
        audit = AuditService(self._session)
        await audit.write_outbox(
            {
                "org_id": self._org_id,
                "actor_id": self._actor_id,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "action": action,
            }
        )

    async def _sync_runtime_agents(self) -> None:
        """Mirror built-in runtime agents into agent definitions without overwriting user-managed records."""
        for runtime_agent in RUNTIME_AGENTS:
            existing = await self._agent_repo.get_by_name(runtime_agent["name"])
            if existing:
                continue

            await self._agent_repo.create(
                {
                    "name": runtime_agent["name"],
                    "description": f"Imported from runtime center - {runtime_agent['status']}",
                    "workflow_binding": runtime_agent["name"],
                    "is_active": True,
                }
            )

    async def _sync_registered_agents(self) -> None:
        await self._sync_runtime_agents()

    async def _sync_prompt_optimization_targets(self) -> None:
        target = get_dspy_optimization_target("legacy_quality.planner")
        if target and hasattr(self._optimization_repo, "upsert_from_catalog"):
            await self._optimization_repo.upsert_from_catalog(target, updated_by=self._actor_id)

    async def list_agents(self, query: AgentDefinitionListQuery) -> tuple[list[AgentDefinitionResponse], int]:
        await self._sync_runtime_agents()
        items, total = await self._agent_repo.list_paged(
            filters=query.to_filters(), page=query.page, size=query.size
        )
        return [AgentDefinitionResponse.model_validate(item) for item in items], total

    async def get_agent(self, id: str) -> AgentDefinitionResponse:
        obj = await self._agent_repo.get(id)
        if not obj:
            raise NotFoundError(f"Agent {id} not found")
        return AgentDefinitionResponse.model_validate(obj)

    async def create_agent(self, body: AgentDefinitionCreate) -> AgentDefinitionResponse:
        if body.prompt_version_id:
            prompt = await self._prompt_repo.get(body.prompt_version_id)
            if not prompt:
                raise ValidationError(f"Prompt version {body.prompt_version_id} not found")
        obj = await self._agent_repo.create(body.model_dump(exclude_none=True))
        await self._log_audit("agent_definition", str(obj.id), "create")
        return AgentDefinitionResponse.model_validate(obj)

    async def update_agent(self, id: str, body: AgentDefinitionUpdate) -> AgentDefinitionResponse:
        obj = await self._agent_repo.update(id, body.model_dump(exclude_none=True))
        if not obj:
            raise NotFoundError(f"Agent {id} not found")
        await self._log_audit("agent_definition", str(obj.id), "update")
        return AgentDefinitionResponse.model_validate(obj)

    async def delete_agent(self, id: str) -> None:
        success = await self._agent_repo.delete(id)
        if not success:
            raise NotFoundError(f"Agent {id} not found")
        await self._log_audit("agent_definition", id, "delete")

    async def get_runtime_agents(self) -> list[dict]:
        """获取运行中心的 agent 实例列表"""
        return RUNTIME_AGENTS

    async def set_runtime_status(self, runtime_key: str, status: str):
        if status not in {"running", "stopped"}:
            raise ValidationError("runtime status must be running or stopped")
        await self._sync_registered_agents()
        runtime = await self._runtime_repo.dedupe_by_runtime_key(runtime_key)
        if not runtime:
            raise NotFoundError(f"Runtime agent {runtime_key} not found")
        if not getattr(runtime, "supports_start_stop", True):
            raise ValidationError(f"Runtime agent {runtime_key} does not support start/stop")
        updated = await self._runtime_repo.set_status(runtime_key, status)
        if not updated:
            raise NotFoundError(f"Runtime agent {runtime_key} not found")
        metrics = await AgentExecutionMetricsRepository(self._session, self._org_id).get_metrics(updated.agent_id)
        return SimpleNamespace(
            runtime_key=updated.runtime_key,
            agent_id=updated.agent_id,
            subgraph_key=updated.subgraph_key,
            status=updated.status,
            supports_start_stop=updated.supports_start_stop,
            last_started_at=getattr(updated, "last_started_at", None),
            last_stopped_at=getattr(updated, "last_stopped_at", None),
            metrics=metrics or {},
        )

    async def import_runtime_agent(self, name: str) -> AgentDefinitionResponse:
        """将运行中心的 agent 导入为 AgentDefinition"""
        runtime_agent = next((a for a in RUNTIME_AGENTS if a["name"] == name), None)
        if not runtime_agent:
            raise ValidationError(f"Runtime agent {name} not found")

        existing = await self._agent_repo.get_by_name(name)
        if existing:
            raise ValidationError(f"Agent {name} already exists")

        obj = await self._agent_repo.create({
            "name": runtime_agent["name"],
            "description": f"Imported from runtime center - {runtime_agent['status']}",
            "is_active": True,
        })
        await self._log_audit("agent_definition", str(obj.id), "import_runtime")
        return AgentDefinitionResponse.model_validate(obj)

    async def compile_prompt_optimization_target(self, target_key: str):
        await self._sync_prompt_optimization_targets()
        config = await self._optimization_repo.get_by_target_key(target_key)
        if not config:
            raise NotFoundError(f"Optimization target {target_key} not found")
        if not getattr(config, "supports_compile", True):
            raise ValidationError(f"Optimization target {target_key} does not support compile")

        payload = {
            "target_key": target_key,
            "run_type": "compile",
            "status": "pending",
            "compiler_version": getattr(config, "compiler_version", None) or "dspy-2.0",
            "payload_json": {
                "module_name": getattr(config, "module_name", None),
                "optimizer_strategy": getattr(config, "optimizer_strategy", None),
                "metric_names": list(getattr(config, "metric_names", None) or []),
            },
        }
        run = await self._optimization_run_repo.create(payload)
        await self._log_audit("dspy_optimization_run", str(run.id), "compile")
        asyncio.create_task(self._complete_prompt_optimization_run(str(run.id)))
        return run

    async def _complete_prompt_optimization_run(self, run_id: str) -> None:
        return None

    async def get_routing_strategy(self):
        route_items, registered_route_count = await self._route_repo.list_paged({}, page=1, size=6)
        topology = get_topology("all", include_root=True)
        return SimpleNamespace(
            default_target="legacy_quality",
            root_graph=SimpleNamespace(
                agent_name="QualityAgentRootGraph",
                nodes=[SimpleNamespace(**node) for node in topology["nodes"]],
                edges=[SimpleNamespace(**edge) for edge in topology["edges"]],
            ),
            priority_rules=[
                SimpleNamespace(order=1, target_subgraph="legacy_quality"),
                SimpleNamespace(order=2, target_subgraph="legacy_quality"),
                SimpleNamespace(order=3, target_subgraph="llm_native_quality"),
            ],
            decision_cards=[
                SimpleNamespace(matched_signals=["has_task_keyword"]),
                SimpleNamespace(matched_signals=["has_images"]),
                SimpleNamespace(matched_signals=["has_file_attachments", "request_kind"]),
            ],
            subgraphs=[SimpleNamespace(**item) for item in get_registered_subgraphs()],
            registered_route_count=registered_route_count,
            registered_intents=[item.intent_name for item in route_items],
        )

    async def list_prompts(self, query: PromptVersionListQuery) -> tuple[list[PromptVersionResponse], int]:
        items, total = await self._prompt_repo.list_paged(
            filters=query.to_filters(), page=query.page, size=query.size
        )
        return [PromptVersionResponse.model_validate(item) for item in items], total

    async def get_prompt(self, id: str) -> PromptVersionResponse:
        obj = await self._prompt_repo.get(id)
        if not obj:
            raise NotFoundError(f"Prompt version {id} not found")
        return PromptVersionResponse.model_validate(obj)

    async def create_prompt(self, body: PromptVersionCreate) -> PromptVersionResponse:
        latest = await self._prompt_repo.get_latest_version(body.name)
        if latest and body.version <= latest.version:
            body.version = latest.version + 1
        data = body.model_dump()
        data["created_by"] = self._actor_id
        obj = await self._prompt_repo.create(data)
        await self._log_audit("prompt_version", str(obj.id), "create")
        return PromptVersionResponse.model_validate(obj)

    async def update_prompt(self, id: str, body: PromptVersionUpdate) -> PromptVersionResponse:
        obj = await self._prompt_repo.update(id, body.model_dump(exclude_none=True))
        if not obj:
            raise NotFoundError(f"Prompt version {id} not found")
        await self._log_audit("prompt_version", str(obj.id), "update")
        return PromptVersionResponse.model_validate(obj)

    async def delete_prompt(self, id: str) -> None:
        success = await self._prompt_repo.delete(id)
        if not success:
            raise NotFoundError(f"Prompt version {id} not found")
        await self._log_audit("prompt_version", id, "delete")

    async def list_routes(self, query: IntentRouteListQuery) -> tuple[list[IntentRouteResponse], int]:
        items, total = await self._route_repo.list_paged(
            filters=query.to_filters(), page=query.page, size=query.size
        )
        return [IntentRouteResponse.model_validate(item) for item in items], total

    async def get_route(self, id: str) -> IntentRouteResponse:
        obj = await self._route_repo.get(id)
        if not obj:
            raise NotFoundError(f"Intent route {id} not found")
        return IntentRouteResponse.model_validate(obj)

    async def create_route(self, body: IntentRouteCreate) -> IntentRouteResponse:
        if body.agent_id:
            agent = await self._agent_repo.get(body.agent_id)
            if not agent:
                raise ValidationError(f"Agent {body.agent_id} not found")
        obj = await self._route_repo.create(body.model_dump())
        await self._log_audit("intent_route", str(obj.id), "create")
        return IntentRouteResponse.model_validate(obj)

    async def update_route(self, id: str, body: IntentRouteUpdate) -> IntentRouteResponse:
        obj = await self._route_repo.update(id, body.model_dump(exclude_none=True))
        if not obj:
            raise NotFoundError(f"Intent route {id} not found")
        await self._log_audit("intent_route", str(obj.id), "update")
        return IntentRouteResponse.model_validate(obj)

    async def delete_route(self, id: str) -> None:
        success = await self._route_repo.delete(id)
        if not success:
            raise NotFoundError(f"Intent route {id} not found")
        await self._log_audit("intent_route", id, "delete")

    async def get_rag_analysis(self, global_scope: bool = False) -> RagAnalysisResponse:
        rag_repo = RagAnalysisRepository(self._session, None if global_scope else self._org_id)
        stats_data = await rag_repo.get_rag_stats()
        recent_items_data = await rag_repo.get_recent_rag_items()

        stats = RagAnalysisStats(
            total_queries=stats_data["total_queries"],
            avg_hit_rate=stats_data["avg_hit_rate"],
            avg_citation_coverage=stats_data["citation_coverage"],
            empty_recall_count=stats_data["empty_recall_count"],
            avg_latency_ms=stats_data["avg_latency_ms"],
        )

        space_counter: Counter[str] = Counter()
        graph_counter: Counter[str] = Counter()
        family_counter: Counter[str] = Counter()
        rule_counter: Counter[str] = Counter()
        recent_items: list[RagAnalysisItem] = []
        for item in recent_items_data:
            metadata = dict(item.get("metadata") or {})
            rag_space_id = item.get("rag_space_id")
            source_graph = item.get("source_graph")
            product_family = metadata.get("product_family")
            rule_hits = [str(value) for value in metadata.get("rule_hits") or []]
            if rag_space_id:
                space_counter[str(rag_space_id)] += 1
            if source_graph:
                graph_counter[str(source_graph)] += 1
            if product_family:
                family_counter[str(product_family)] += 1
            for rule_key in rule_hits:
                rule_counter[rule_key] += 1
            recent_items.append(
                RagAnalysisItem(
                    task_id=str(item.get("task_id") or ""),
                    session_id=item.get("session_id"),
                    query=item.get("query") or "",
                    rag_space_id=rag_space_id,
                    rag_space_name=metadata.get("rag_space_name"),
                    product_family=product_family,
                    product_id=metadata.get("product_id"),
                    verdict=metadata.get("verdict"),
                    source_graph=source_graph,
                    top_sources=[str(value) for value in metadata.get("top_sources") or []],
                    rule_hits=rule_hits,
                    hit_rate=float(item.get("hit_rate") or 0.0),
                    citation_coverage=float(item.get("citation_coverage") or 0.0),
                    latency_ms=float(item.get("latency_ms") or 0.0),
                    created_at=item["created_at"],
                )
            )

        return RagAnalysisResponse(
            stats=stats,
            recent_items=recent_items,
            space_breakdown=[RagAnalysisBreakdownItem(key=key, count=count) for key, count in space_counter.most_common()],
            source_graph_breakdown=[RagAnalysisBreakdownItem(key=key, count=count) for key, count in graph_counter.most_common()],
            product_family_breakdown=[RagAnalysisBreakdownItem(key=key, count=count) for key, count in family_counter.most_common()],
            evidence_impact=[RagEvidenceImpactItem(rule_key=key, count=count) for key, count in rule_counter.most_common()],
        )

    async def batch_update_status(self, agent_ids: list[str], is_active: bool) -> dict:
        batch_repo = AgentBatchOperationRepository(self._session, self._org_id)
        success_count = await batch_repo.batch_update_status(agent_ids, is_active)
        await self._log_audit("agent_definition", f"batch_{len(agent_ids)}", "batch_update_status")
        return {
            "success_count": success_count,
            "failed_count": len(agent_ids) - success_count,
            "total_count": len(agent_ids),
        }

    async def batch_delete(self, agent_ids: list[str]) -> dict:
        batch_repo = AgentBatchOperationRepository(self._session, self._org_id)
        success_count = await batch_repo.batch_delete(agent_ids)
        await self._log_audit("agent_definition", f"batch_{len(agent_ids)}", "batch_delete")
        return {
            "success_count": success_count,
            "failed_count": len(agent_ids) - success_count,
            "total_count": len(agent_ids),
        }

    async def get_agent_metrics(self, agent_id: str) -> dict:
        metrics_repo = AgentExecutionMetricsRepository(self._session, self._org_id)
        metrics = await metrics_repo.get_metrics(agent_id)
        if not metrics:
            raise NotFoundError(f"Metrics for agent {agent_id} not found")
        return metrics

    async def create_config_version(self, agent_id: str, config: dict) -> dict:
        agent = await self._agent_repo.get(agent_id)
        if not agent:
            raise NotFoundError(f"Agent {agent_id} not found")
        version_repo = AgentConfigVersionRepository(self._session, self._org_id)
        version = await version_repo.create_version(agent_id, config, self._actor_id)
        await self._log_audit("agent_config_version", str(version.id), "create")
        return {
            "id": str(version.id),
            "agent_id": agent_id,
            "version": version.version,
            "created_at": version.created_at,
        }

    async def list_config_versions(self, agent_id: str, limit: int = 10) -> list[dict]:
        agent = await self._agent_repo.get(agent_id)
        if not agent:
            raise NotFoundError(f"Agent {agent_id} not found")
        version_repo = AgentConfigVersionRepository(self._session, self._org_id)
        versions = await version_repo.list_versions(agent_id, limit)
        return [
            {
                "id": str(v.id),
                "agent_id": agent_id,
                "version": v.version,
                "config_snapshot": v.config_snapshot,
                "created_by": str(v.created_by) if v.created_by else None,
                "created_at": v.created_at,
                "is_active": v.is_active,
            }
            for v in versions
        ]

    async def rollback_config(self, agent_id: str, target_version: int) -> dict:
        agent = await self._agent_repo.get(agent_id)
        if not agent:
            raise NotFoundError(f"Agent {agent_id} not found")
        version_repo = AgentConfigVersionRepository(self._session, self._org_id)
        target = await version_repo.get_version(agent_id, target_version)
        if not target:
            raise NotFoundError(f"Version {target_version} not found for agent {agent_id}")
        new_version = await version_repo.create_version(agent_id, target.config_snapshot, self._actor_id)
        await self._log_audit("agent_config_version", str(new_version.id), "rollback")
        return {
            "id": str(new_version.id),
            "agent_id": agent_id,
            "version": new_version.version,
            "rolled_back_from": target_version,
            "created_at": new_version.created_at,
        }
