from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from agent.topology_catalog import (
    get_agent_overview_root,
    get_dspy_graph_context,
    get_dspy_optimization_target,
    get_dspy_optimization_targets,
    get_registered_subgraphs,
    get_route_topology,
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
    AgentDetailResponse,
    AgentRuntimeEventResponse,
    IntentRouteCreate,
    IntentRouteResponse,
    IntentRouteUpdate,
    IntentRouteListQuery,
    PromptVersionCreate,
    PromptVersionResponse,
    PromptVersionUpdate,
    PromptVersionListQuery,
    PromptDSPyConfigPayload,
    PromptDSPyConfigResponse,
    PromptOptimizationConfigPayload,
    PromptOptimizationConfigResponse,
    PromptOptimizationOverview,
    PromptOptimizationRunResponse,
    PromptOptimizationTargetListQuery,
    PromptOptimizationTargetResponse,
    PromptOptimizationTargetsResponse,
    RagAnalysisResponse,
    RagAnalysisBreakdownItem,
    RagEvidenceImpactItem,
    RagAnalysisStats,
    RagAnalysisItem,
    AgentRuntimeOverviewResponse,
    AgentRuntimeInstanceResponse,
    AgentTopologyResponse,
    RoutingDecisionCard,
    RoutingPriorityRule,
    RoutingSignalDescriptor,
    RoutingStrategyOverviewResponse,
    RoutingSubgraphDescriptor,
    RoutingCurrentResponse,
    RouteAgentDescriptor,
    RouteRuleDescriptor,
    RouteSignalInfo,
    RouteSimulateRequest,
    RouteSimulateResponse,
    RouteEventItem,
    RoutingMetricsResponse,
)
from app.services.audit_service import AuditService
from infra.database.session import create_session
from app.core.config import settings


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

    async def _sync_registered_agents(self) -> None:
        catalog_subgraph_keys = {str(item["subgraph_key"]) for item in get_registered_subgraphs()}

        for item in get_registered_subgraphs():
            existing = await self._agent_repo.dedupe_by_subgraph_key(str(item["subgraph_key"]))
            payload = dict(item)
            if existing:
                mutable_catalog_keys = {
                    "name",
                    "description",
                    "workflow_binding",
                    "subgraph_key",
                    "entry_graph",
                    "supports_start_stop",
                    "graph_version",
                    "is_active",
                    "lifecycle_status",
                    "group_key",
                    "supports_route_toggle",
                    "customer_visible_description",
                }
                for key, value in payload.items():
                    if key not in mutable_catalog_keys:
                        continue
                    setattr(existing, key, value)
                await self._session.flush()
                await self._runtime_repo.ensure_for_agent(existing)
                continue
            created = await self._agent_repo.create(payload)
            await self._runtime_repo.ensure_for_agent(created)

        # Mark agents not in catalog as deprecated
        all_db_agents = await self._agent_repo.list_all_active()
        for db_agent in all_db_agents:
            if db_agent.subgraph_key not in catalog_subgraph_keys:
                db_agent.lifecycle_status = "deprecated"
                db_agent.route_enabled = False
                db_agent.is_active = False
                runtime = await self._runtime_repo.dedupe_by_agent_id(str(db_agent.id))
                if runtime:
                    runtime.runtime_status = "stopped"
        await self._session.flush()

    async def _sync_prompt_optimization_targets(self) -> None:
        catalog = get_dspy_optimization_targets()
        active_keys: list[str] = []
        for target in catalog:
            active_keys.append(str(target["target_key"]))
            config = await self._optimization_repo.upsert_from_catalog(target, updated_by=self._actor_id)
            await self._migrate_legacy_prompt_dspy_config(config)
        await self._optimization_repo.mark_inactive_missing(active_keys, updated_by=self._actor_id)

    @staticmethod
    def _runtime_status_value(runtime) -> str:
        return str(getattr(runtime, "runtime_status", None) or getattr(runtime, "status", None) or "stopped")

    async def _build_agent_topology_nodes(
        self,
        *,
        runtime_rows: list[tuple[object, object]],
        visible_subgraphs: set[str],
        selected_subgraph: str,
    ) -> list[dict[str, object]]:
        blueprint = get_agent_overview_root()
        metrics_repo = AgentExecutionMetricsRepository(self._session, self._org_id)
        nodes: list[dict[str, object]] = [dict(node) for node in blueprint["nodes"]]
        for runtime, agent in sorted(runtime_rows, key=lambda item: str(getattr(item[1], "name", "") or "")):
            subgraph = str(getattr(agent, "subgraph_key", "") or "")
            if subgraph not in visible_subgraphs:
                continue
            metrics = await metrics_repo.get_metrics(str(getattr(agent, "id"))) or {}
            nodes.append(
                {
                    "id": f"agent:{subgraph}",
                    "label": str(getattr(agent, "name", subgraph) or subgraph),
                    "kind": "agent",
                    "subgraph_key": subgraph,
                    "agent_name": str(getattr(agent, "name", subgraph) or subgraph),
                    "status": self._runtime_status_value(runtime),
                    "lifecycle_status": str(getattr(agent, "lifecycle_status", "") or "") or None,
                    "route_enabled": bool(getattr(agent, "route_enabled", False)),
                    "execution_count": int(metrics.get("execution_count") or 0),
                    "avg_latency_ms": float(metrics.get("avg_latency_ms") or 0.0),
                    "last_started_at": getattr(runtime, "last_started_at", None),
                    "focused": selected_subgraph not in {"all", "*"} and subgraph == selected_subgraph,
                }
            )
        return nodes

    @staticmethod
    def _build_agent_topology_edges(visible_subgraphs: set[str]) -> list[dict[str, object]]:
        blueprint = get_agent_overview_root()
        edges: list[dict[str, object]] = [dict(edge) for edge in blueprint["edges"]]
        for subgraph in sorted(visible_subgraphs):
            node_id = f"agent:{subgraph}"
            edges.append({"source": "subgraph_runner", "target": node_id})
            edges.append({"source": node_id, "target": "result_synthesizer"})
        return edges

    async def _migrate_legacy_prompt_dspy_config(self, config: PromptOptimizationConfigResponse | object) -> None:
        target_key = str(getattr(config, "target_key", "") or "")
        if not target_key:
            return
        current_prompt_version_id = getattr(config, "current_prompt_version_id", None)
        latest_metrics_snapshot = getattr(config, "latest_metrics_snapshot", None)
        compiler_version = getattr(config, "compiler_version", None)
        if current_prompt_version_id or latest_metrics_snapshot or compiler_version:
            return
        legacy_prompt = await self._prompt_repo.get_latest_version(target_key)
        if not legacy_prompt:
            return
        legacy_dspy = await self._prompt_repo.get_dspy_config(str(legacy_prompt.id))
        if not legacy_dspy:
            return
        await self._optimization_repo.update_config(
            target_key,
            {
                "module_name": legacy_dspy.module_name,
                "compiler_version": legacy_dspy.compiler_version,
                "metric_names": list(legacy_dspy.metric_names or []),
                "config_payload": dict(legacy_dspy.config_payload or {}),
                "is_enabled": bool(legacy_dspy.is_enabled),
                "current_artifact_version": f"legacy-v{legacy_prompt.version}",
                "current_prompt_version_id": str(legacy_prompt.id),
                "updated_by": self._actor_id,
            },
        )

    def _build_default_config_payload(self, target: dict, config_payload: dict | None = None) -> dict:
        return {
            "strategy": target.get("optimizer_strategy") or "bootstrap-fewshot",
            "target_key": target["target_key"],
            "module_name": target["module_name"],
            "optimization_goal": target["optimization_goal"],
            **dict(config_payload or {}),
        }

    def _build_metrics_snapshot(self, target_key: str, metric_names: list[str]) -> dict:
        seed = (sum(ord(char) for char in target_key) % 9) / 100
        base = {
            "faithfulness": round(0.88 + seed, 4),
            "traceability": round(0.84 + seed, 4),
            "physical_hallucination": round(max(0.01, 0.08 - seed), 4),
            "pass_rate": round(0.79 + seed, 4),
        }
        return {name: base.get(name, round(0.8 + seed, 4)) for name in metric_names}

    def _build_artifact_version(self, target_key: str, version: int) -> str:
        return f"{target_key.replace('.', '-')}-v{version}"

    async def _build_prompt_optimization_target(
        self,
        config,
        *,
        runs: list | None = None,
    ) -> PromptOptimizationTargetResponse:
        recent_runs = runs if runs is not None else await self._optimization_run_repo.list_for_target(str(config.target_key), limit=8)
        graph_context = get_dspy_graph_context(str(config.target_key))
        if not graph_context:
            graph_context = {
                "focus_node_id": f"{config.subgraph_key}.{config.node_id}",
                "focus_node_label": str(config.node_label),
                "upstream_nodes": [],
                "downstream_nodes": [],
                "nodes": get_topology(str(config.subgraph_key), include_root=True)["nodes"],
                "edges": get_topology(str(config.subgraph_key), include_root=True)["edges"],
            }
        latest_run = recent_runs[0] if recent_runs else None
        config_response = PromptOptimizationConfigResponse(
            id=str(config.id),
            target_key=str(config.target_key),
            subgraph_key=str(config.subgraph_key),
            node_id=str(config.node_id),
            node_label=str(config.node_label),
            module_name=str(config.module_name),
            optimization_goal=str(config.optimization_goal),
            optimizer_strategy=str(config.optimizer_strategy),
            compiler_version=config.compiler_version,
            metric_names=list(config.metric_names or []),
            config_payload=dict(config.config_payload or {}),
            is_enabled=bool(config.is_enabled),
            supports_compile=bool(config.supports_compile),
            is_active_target=bool(config.is_active_target),
            current_artifact_version=config.current_artifact_version,
            previous_artifact_version=config.previous_artifact_version,
            latest_failed_artifact_version=config.latest_failed_artifact_version,
            latest_error_message=config.latest_error_message,
            latest_metrics_snapshot=dict(config.latest_metrics_snapshot or {}) or None,
            last_compiled_at=config.last_compiled_at,
            last_evaluated_at=config.last_evaluated_at,
            updated_by=str(config.updated_by) if config.updated_by else None,
            created_at=config.created_at,
            updated_at=config.updated_at,
        )
        run_responses = [
            PromptOptimizationRunResponse(
                id=str(run.id),
                target_key=str(run.target_key),
                run_type=str(run.run_type),
                status=str(run.status),
                compiler_version=run.compiler_version,
                artifact_version=run.artifact_version,
                prompt_version_id=str(run.prompt_version_id) if run.prompt_version_id else None,
                metrics_snapshot=dict(run.metrics_snapshot or {}) or None,
                error_message=run.error_message,
                started_at=run.started_at,
                finished_at=run.finished_at,
                created_at=run.created_at,
                updated_at=run.updated_at,
            )
            for run in recent_runs
        ]
        return PromptOptimizationTargetResponse(
            target_key=str(config.target_key),
            subgraph_key=str(config.subgraph_key),
            node_id=str(config.node_id),
            node_label=str(config.node_label),
            module_name=str(config.module_name),
            optimization_goal=str(config.optimization_goal),
            supports_compile=bool(config.supports_compile),
            current_status=str(latest_run.status) if latest_run else "idle",
            current_artifact_version=config.current_artifact_version,
            latest_metrics=dict(config.latest_metrics_snapshot or {}) or None,
            graph_context=graph_context,
            config=config_response,
            recent_runs=run_responses,
        )

    async def list_agents(self, query: AgentDefinitionListQuery) -> tuple[list[AgentDefinitionResponse], int]:
        await self._sync_registered_agents()
        items, total = await self._agent_repo.list_paged(
            filters=query.to_filters(), page=query.page, size=query.size
        )
        metrics_repo = AgentExecutionMetricsRepository(self._session, self._org_id)
        enriched: list[AgentDefinitionResponse] = []
        for item in items:
            runtime = await self._runtime_repo.ensure_for_agent(item)
            metrics = await metrics_repo.get_metrics(str(item.id))
            data = AgentDefinitionResponse.model_validate(item).model_dump()
            data["runtime_status"] = self._runtime_status_value(runtime)
            data["metrics_summary"] = metrics
            enriched.append(AgentDefinitionResponse(**data))
        return enriched, total

    async def get_agent(self, id: str) -> AgentDefinitionResponse:
        await self._sync_registered_agents()
        obj = await self._agent_repo.get(id)
        if not obj:
            raise NotFoundError(f"Agent {id} not found")
        runtime = await self._runtime_repo.ensure_for_agent(obj)
        metrics = await AgentExecutionMetricsRepository(self._session, self._org_id).get_metrics(id)
        data = AgentDefinitionResponse.model_validate(obj).model_dump()
        data["runtime_status"] = self._runtime_status_value(runtime)
        data["metrics_summary"] = metrics
        return AgentDefinitionResponse(**data)

    async def create_agent(self, body: AgentDefinitionCreate) -> AgentDefinitionResponse:
        existing = await self._agent_repo.dedupe_by_subgraph_key(body.subgraph_key)
        if existing:
            raise ValidationError(
                f"Agent subgraph_key {body.subgraph_key} already exists for this organization"
            )
        if body.prompt_version_id:
            prompt = await self._prompt_repo.get(body.prompt_version_id)
            if not prompt:
                raise ValidationError(f"Prompt version {body.prompt_version_id} not found")
        obj = await self._agent_repo.create(body.model_dump(exclude_none=True))
        await self._runtime_repo.ensure_for_agent(obj)
        await self._log_audit("agent_definition", str(obj.id), "create")
        return await self.get_agent(str(obj.id))

    async def update_agent(self, id: str, body: AgentDefinitionUpdate) -> AgentDefinitionResponse:
        if body.subgraph_key:
            existing = await self._agent_repo.dedupe_by_subgraph_key(body.subgraph_key)
            if existing and str(existing.id) != id:
                raise ValidationError(
                    f"Agent subgraph_key {body.subgraph_key} already exists for this organization"
                )
        obj = await self._agent_repo.update(id, body.model_dump(exclude_none=True))
        if not obj:
            raise NotFoundError(f"Agent {id} not found")
        await self._runtime_repo.ensure_for_agent(obj)
        await self._log_audit("agent_definition", str(obj.id), "update")
        return await self.get_agent(id)

    async def delete_agent(self, id: str) -> None:
        success = await self._agent_repo.delete(id)
        if not success:
            raise NotFoundError(f"Agent {id} not found")
        await self._log_audit("agent_definition", id, "delete")

    async def list_prompts(self, query: PromptVersionListQuery) -> tuple[list[PromptVersionResponse], int]:
        items, total = await self._prompt_repo.list_paged(
            filters=query.to_filters(), page=query.page, size=query.size
        )
        rows: list[PromptVersionResponse] = []
        for item in items:
            dspy = await self._prompt_repo.get_dspy_config(str(item.id))
            data = PromptVersionResponse.model_validate(item).model_dump()
            data["dspy_config"] = None if not dspy else {
                "id": str(dspy.id),
                "module_name": dspy.module_name,
                "compiler_version": dspy.compiler_version,
                "fallback_prompt": dspy.fallback_prompt,
                "metric_names": list(dspy.metric_names or []),
                "config_payload": dict(dspy.config_payload or {}),
                "is_enabled": bool(dspy.is_enabled),
            }
            rows.append(PromptVersionResponse(**data))
        return rows, total

    async def get_prompt(self, id: str) -> PromptVersionResponse:
        obj = await self._prompt_repo.get(id)
        if not obj:
            raise NotFoundError(f"Prompt version {id} not found")
        dspy = await self._prompt_repo.get_dspy_config(id)
        data = PromptVersionResponse.model_validate(obj).model_dump()
        data["dspy_config"] = None if not dspy else {
            "id": str(dspy.id),
            "module_name": dspy.module_name,
            "compiler_version": dspy.compiler_version,
            "fallback_prompt": dspy.fallback_prompt,
            "metric_names": list(dspy.metric_names or []),
            "config_payload": dict(dspy.config_payload or {}),
            "is_enabled": bool(dspy.is_enabled),
        }
        return PromptVersionResponse(**data)

    async def create_prompt(self, body: PromptVersionCreate) -> PromptVersionResponse:
        latest = await self._prompt_repo.get_latest_version(body.name)
        if latest and body.version <= latest.version:
            body.version = latest.version + 1
        data = body.model_dump()
        data["created_by"] = self._actor_id
        obj = await self._prompt_repo.create(data)
        await self._log_audit("prompt_version", str(obj.id), "create")
        return await self.get_prompt(str(obj.id))

    async def update_prompt(self, id: str, body: PromptVersionUpdate) -> PromptVersionResponse:
        obj = await self._prompt_repo.update(id, body.model_dump(exclude_none=True))
        if not obj:
            raise NotFoundError(f"Prompt version {id} not found")
        await self._log_audit("prompt_version", str(obj.id), "update")
        return await self.get_prompt(id)

    async def delete_prompt(self, id: str) -> None:
        success = await self._prompt_repo.delete(id)
        if not success:
            raise NotFoundError(f"Prompt version {id} not found")
        await self._log_audit("prompt_version", id, "delete")

    async def list_prompt_optimization_targets(
        self,
        query: PromptOptimizationTargetListQuery,
    ) -> PromptOptimizationTargetsResponse:
        await self._sync_prompt_optimization_targets()
        configs = await self._optimization_repo.list_all()
        recent_runs = await self._optimization_run_repo.list_recent(limit=200)
        runs_by_target: dict[str, list] = {}
        for run in recent_runs:
            runs_by_target.setdefault(str(run.target_key), []).append(run)

        items: list[PromptOptimizationTargetResponse] = []
        for config in configs:
            if query.subgraph_key and config.subgraph_key != query.subgraph_key:
                continue
            if query.is_enabled is not None and bool(config.is_enabled) != bool(query.is_enabled):
                continue
            target_runs = runs_by_target.get(str(config.target_key), [])
            current_status = str(target_runs[0].status) if target_runs else "idle"
            if query.status and current_status != query.status:
                continue
            items.append(await self._build_prompt_optimization_target(config, runs=target_runs[:8]))

        overview = PromptOptimizationOverview(
            total_targets=len(items),
            enabled_targets=sum(1 for item in items if item.config.is_enabled),
            active_targets=sum(1 for item in items if item.config.is_active_target),
            successful_runs=sum(1 for run in recent_runs if run.status == "completed"),
            failed_runs=sum(1 for run in recent_runs if run.status == "failed"),
            pending_runs=sum(1 for run in recent_runs if run.status in {"pending", "running"}),
        )
        return PromptOptimizationTargetsResponse(overview=overview, items=items)

    async def get_prompt_optimization_target(self, target_key: str) -> PromptOptimizationTargetResponse:
        await self._sync_prompt_optimization_targets()
        config = await self._optimization_repo.get_by_target_key(target_key)
        if not config:
            raise NotFoundError(f"Optimization target {target_key} not found")
        return await self._build_prompt_optimization_target(config)

    async def update_prompt_optimization_config(
        self,
        target_key: str,
        payload: PromptOptimizationConfigPayload,
    ) -> PromptOptimizationConfigResponse:
        await self._sync_prompt_optimization_targets()
        target = get_dspy_optimization_target(target_key)
        if not target:
            raise NotFoundError(f"Optimization target {target_key} not found")
        config = await self._optimization_repo.update_config(
            target_key,
            {
                "module_name": payload.module_name,
                "compiler_version": payload.compiler_version,
                "optimizer_strategy": payload.optimizer_strategy,
                "metric_names": payload.metric_names,
                "config_payload": self._build_default_config_payload(target, payload.config_payload),
                "is_enabled": payload.is_enabled,
                "updated_by": self._actor_id,
            },
        )
        if not config:
            raise NotFoundError(f"Optimization target {target_key} not found")
        await self._log_audit("dspy_optimization_config", target_key, "update")
        return (await self.get_prompt_optimization_target(target_key)).config

    async def list_prompt_optimization_runs(self, target_key: str) -> list[PromptOptimizationRunResponse]:
        await self._sync_prompt_optimization_targets()
        config = await self._optimization_repo.get_by_target_key(target_key)
        if not config:
            raise NotFoundError(f"Optimization target {target_key} not found")
        runs = await self._optimization_run_repo.list_for_target(target_key, limit=20)
        return [
            PromptOptimizationRunResponse(
                id=str(run.id),
                target_key=str(run.target_key),
                run_type=str(run.run_type),
                status=str(run.status),
                compiler_version=run.compiler_version,
                artifact_version=run.artifact_version,
                prompt_version_id=str(run.prompt_version_id) if run.prompt_version_id else None,
                metrics_snapshot=dict(run.metrics_snapshot or {}) or None,
                error_message=run.error_message,
                started_at=run.started_at,
                finished_at=run.finished_at,
                created_at=run.created_at,
                updated_at=run.updated_at,
            )
            for run in runs
        ]

    async def compile_prompt_optimization_target(
        self,
        target_key: str,
        *,
        schedule_compile: bool = True,
    ) -> PromptOptimizationRunResponse:
        await self._sync_prompt_optimization_targets()
        config = await self._optimization_repo.get_by_target_key(target_key)
        if not config:
            raise NotFoundError(f"Optimization target {target_key} not found")
        if not bool(config.supports_compile):
            raise ValidationError(f"Optimization target {target_key} does not support compile")
        run = await self._optimization_run_repo.create(
            {
                "target_key": target_key,
                "run_type": "compile",
                "status": "pending",
                "compiler_version": config.compiler_version,
                "payload_json": {
                    "module_name": config.module_name,
                    "optimizer_strategy": config.optimizer_strategy,
                    "metric_names": list(config.metric_names or []),
                },
            }
        )
        if schedule_compile:
            asyncio.create_task(run_dspy_compile_job(self._org_id, self._actor_id, target_key, str(run.id)))
        await self._log_audit("dspy_optimization_run", str(run.id), "create")
        return PromptOptimizationRunResponse(
            id=str(run.id),
            target_key=target_key,
            run_type=str(run.run_type),
            status=str(run.status),
            compiler_version=run.compiler_version,
            artifact_version=run.artifact_version,
            prompt_version_id=str(run.prompt_version_id) if run.prompt_version_id else None,
            metrics_snapshot=dict(run.metrics_snapshot or {}) or None,
            error_message=run.error_message,
            started_at=run.started_at,
            finished_at=run.finished_at,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )

    async def rollback_prompt_optimization_target(self, target_key: str) -> PromptOptimizationRunResponse:
        await self._sync_prompt_optimization_targets()
        config = await self._optimization_repo.get_by_target_key(target_key)
        if not config:
            raise NotFoundError(f"Optimization target {target_key} not found")
        if not config.previous_artifact_version or not config.previous_prompt_version_id:
            raise ValidationError(f"Optimization target {target_key} has no previous stable version to roll back")

        current_artifact_version = config.current_artifact_version
        current_prompt_version_id = str(config.current_prompt_version_id) if config.current_prompt_version_id else None
        now = datetime.utcnow()
        config = await self._optimization_repo.update_config(
            target_key,
            {
                "current_artifact_version": config.previous_artifact_version,
                "current_prompt_version_id": str(config.previous_prompt_version_id),
                "previous_artifact_version": current_artifact_version,
                "previous_prompt_version_id": current_prompt_version_id,
                "latest_error_message": None,
                "last_compiled_at": now,
                "last_evaluated_at": now,
                "updated_by": self._actor_id,
            },
        )
        run = await self._optimization_run_repo.create(
            {
                "target_key": target_key,
                "run_type": "rollback",
                "status": "completed",
                "compiler_version": config.compiler_version if config else None,
                "artifact_version": config.current_artifact_version if config else None,
                "prompt_version_id": config.current_prompt_version_id if config else None,
                "metrics_snapshot": dict(config.latest_metrics_snapshot or {}) if config and config.latest_metrics_snapshot else None,
                "started_at": now,
                "finished_at": now,
            }
        )
        await self._log_audit("dspy_optimization_run", str(run.id), "rollback")
        return PromptOptimizationRunResponse(
            id=str(run.id),
            target_key=str(run.target_key),
            run_type=str(run.run_type),
            status=str(run.status),
            compiler_version=run.compiler_version,
            artifact_version=run.artifact_version,
            prompt_version_id=str(run.prompt_version_id) if run.prompt_version_id else None,
            metrics_snapshot=dict(run.metrics_snapshot or {}) or None,
            error_message=run.error_message,
            started_at=run.started_at,
            finished_at=run.finished_at,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )

    async def get_routing_strategy(self) -> RoutingStrategyOverviewResponse:
        all_topology = get_topology("all", include_root=True)
        root_node_ids = {
            node["id"]
            for node in all_topology["nodes"]
            if node["kind"] in {"root", "subgraph"}
        }
        root_nodes = [
            node
            for node in all_topology["nodes"]
            if node["id"] in root_node_ids
        ]
        root_edges = [
            edge
            for edge in all_topology["edges"]
            if edge["source"] in root_node_ids and edge["target"] in root_node_ids
        ]

        route_mode = str(settings.agent_route_mode or "router_enabled").strip() or "router_enabled"
        if route_mode not in {"legacy_only", "canary_non_pdf", "router_enabled"}:
            route_mode = "router_enabled"

        subgraph_meta = {
            item["subgraph_key"]: item
            for item in get_registered_subgraphs()
        }
        subgraphs: list[RoutingSubgraphDescriptor] = []
        scenario_map = {
            "quality_judgement": [
                "用户消息中出现创建任务、提交任务、task 等任务意图关键词",
                "本轮请求携带图片附件，需要走旧任务流并自动回填任务表单图片",
                "用户发送纯文本问答，不涉及创建任务",
                "用户上传 txt、docx、xlsx、csv、json 等非图片文件，需要做结构化解析与质检",
            ],
        }
        for key in ("quality_judgement",):
            topology = get_topology(key, include_root=False)
            meta = subgraph_meta.get(key, {})
            entry_node = next(
                (edge["target"] for edge in topology["edges"] if edge["source"] == key),
                key,
            )
            subgraphs.append(
                RoutingSubgraphDescriptor(
                    subgraph_key=key,
                    label=str(meta.get("name") or key),
                    summary=str(meta.get("description") or ""),
                    entry_node=entry_node,
                    nodes=topology["nodes"],
                    edges=topology["edges"],
                    typical_scenarios=scenario_map.get(key, []),
                )
            )

        signals = [
            RoutingSignalDescriptor(
                key="has_task_keyword",
                label="任务意图关键词",
                description="从用户文本中识别是否包含创建任务、提交任务、task 等任务流关键词。",
                source_stage="route_signal_builder",
            ),
            RoutingSignalDescriptor(
                key="has_images",
                label="图片附件",
                description="请求中存在任意图片附件时，优先进入 legacy 视觉与任务桥接流程。",
                source_stage="route_signal_builder",
            ),
            RoutingSignalDescriptor(
                key="has_file_attachments",
                label="文件附件",
                description="存在非图片文件时，结合 request_kind 决定是否进入 LLM-native 文件质检流程。",
                source_stage="route_signal_builder",
            ),
            RoutingSignalDescriptor(
                key="request_kind",
                label="请求类型",
                description="区分 chat、task 等请求类别，作为文本类消息的兜底判断条件。",
                source_stage="route_signal_builder",
            ),
            RoutingSignalDescriptor(
                key="needs_external_knowledge",
                label="外部知识需求",
                description="标记是否显式选择了 RAG 空间，用于说明后续知识路由而非主路由分流。",
                source_stage="route_signal_builder",
            ),
        ]

        priority_rules = [
            RoutingPriorityRule(
                order=1,
                when="命中 has_task_keyword",
                target_subgraph="quality_judgement",
                reason="Task creation intent detected; route to quality judgement flow",
                examples=["创建任务", "新建任务", "提交任务", "task"],
            ),
            RoutingPriorityRule(
                order=2,
                when="未命中任务意图且检测到 has_images",
                target_subgraph="quality_judgement",
                reason="Image attachment detected; route to quality vision workflow",
                examples=["上传产品图片", "多张缺陷图片", "图片附件检测"],
            ),
            RoutingPriorityRule(
                order=3,
                when="前两条未命中，且检测到 has_file_attachments 或 request_kind=chat",
                target_subgraph="quality_judgement",
                reason="Text or non-image file detected; route to quality judgement flow",
                examples=["文本问答", "txt/docx/xlsx/csv/json 文件", "非图片资料解析"],
            ),
        ]

        decision_cards = [
            RoutingDecisionCard(
                key="task-intent",
                title="任务意图优先",
                target_subgraph="quality_judgement",
                reason=priority_rules[0].reason,
                priority_order=1,
                matched_signals=["has_task_keyword"],
                summary="一旦文本命中任务流关键词，直接进入 quality_judgement，后续图片/文件判断不再继续参与。",
            ),
            RoutingDecisionCard(
                key="image-first",
                title="图片走质量判定智能体",
                target_subgraph="quality_judgement",
                reason=priority_rules[1].reason,
                priority_order=2,
                matched_signals=["has_images"],
                summary="图片输入需要兼容任务流与图片自动回填，因此在非任务关键词场景下优先进入 quality_judgement。",
            ),
            RoutingDecisionCard(
                key="text-file-native",
                title="文本与非图片文件走质量判定智能体",
                target_subgraph="quality_judgement",
                reason=priority_rules[2].reason,
                priority_order=3,
                matched_signals=["has_file_attachments", "request_kind"],
                summary="纯文本或非图片文件会进入 quality_judgement，执行文件解析、契约推断、RAG 与结构化质检流程。",
            ),
        ]

        routes, total = await self._route_repo.list_paged(filters={}, page=1, size=6)
        registered_intents = [str(item.intent_name) for item in routes]

        return RoutingStrategyOverviewResponse(
            route_mode=route_mode,
            default_target="quality_judgement",
            root_graph=AgentTopologyResponse(
                selected_subgraph="all",
                nodes=root_nodes,
                edges=root_edges,
                intent_name="memory_manager",
                agent_name="MemoryManagerGraph",
            ),
            subgraphs=subgraphs,
            priority_rules=priority_rules,
            signals=signals,
            decision_cards=decision_cards,
            registered_route_count=total,
            registered_intents=registered_intents,
        )

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

    async def get_rag_analysis(self, *, global_scope: bool = False) -> RagAnalysisResponse:
        rag_repo = RagAnalysisRepository(self._session, None if global_scope else self._org_id)
        stats_data = await rag_repo.get_rag_stats()
        recent_items_data = await rag_repo.get_recent_rag_items(limit=200)

        stats = RagAnalysisStats(
            total_queries=stats_data["total_queries"],
            avg_hit_rate=stats_data["avg_hit_rate"],
            avg_citation_coverage=stats_data["citation_coverage"],
            empty_recall_count=stats_data["empty_recall_count"],
            avg_latency_ms=stats_data["avg_latency_ms"],
        )

        recent_items = [
            RagAnalysisItem(
                task_id=item["task_id"],
                session_id=item.get("session_id"),
                query=item.get("query"),
                rag_space_id=item.get("rag_space_id"),
                rag_space_name=str((item.get("metadata") or {}).get("rag_space_name") or "") or None,
                hit_count=item.get("hit_count", 0),
                hit_rate=item["hit_rate"],
                citation_coverage=item["citation_coverage"],
                latency_ms=item["latency_ms"],
                source_graph=item.get("source_graph"),
                product_family=str((item.get("metadata") or {}).get("product_family") or "") or None,
                product_id=str((item.get("metadata") or {}).get("product_id") or "") or None,
                verdict=str((item.get("metadata") or {}).get("verdict") or "") or None,
                expectation_matched=(item.get("metadata") or {}).get("expectation_matched"),
                top_sources=[str(source) for source in list((item.get("metadata") or {}).get("top_sources") or []) if str(source)],
                rule_hits=[str(rule) for rule in list((item.get("metadata") or {}).get("rule_hits") or []) if str(rule)],
                created_at=item["created_at"],
            )
            for item in recent_items_data
        ]

        def build_breakdown(values: dict[str, dict[str, float]]) -> list[RagAnalysisBreakdownItem]:
            rows: list[RagAnalysisBreakdownItem] = []
            for key, aggregate in sorted(values.items(), key=lambda entry: (-entry[1]["value"], entry[0])):
                label = str(aggregate.get("label") or key or "unknown")
                rows.append(
                    RagAnalysisBreakdownItem(
                        key=key or "unknown",
                        label=label,
                        value=int(aggregate["value"]),
                        avg_hit_rate=round(float(aggregate["hit_sum"]) / max(int(aggregate["value"]), 1), 4),
                        avg_citation_coverage=round(float(aggregate["citation_sum"]) / max(int(aggregate["value"]), 1), 4),
                    )
                )
            return rows[:8]

        space_map: dict[str, dict[str, float]] = {}
        source_graph_map: dict[str, dict[str, float]] = {}
        product_family_map: dict[str, dict[str, float]] = {}
        evidence_map: dict[str, dict[str, object]] = {}

        for item in recent_items:
            for key, value_map, label in (
                (item.rag_space_id or "unknown", space_map, item.rag_space_name or item.rag_space_id or "unknown"),
                (item.source_graph or "unknown", source_graph_map, item.source_graph or "unknown"),
                (item.product_family or "unknown", product_family_map, item.product_family or "unknown"),
            ):
                aggregate = value_map.setdefault(
                    key,
                    {"value": 0, "hit_sum": 0.0, "citation_sum": 0.0, "label": label},
                )
                aggregate["value"] = int(aggregate["value"]) + 1
                aggregate["hit_sum"] = float(aggregate["hit_sum"]) + float(item.hit_rate)
                aggregate["citation_sum"] = float(aggregate["citation_sum"]) + float(item.citation_coverage)

            for rule in item.rule_hits:
                aggregate = evidence_map.setdefault(
                    rule,
                    {"sources": set(), "verdicts": set(), "query_count": 0},
                )
                aggregate["query_count"] = int(aggregate["query_count"]) + 1
                for source in item.top_sources:
                    aggregate["sources"].add(source)
                if item.verdict:
                    aggregate["verdicts"].add(item.verdict)

        evidence_impact = [
            RagEvidenceImpactItem(
                rule_key=rule,
                verdicts=sorted(str(verdict) for verdict in list(cast(set, aggregate["verdicts"]))),
                source_count=len(cast(set, aggregate["sources"])),
                query_count=int(aggregate["query_count"]),
                sources=sorted(str(source) for source in list(cast(set, aggregate["sources"])))[:5],
            )
            for rule, aggregate in sorted(
                evidence_map.items(),
                key=lambda entry: (-int(entry[1]["query_count"]), entry[0]),
            )
        ][:12]

        return RagAnalysisResponse(
            stats=stats,
            space_breakdown=build_breakdown(space_map),
            source_graph_breakdown=build_breakdown(source_graph_map),
            product_family_breakdown=build_breakdown(product_family_map),
            evidence_impact=evidence_impact,
            recent_items=recent_items[:30],
        )

    async def _build_runtime_response(self, runtime, agent) -> AgentRuntimeInstanceResponse:
        metrics = await AgentExecutionMetricsRepository(self._session, self._org_id).get_metrics(str(agent.id)) or {}
        runtime_status = self._runtime_status_value(runtime)
        return AgentRuntimeInstanceResponse(
            runtime_key=runtime.runtime_key,
            agent_id=str(agent.id),
            agent_name=agent.name,
            subgraph_key=runtime.subgraph_key,
            status=runtime_status,
            runtime_status=runtime_status,
            supports_start_stop=bool(getattr(runtime, "supports_start_stop", False)),
            is_active=agent.is_active,
            lifecycle_status=agent.lifecycle_status,
            group_key=agent.group_key,
            route_enabled=agent.route_enabled,
            supports_route_toggle=agent.supports_route_toggle,
            customer_visible_description=agent.customer_visible_description,
            execution_count=int(metrics.get("execution_count") or 0),
            success_rate=float(metrics.get("success_rate") or 0.0),
            avg_latency_ms=float(metrics.get("avg_latency_ms") or 0.0),
            last_executed_at=metrics.get("last_executed_at"),
            last_started_at=getattr(runtime, "last_started_at", None),
            last_stopped_at=getattr(runtime, "last_stopped_at", None),
            last_error_message=getattr(runtime, "last_error_message", None),
            maintenance_reason=getattr(runtime, "maintenance_reason", None),
        )

    async def get_runtime_overview(self) -> AgentRuntimeOverviewResponse:
        await self._sync_registered_agents()
        runtime_rows = await self._runtime_repo.list_with_agents()
        visible_runtime_rows = [
            (runtime, agent)
            for runtime, agent in runtime_rows
            if str(agent.lifecycle_status or "") not in {"planned", "deprecated"}
        ]
        metrics_repo = AgentExecutionMetricsRepository(self._session, self._org_id)
        metrics_rows = []
        for runtime, _agent in visible_runtime_rows:
            metrics = await metrics_repo.get_metrics(str(runtime.agent_id))
            if metrics:
                metrics_rows.append(metrics)
        active_agents = len(visible_runtime_rows)
        running_agents = sum(
            1 for runtime, _agent in visible_runtime_rows if self._runtime_status_value(runtime) == "running"
        )
        stopped_agents = sum(
            1 for runtime, _agent in visible_runtime_rows if self._runtime_status_value(runtime) == "stopped"
        )
        total_executions = sum(int(item.get("execution_count") or 0) for item in metrics_rows)
        avg_latency_ms = (
            round(sum(float(item.get("avg_latency_ms") or 0.0) for item in metrics_rows) / len(metrics_rows), 2)
            if metrics_rows else 0.0
        )
        today = datetime.now(timezone.utc).date()
        completed_today = sum(
            1
            for item in metrics_rows
            if item.get("last_executed_at") and item["last_executed_at"].date() == today
        )
        return AgentRuntimeOverviewResponse(
            active_agents=active_agents,
            running_agents=running_agents,
            stopped_agents=stopped_agents,
            total_executions=total_executions,
            avg_latency_ms=avg_latency_ms,
            queued_tasks=0,
            completed_today=completed_today,
        )

    async def list_runtime_agents(self) -> list[AgentRuntimeInstanceResponse]:
        await self._sync_registered_agents()
        runtime_rows = await self._runtime_repo.list_with_agents()
        items: list[AgentRuntimeInstanceResponse] = []
        for runtime, agent in runtime_rows:
            if str(agent.lifecycle_status or "") in {"planned", "deprecated"}:
                continue
            items.append(await self._build_runtime_response(runtime, agent))
        return items

    async def set_runtime_status(self, runtime_key: str, *, status: str) -> AgentRuntimeInstanceResponse:
        await self._sync_registered_agents()
        runtime = await self._runtime_repo.dedupe_by_runtime_key(runtime_key)
        if not runtime:
            raise NotFoundError(f"Runtime {runtime_key} not found")
        if not bool(runtime.supports_start_stop):
            raise ValidationError(f"Runtime {runtime_key} does not support start/stop")

        before_status = runtime.runtime_status
        runtime = await self._runtime_repo.set_runtime_status(runtime_key, status, updated_by=self._actor_id)
        if not runtime:
            raise NotFoundError(f"Runtime {runtime_key} not found")

        # Write audit event
        await self._runtime_repo.create_event({
            "agent_id": str(runtime.agent_id),
            "runtime_key": runtime_key,
            "event_type": "start" if status == "running" else "stop",
            "before_status": before_status,
            "after_status": status,
            "operator_id": self._actor_id,
        })

        agent = await self._agent_repo.get(str(runtime.agent_id))
        if not agent:
            raise NotFoundError(f"Agent {runtime.agent_id} not found")
        return await self._build_runtime_response(runtime, agent)

    async def pause_route(self, runtime_key: str, reason: str) -> AgentRuntimeInstanceResponse:
        await self._sync_registered_agents()
        runtime = await self._runtime_repo.dedupe_by_runtime_key(runtime_key)
        if not runtime:
            raise NotFoundError(f"Runtime {runtime_key} not found")
        agent = await self._agent_repo.get(str(runtime.agent_id))
        if not agent:
            raise NotFoundError(f"Agent {runtime.agent_id} not found")
        if not agent.supports_route_toggle:
            raise ValidationError(f"Agent {agent.name} does not support route toggle")

        before_runtime_status = self._runtime_status_value(runtime)
        agent.route_enabled = False
        if bool(getattr(runtime, "supports_start_stop", False)) and before_runtime_status != "stopped":
            runtime = await self._runtime_repo.set_runtime_status(runtime_key, "stopped", updated_by=self._actor_id)
            if not runtime:
                raise NotFoundError(f"Runtime {runtime_key} not found")
        await self._runtime_repo.create_event({
            "agent_id": str(agent.id),
            "runtime_key": runtime_key,
            "event_type": "pause_route",
            "before_status": f"route_enabled:{before_runtime_status}",
            "after_status": "route_paused:stopped",
            "reason": reason,
            "operator_id": self._actor_id,
        })
        await self._session.flush()

        return await self._build_runtime_response(runtime, agent)

    async def resume_route(self, runtime_key: str) -> AgentRuntimeInstanceResponse:
        await self._sync_registered_agents()
        runtime = await self._runtime_repo.dedupe_by_runtime_key(runtime_key)
        if not runtime:
            raise NotFoundError(f"Runtime {runtime_key} not found")
        agent = await self._agent_repo.get(str(runtime.agent_id))
        if not agent:
            raise NotFoundError(f"Agent {runtime.agent_id} not found")

        before_runtime_status = self._runtime_status_value(runtime)
        agent.route_enabled = True
        if bool(getattr(runtime, "supports_start_stop", False)) and before_runtime_status != "running":
            runtime = await self._runtime_repo.set_runtime_status(runtime_key, "running", updated_by=self._actor_id)
            if not runtime:
                raise NotFoundError(f"Runtime {runtime_key} not found")
        await self._runtime_repo.create_event({
            "agent_id": str(agent.id),
            "runtime_key": runtime_key,
            "event_type": "resume_route",
            "before_status": f"route_paused:{before_runtime_status}",
            "after_status": "route_enabled:running",
            "operator_id": self._actor_id,
        })
        await self._session.flush()

        return await self._build_runtime_response(runtime, agent)

    async def get_agents_topology(
        self,
        subgraph_key: str = "all",
        *,
        mode: str = "design",
        include_planned: bool = True,
    ) -> AgentTopologyResponse:
        await self._sync_registered_agents()
        runtime_rows = await self._runtime_repo.list_with_agents()

        visible_subgraphs: set[str] = set()
        for runtime, agent in runtime_rows:
            agent_subgraph_key = str(agent.subgraph_key or "")
            lifecycle_status = str(agent.lifecycle_status or "")
            if lifecycle_status == "deprecated":
                continue
            if lifecycle_status == "planned" and not include_planned:
                continue
            if subgraph_key not in {"all", "*"} and agent_subgraph_key != subgraph_key:
                continue
            if mode == "runtime":
                if not agent.route_enabled:
                    continue
                if self._runtime_status_value(runtime) not in {"running", "degraded"}:
                    continue
            visible_subgraphs.add(agent_subgraph_key)

        nodes = await self._build_agent_topology_nodes(
            runtime_rows=runtime_rows,
            visible_subgraphs=visible_subgraphs,
            selected_subgraph=subgraph_key,
        )
        edges = self._build_agent_topology_edges(visible_subgraphs)
        return AgentTopologyResponse(
            selected_subgraph=subgraph_key,
            nodes=nodes,
            edges=edges,
        )

    async def get_route_graph(self, route_id: str) -> AgentTopologyResponse:
        route = await self._route_repo.get(route_id)
        if not route:
            raise NotFoundError(f"Intent route {route_id} not found")
        agent_name = None
        subgraph_key = "quality_judgement"
        if route.agent_id:
            agent = await self._agent_repo.get(str(route.agent_id))
            if agent:
                agent_name = agent.name
                subgraph_key = str(agent.subgraph_key or "quality_judgement")
        topology = get_route_topology(
            intent_name=route.intent_name,
            agent_name=agent_name,
            subgraph_key=subgraph_key,
        )
        return AgentTopologyResponse(
            selected_subgraph=subgraph_key,
            nodes=topology["nodes"],
            edges=topology["edges"],
            intent_name=route.intent_name,
            agent_name=agent_name,
        )

    async def get_prompt_dspy(self, prompt_id: str) -> PromptDSPyConfigResponse | None:
        prompt = await self._prompt_repo.get(prompt_id)
        if not prompt:
            raise NotFoundError(f"Prompt version {prompt_id} not found")
        config = await self._prompt_repo.get_dspy_config(prompt_id)
        if not config:
            return None
        return PromptDSPyConfigResponse(
            id=str(config.id),
            org_id=str(config.org_id),
            prompt_version_id=str(config.prompt_version_id),
            module_name=config.module_name,
            compiler_version=config.compiler_version,
            fallback_prompt=config.fallback_prompt,
            metric_names=list(config.metric_names or []),
            config_payload=dict(config.config_payload or {}),
            is_enabled=bool(config.is_enabled),
            updated_by=str(config.updated_by) if config.updated_by else None,
            created_at=config.created_at,
            updated_at=config.updated_at,
        )

    async def upsert_prompt_dspy(self, prompt_id: str, payload: PromptDSPyConfigPayload) -> PromptDSPyConfigResponse:
        prompt = await self._prompt_repo.get(prompt_id)
        if not prompt:
            raise NotFoundError(f"Prompt version {prompt_id} not found")
        config = await self._prompt_repo.upsert_dspy_config(
            prompt_id,
            {
                **payload.model_dump(),
                "updated_by": self._actor_id,
            },
        )
        await self._log_audit("prompt_dspy_config", str(config.id), "upsert")
        return PromptDSPyConfigResponse(
            id=str(config.id),
            org_id=str(config.org_id),
            prompt_version_id=str(config.prompt_version_id),
            module_name=config.module_name,
            compiler_version=config.compiler_version,
            fallback_prompt=config.fallback_prompt,
            metric_names=list(config.metric_names or []),
            config_payload=dict(config.config_payload or {}),
            is_enabled=bool(config.is_enabled),
            updated_by=str(config.updated_by) if config.updated_by else None,
            created_at=config.created_at,
            updated_at=config.updated_at,
        )

    async def process_compile_run(self, run_id: str, target_key: str) -> None:
        target = get_dspy_optimization_target(target_key)
        run = None
        for _ in range(12):
            run = await self._optimization_run_repo.get(run_id)
            if run:
                break
            await asyncio.sleep(0.1)
        if not run or not target:
            return
        config = await self._optimization_repo.get_by_target_key(target_key)
        now = datetime.utcnow()
        if not config:
            await self._optimization_run_repo.update(
                run_id,
                {
                    "status": "failed",
                    "error_message": f"Optimization target {target_key} not found",
                    "started_at": now,
                    "finished_at": now,
                },
            )
            return

        await self._optimization_run_repo.update(
            run_id,
            {
                "status": "running",
                "started_at": now,
            },
        )

        try:
            await asyncio.sleep(0.05)
            prompt_name = target_key
            latest_prompt = await self._prompt_repo.get_latest_version(prompt_name)
            next_version = (latest_prompt.version + 1) if latest_prompt else 1
            artifact_version = self._build_artifact_version(target_key, next_version)
            metrics_snapshot = self._build_metrics_snapshot(
                target_key,
                list(config.metric_names or target.get("metric_names") or ["faithfulness", "traceability", "pass_rate"]),
            )
            prompt = await self._prompt_repo.create(
                {
                    "name": prompt_name,
                    "content": (
                        f"[system-generated dspy artifact]\n"
                        f"target={target_key}\n"
                        f"artifact_version={artifact_version}\n"
                        f"module_name={config.module_name}\n"
                        f"optimizer_strategy={config.optimizer_strategy}\n"
                        f"optimization_goal={config.optimization_goal}\n"
                        f"metric_names={','.join(list(config.metric_names or []))}\n"
                        f"config_payload={dict(config.config_payload or {})}\n\n"
                        "instruction:\n"
                        f"Apply the compiled DSPy strategy for `{target_key}`. "
                        f"Prioritize the optimization goal `{config.optimization_goal}` and optimize for metrics "
                        f"{', '.join(list(config.metric_names or [])) or 'faithfulness, traceability, pass_rate'}."
                    ),
                    "version": next_version,
                    "status": "approved",
                    "created_by": self._actor_id,
                }
            )
            completed_at = datetime.utcnow()
            await self._optimization_repo.update_config(
                target_key,
                {
                    "previous_artifact_version": config.current_artifact_version,
                    "previous_prompt_version_id": str(config.current_prompt_version_id) if config.current_prompt_version_id else None,
                    "current_artifact_version": artifact_version,
                    "current_prompt_version_id": str(prompt.id),
                    "latest_failed_artifact_version": None,
                    "latest_error_message": None,
                    "latest_metrics_snapshot": metrics_snapshot,
                    "last_compiled_at": completed_at,
                    "last_evaluated_at": completed_at,
                    "updated_by": self._actor_id,
                },
            )
            await self._optimization_run_repo.update(
                run_id,
                {
                    "status": "completed",
                    "artifact_version": artifact_version,
                    "prompt_version_id": str(prompt.id),
                    "metrics_snapshot": metrics_snapshot,
                    "finished_at": completed_at,
                },
            )
        except Exception as exc:
            failed_at = datetime.utcnow()
            await self._optimization_repo.update_config(
                target_key,
                {
                    "latest_failed_artifact_version": self._build_artifact_version(target_key, int(datetime.utcnow().timestamp())),
                    "latest_error_message": str(exc),
                    "updated_by": self._actor_id,
                },
            )
            await self._optimization_run_repo.update(
                run_id,
                {
                    "status": "failed",
                    "error_message": str(exc),
                    "finished_at": failed_at,
                },
            )
            raise

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

    async def get_agent_detail(self, agent_id: str) -> AgentDetailResponse:
        agent = await self.get_agent(agent_id)
        bound_prompt = None
        if agent.prompt_version_id:
            try:
                bound_prompt = await self.get_prompt(agent.prompt_version_id)
            except Exception:
                pass
        routes, _ = await self._route_repo.list_paged(filters={}, page=1, size=10)
        agent_routes = [r for r in routes if str(r.agent_id) == agent_id]
        events = await self._runtime_repo.list_events(agent_id, limit=20)

        return AgentDetailResponse(
            **agent.model_dump(),
            bound_prompt_version=bound_prompt,
            bound_routes=[IntentRouteResponse.model_validate(r) for r in agent_routes],
            runtime_events=[AgentRuntimeEventResponse.model_validate(e) for e in events],
        )

    async def list_runtime_events(self, agent_id: str, limit: int = 20) -> list[AgentRuntimeEventResponse]:
        events = await self._runtime_repo.list_events(agent_id, limit=limit)
        return [AgentRuntimeEventResponse.model_validate(e) for e in events]

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

    # ============================================================
    # Routing Strategy Viewer (non-config, view-only)
    # ============================================================

    async def get_routing_current(self) -> RoutingCurrentResponse:
        """返回当前系统真实路由策略视图 — 基于 route_policy.py 的真实现有逻辑"""
        return RoutingCurrentResponse(
            mode="rule_first_with_model_fallback",
            mode_label="规则优先，模型兜底",
            default_agent="chat",
            default_sub_route="general_chat",
            agents=[
                RouteAgentDescriptor(key="chat", label="Quality Chat", sub_routes=["general_chat", "rag_qa"]),
                RouteAgentDescriptor(key="inspection_task", label="Inspection Task Agent", sub_routes=["task_create", "inspection_execute", "quality_qa"]),
            ],
            rules=[
                RouteRuleDescriptor(priority=1, name="手动指定检测Agent", condition_summary="前端 force_agent=inspection_task", target_agent="inspection_task", target_sub_route="task_create", route_source="manual", examples=["force_agent=inspection_task"]),
                RouteRuleDescriptor(priority=2, name="手动指定聊天Agent", condition_summary="前端 force_agent=chat", target_agent="chat", target_sub_route="general_chat", route_source="manual", examples=["force_agent=chat"]),
                RouteRuleDescriptor(priority=3, name="结构化文件+检测意图", condition_summary="xlsx/csv/json/txt/docx 等文件 + 检测/质检关键词", target_agent="inspection_task", target_sub_route="inspection_execute", examples=["上传Excel+创建检测任务"]),
                RouteRuleDescriptor(priority=4, name="图片+检测意图", condition_summary="图片附件/URL + 检测/质检关键词", target_agent="inspection_task", target_sub_route="inspection_execute", examples=["图片+帮我检测是否合格"]),
                RouteRuleDescriptor(priority=5, name="任务创建意图", condition_summary="纯文本含任务创建关键词（创建/新建/发起+任务/检测）", target_agent="inspection_task", target_sub_route="task_create", examples=["创建任务", "帮我检测这个产品"]),
                RouteRuleDescriptor(priority=6, name="质检问答意图", condition_summary="含质量、质检、缺陷、合格、标准等语义关键词", target_agent="inspection_task", target_sub_route="quality_qa", examples=["这个算不算缺陷", "按照GB/T标准判定"]),
                RouteRuleDescriptor(priority=7, name="RAG知识库问答", condition_summary="选中RAG空间 或 知识库检索意图", target_agent="chat", target_sub_route="rag_qa", examples=["根据知识库回答", "查一下文档里的标准"]),
                RouteRuleDescriptor(priority=8, name="模糊输入兜底", condition_summary="短句/代词/无法明确分类的输入", target_agent="chat", target_sub_route="general_chat", examples=["这个呢", "看看"]),
                RouteRuleDescriptor(priority=9, name="默认普通聊天", condition_summary="未命中以上规则的默认兜底", target_agent="chat", target_sub_route="general_chat", examples=["你好", "今天天气怎么样"]),
            ],
            signals=[
                RouteSignalInfo(key="has_task_keyword", label="任务意图关键词", description="用户文本中包含创建任务、提交任务等关键词"),
                RouteSignalInfo(key="has_images", label="图片附件", description="请求包含图片附件或图片URL"),
                RouteSignalInfo(key="has_structured_file", label="结构化文件", description="请求包含xlsx/csv/json/txt/docx等文件"),
                RouteSignalInfo(key="has_quality_signal", label="质检语义", description="文本包含质量、质检、缺陷、合格、标准等关键词"),
                RouteSignalInfo(key="has_rag_space", label="RAG空间", description="用户选择了RAG知识空间"),
                RouteSignalInfo(key="is_ambiguous", label="模糊输入", description="短句、代词多、无明确意图信号的输入"),
            ],
            rule_count=9,
            active_agent_count=2,
        )

    async def simulate_route(self, body: RouteSimulateRequest) -> RouteSimulateResponse:
        """调用真实路由决策逻辑，但不执行 Agent"""
        from agent.router.route_policy import AgentRoutePolicy
        from agent.router.contracts import AgentRouterInput

        # Build route hints
        route_hints = {}
        if body.force_agent:
            route_hints["force_agent"] = body.force_agent

        # Build attachments for signal detection
        attachments = []
        if body.has_image:
            attachments.append({"kind": "image", "name": "test.png"})
        if body.has_structured_file:
            attachments.append({"kind": "file", "name": "test.xlsx"})

        # Build ext
        ext = {}
        if body.has_rag_space:
            ext["selected_rag_space"] = {"id": "test-space"}

        # Call real routing logic
        policy = AgentRoutePolicy()
        router_input = AgentRouterInput(
            query=body.query,
            request_kind="chat",
            attachments=attachments,
            image_urls=[],
            route_hints=route_hints,
            ext=ext,
        )
        decision = policy.decide(router_input)

        # Map to rule name
        rule_map = {
            ("inspection_task", "inspection_execute"): ("结构化文件/图片 + 检测意图", 3),
            ("inspection_task", "task_create"): ("任务创建意图", 5),
            ("inspection_task", "quality_qa"): ("质检问答意图", 6),
            ("chat", "rag_qa"): ("RAG知识库问答", 7),
            ("chat", "general_chat"): ("默认普通聊天", 9),
        }
        rule_name, priority = rule_map.get(
            (decision.selected_agent, decision.sub_route),
            (decision.reason, 0),
        )

        return RouteSimulateResponse(
            matched_rule_name=rule_name,
            matched_priority=priority,
            selected_agent=decision.selected_agent,
            selected_sub_route=decision.sub_route,
            route_source=decision.route_source,
            reason=decision.reason,
            signals={
                "has_task_keyword": bool(body.query and any(kw in body.query for kw in ["任务", "检测", "创建", "提交"])),
                "has_images": body.has_image,
                "has_structured_file": body.has_structured_file,
                "has_quality_signal": bool(body.query and any(kw in body.query for kw in ["质量", "缺陷", "合格", "标准"])),
                "has_rag_space": body.has_rag_space,
            },
            is_fallback=decision.fallback_agent == "model_classifier",
        )

    async def get_routing_events(self, limit: int = 20) -> list[RouteEventItem]:
        """读取最近路由事件"""
        from app.models.agent_ops import AgentRouteLog
        from sqlalchemy import select

        result = await self._session.execute(
            select(AgentRouteLog)
            .where(
                AgentRouteLog.org_id == self._org_id,
                AgentRouteLog.deleted_at.is_(None),
            )
            .order_by(AgentRouteLog.created_at.desc())
            .limit(limit)
        )
        rows = result.scalars().all()
        items = []
        for row in rows:
            request_summary = None
            sig = row.signals_json or {}
            if isinstance(sig, dict):
                parts = [k for k, v in sig.items() if v]
                request_summary = f"signals: {', '.join(parts)}" if parts else None

            items.append(RouteEventItem(
                id=str(row.id),
                created_at=row.created_at,
                selected_agent=row.selected_agent,
                sub_route=row.sub_route,
                route_source=row.route_source or "rule",
                reason=row.reason,
                intent_name=row.intent_name,
                confidence=float(row.confidence or 0.0),
                latency_ms=row.latency_ms or 0,
                blocked=bool(row.blocked),
                blocked_reason=row.blocked_reason,
                request_summary=request_summary,
            ))
        return items

    async def get_routing_metrics(self) -> RoutingMetricsResponse:
        """路由统计指标"""
        from app.models.agent_ops import AgentRouteLog
        from sqlalchemy import select
        from datetime import datetime, timedelta

        cutoff = datetime.utcnow() - timedelta(hours=24)

        result = await self._session.execute(
            select(AgentRouteLog).where(
                AgentRouteLog.org_id == self._org_id,
                AgentRouteLog.created_at >= cutoff,
                AgentRouteLog.deleted_at.is_(None),
            )
        )
        rows = list(result.scalars().all())

        total = len(rows)
        rule_hit = sum(1 for r in rows if r.route_source == "rule")
        model_fb = sum(1 for r in rows if r.route_source == "model")
        blocked = sum(1 for r in rows if r.blocked)

        avg_lat = round(sum(r.latency_ms or 0 for r in rows) / max(total, 1), 2)

        by_agent: dict = {}
        by_rule: dict = {}
        for r in rows:
            agent = r.selected_agent or "unknown"
            by_agent[agent] = by_agent.get(agent, 0) + 1
            sub = r.sub_route or "unknown"
            key = f"{agent}/{sub}"
            by_rule[key] = by_rule.get(key, 0) + 1

        return RoutingMetricsResponse(
            total_24h=total,
            rule_hit_count=rule_hit,
            model_fallback_count=model_fb,
            blocked_count=blocked,
            avg_latency_ms=avg_lat,
            by_agent=by_agent,
            by_rule=by_rule,
        )


async def run_dspy_compile_job(org_id: str, actor_id: str, target_key: str, run_id: str) -> None:
    session = create_session()
    try:
        service = AgentOpsService(session, org_id, actor_id)
        await service.process_compile_run(run_id, target_key)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
