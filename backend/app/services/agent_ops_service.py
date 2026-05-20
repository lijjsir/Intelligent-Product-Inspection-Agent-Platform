from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from agent.topology_catalog import (
    get_agent_overview_root,
    get_registered_subgraphs,
    get_route_topology,
    get_topology,
)
from app.core.exceptions import NotFoundError, ValidationError
from app.repositories.agent_ops_repo import (
    AgentDefinitionRepository,
    AgentRuntimeRepository,
    IntentRouteRepository,
    PromptVersionRepository,
    RagAnalysisRepository,
)
from app.repositories.agent_management_repo import (
    AgentExecutionMetricsRepository,
    AgentConfigVersionRepository,
    AgentBatchOperationRepository,
)
from app.repositories.rag_space_repo import RagSpaceRepository
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
    RagAnalysisResponse,
    RagAnalysisOption,
    RagAnalysisBreakdownItem,
    RagEvidenceImpactItem,
    RagAnalysisStats,
    RagAnalysisItem,
    RagTraceDetailResponse,
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

    @staticmethod
    def _clean_rag_text(value: object | None) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        if text.lower() in {"unknown", "null", "none", "nan"}:
            return None
        return text

    @classmethod
    def _normalize_rag_sub_route(cls, raw_value: object | None) -> str | None:
        value = cls._clean_rag_text(raw_value)
        if value == "general_qa":
            return "general_chat"
        return value

    @classmethod
    def _derive_rag_source_key(cls, item: dict) -> str | None:
        metadata = dict(item.get("metadata") or {})
        raw_agent = cls._clean_rag_text(item.get("agent_name")) or cls._clean_rag_text(metadata.get("agent"))
        if raw_agent in {"chat", "inspection_task"}:
            return raw_agent
        raw_graph = cls._clean_rag_text(item.get("source_graph")) or cls._clean_rag_text(metadata.get("source_graph"))
        if raw_graph in {"chat", "inspection_task"}:
            return raw_graph
        normalized_sub_route = cls._normalize_rag_sub_route(
            item.get("sub_route") or metadata.get("sub_route") or metadata.get("intent")
        )
        if raw_graph in {"quality_judgement", "llm_native_quality", "legacy_quality"}:
            if normalized_sub_route in {"task_create", "inspection_execute"}:
                return "inspection_task"
            if normalized_sub_route in {"general_chat", "rag_qa", "quality_qa"}:
                return "chat"
            if item.get("task_id"):
                return "inspection_task"
            if item.get("session_id"):
                return "chat"
        return raw_agent or raw_graph

    @classmethod
    def _resolve_rag_source_agent(
        cls,
        item: dict,
        *,
        source_display_map: dict[str, str],
    ) -> tuple[str | None, str | None, str | None]:
        metadata = dict(item.get("metadata") or {})
        normalized_key = cls._derive_rag_source_key(item)
        raw_agent = cls._clean_rag_text(item.get("agent_name")) or cls._clean_rag_text(metadata.get("agent"))
        source_graph = normalized_key or cls._clean_rag_text(item.get("source_graph"))
        source_agent = source_display_map.get(normalized_key or "") if normalized_key else None
        if source_agent is None and raw_agent and raw_agent not in {"chat", "inspection_task", "quality_judgement", "llm_native_quality", "legacy_quality"}:
            source_agent = raw_agent
        if source_agent is None and source_graph:
            source_agent = source_display_map.get(source_graph) or source_graph
        sub_route = cls._normalize_rag_sub_route(
            item.get("sub_route") or metadata.get("sub_route") or metadata.get("intent")
        )
        return source_agent, source_graph, sub_route

    @classmethod
    def _derive_rag_effectiveness(cls, item: dict) -> tuple[bool, bool, bool]:
        metadata = dict(item.get("metadata") or {})
        top_sources = [str(source) for source in list(metadata.get("top_sources") or []) if str(source).strip()]
        retrieved_chunks = [chunk for chunk in list(metadata.get("retrieved_chunks") or []) if isinstance(chunk, dict)]
        used_citations = [citation for citation in list(metadata.get("used_citations") or []) if isinstance(citation, dict)]
        rule_hits = [str(rule) for rule in list(metadata.get("rule_hits") or []) if str(rule).strip()]
        evidence_found = metadata.get("evidence_found")
        if evidence_found is None:
            evidence_found = bool(int(item.get("hit_count") or 0) > 0 or retrieved_chunks or top_sources)
        evidence_used = metadata.get("evidence_used")
        if evidence_used is None:
            evidence_used = bool(used_citations)
        verdict_impacted = metadata.get("verdict_impacted")
        if verdict_impacted is None:
            verdict_impacted = bool(rule_hits)
        return bool(evidence_found), bool(evidence_used), bool(verdict_impacted)

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
        rows = [PromptVersionResponse.model_validate(item) for item in items]
        return rows, total

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

        rag_space_name_map: dict[str, str] = {}
        if not global_scope:
            rag_spaces = await RagSpaceRepository(self._session).list_for_org(
                org_id=self._org_id,
                owner_user_id=None,
                limit=500,
            )
            rag_space_name_map = {
                str(space.id): str(space.name).strip()
                for space in rag_spaces
                if getattr(space, "id", None) and str(getattr(space, "name", "")).strip()
            }

        agent_name_map: dict[str, str] = {}
        try:
            registered_agents = await self._agent_repo.list_all_active()
            agent_name_map = {
                str(item.subgraph_key): str(item.name).strip()
                for item in registered_agents
                if getattr(item, "subgraph_key", None) and str(getattr(item, "name", "")).strip()
            }
        except Exception:
            agent_name_map = {}
        source_display_map = {
            "chat": agent_name_map.get("chat") or "Quality Chat",
            "inspection_task": agent_name_map.get("inspection_task") or "Inspection Task Agent",
            "quality_judgement": agent_name_map.get("quality_judgement") or "Quality Judgement",
        }

        space_options = [
            RagAnalysisOption(key=space_id, label=space_name)
            for space_id, space_name in sorted(rag_space_name_map.items(), key=lambda entry: entry[1])
        ]

        stats = RagAnalysisStats(
            total_queries=stats_data["total_queries"],
            avg_hit_rate=stats_data["avg_hit_rate"],
            avg_citation_coverage=stats_data["citation_coverage"],
            empty_recall_count=stats_data["empty_recall_count"],
            avg_latency_ms=stats_data["avg_latency_ms"],
        )

        def resolve_rag_space(item: dict) -> tuple[str | None, str | None]:
            rag_space_id = self._clean_rag_text(item.get("rag_space_id"))
            metadata = item.get("metadata") or {}
            rag_space_name = (
                rag_space_name_map.get(rag_space_id or "")
                or self._clean_rag_text(metadata.get("rag_space_name"))
            )
            if rag_space_id and rag_space_id not in rag_space_name_map and rag_space_name is None:
                rag_space_id = None
            return rag_space_id, rag_space_name

        recent_items = [
            RagAnalysisItem(
                task_id=item["task_id"],
                session_id=item.get("session_id"),
                query=item.get("query"),
                rag_space_id=resolve_rag_space(item)[0],
                rag_space_name=resolve_rag_space(item)[1],
                hit_count=item.get("hit_count", 0),
                hit_rate=item["hit_rate"],
                citation_coverage=item["citation_coverage"],
                latency_ms=item["latency_ms"],
                source_agent=self._resolve_rag_source_agent(item, source_display_map=source_display_map)[0],
                source_graph=self._resolve_rag_source_agent(item, source_display_map=source_display_map)[1],
                sub_route=self._resolve_rag_source_agent(item, source_display_map=source_display_map)[2],
                trace_id=self._clean_rag_text(item.get("trace_id")),
                top_score=float(item.get("top_score")) if item.get("top_score") is not None else None,
                product_id=str((item.get("metadata") or {}).get("product_id") or "") or None,
                verdict=str((item.get("metadata") or {}).get("verdict") or "") or None,
                expectation_matched=(item.get("metadata") or {}).get("expectation_matched"),
                evidence_found=self._derive_rag_effectiveness(item)[0],
                evidence_used=self._derive_rag_effectiveness(item)[1],
                verdict_impacted=self._derive_rag_effectiveness(item)[2],
                top_sources=[str(source) for source in list((item.get("metadata") or {}).get("top_sources") or []) if str(source)],
                rule_hits=[str(rule) for rule in list((item.get("metadata") or {}).get("rule_hits") or []) if str(rule)],
                created_at=item["created_at"],
            )
            for item in recent_items_data
        ]

        source_agent_option_names = {
            name for name in agent_name_map.values() if name
        } | {
            item.source_agent for item in recent_items if item.source_agent
        }
        source_agent_options = [
            RagAnalysisOption(key=agent_name, label=agent_name)
            for agent_name in sorted(source_agent_option_names)
        ]

        def build_breakdown(values: dict[str, dict[str, float]]) -> list[RagAnalysisBreakdownItem]:
            rows: list[RagAnalysisBreakdownItem] = []
            for key, aggregate in sorted(values.items(), key=lambda entry: (-entry[1]["value"], entry[0])):
                label = self._clean_rag_text(aggregate.get("label")) or self._clean_rag_text(key)
                if label is None:
                    continue
                rows.append(
                    RagAnalysisBreakdownItem(
                        key=key,
                        label=label,
                        value=int(aggregate["value"]),
                        avg_hit_rate=round(float(aggregate["hit_sum"]) / max(int(aggregate["value"]), 1), 4),
                        avg_citation_coverage=round(float(aggregate["citation_sum"]) / max(int(aggregate["value"]), 1), 4),
                    )
                )
            return rows[:8]

        space_map: dict[str, dict[str, float]] = {}
        source_agent_map: dict[str, dict[str, float]] = {}
        evidence_map: dict[str, dict[str, object]] = {}

        for item in recent_items:
            for key, value_map, label in (
                (item.rag_space_id, space_map, item.rag_space_name or item.rag_space_id),
                (item.source_agent, source_agent_map, item.source_agent),
            ):
                if not key or not self._clean_rag_text(label):
                    continue
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
            space_options=space_options,
            source_agent_options=source_agent_options,
            space_breakdown=build_breakdown(space_map),
            source_agent_breakdown=build_breakdown(source_agent_map),
            evidence_impact=evidence_impact,
            recent_items=recent_items[:30],
        )

    async def get_rag_trace_detail(
        self,
        trace_id: str,
        *,
        global_scope: bool = False,
    ) -> RagTraceDetailResponse:
        rag_repo = RagAnalysisRepository(self._session, None if global_scope else self._org_id)
        item = await rag_repo.get_trace_detail(trace_id)
        if item is None:
            raise NotFoundError(f"RAG trace {trace_id} not found")

        rag_space_name_map: dict[str, str] = {}
        if not global_scope:
            rag_spaces = await RagSpaceRepository(self._session).list_for_org(
                org_id=self._org_id,
                owner_user_id=None,
                limit=500,
            )
            rag_space_name_map = {
                str(space.id): str(space.name).strip()
                for space in rag_spaces
                if getattr(space, "id", None) and str(getattr(space, "name", "")).strip()
            }

        agent_name_map: dict[str, str] = {}
        try:
            registered_agents = await self._agent_repo.list_all_active()
            agent_name_map = {
                str(item.subgraph_key): str(item.name).strip()
                for item in registered_agents
                if getattr(item, "subgraph_key", None) and str(getattr(item, "name", "")).strip()
            }
        except Exception:
            agent_name_map = {}
        source_display_map = {
            "chat": agent_name_map.get("chat") or "Quality Chat",
            "inspection_task": agent_name_map.get("inspection_task") or "Inspection Task Agent",
            "quality_judgement": agent_name_map.get("quality_judgement") or "Quality Judgement",
        }

        metadata = dict(item.get("metadata") or {})
        rag_space_id = self._clean_rag_text(item.get("rag_space_id"))
        rag_space_name = rag_space_name_map.get(rag_space_id or "") or self._clean_rag_text(metadata.get("rag_space_name"))
        if rag_space_id and rag_space_id not in rag_space_name_map and rag_space_name is None:
            rag_space_id = None

        source_agent, source_graph, sub_route = self._resolve_rag_source_agent(
            item,
            source_display_map=source_display_map,
        )
        evidence_found, evidence_used, verdict_impacted = self._derive_rag_effectiveness(item)

        return RagTraceDetailResponse(
            trace_id=self._clean_rag_text(item.get("trace_id")) or trace_id,
            query=self._clean_rag_text(item.get("query")),
            rag_space_id=rag_space_id,
            rag_space_name=rag_space_name,
            source_agent=source_agent,
            source_graph=source_graph,
            sub_route=sub_route,
            top_k=int(item.get("top_k") or 0),
            hit_count=int(item.get("hit_count") or 0),
            hit_rate=float(item.get("hit_rate") or 0.0),
            citation_coverage=float(item.get("citation_coverage") or 0.0),
            latency_ms=float(item.get("latency_ms") or 0.0),
            top_score=float(item.get("top_score")) if item.get("top_score") is not None else None,
            product_family=self._clean_rag_text(metadata.get("product_family")),
            expectation_matched=metadata.get("expectation_matched"),
            evidence_found=evidence_found,
            evidence_used=evidence_used,
            verdict_impacted=verdict_impacted,
            retrieval_config=dict(metadata.get("retrieval_config") or {}),
            retrieved_chunks=[
                dict(chunk) for chunk in list(metadata.get("retrieved_chunks") or []) if isinstance(chunk, dict)
            ],
            used_citations=[
                dict(citation) for citation in list(metadata.get("used_citations") or []) if isinstance(citation, dict)
            ],
            rule_hits=[str(rule) for rule in list(metadata.get("rule_hits") or []) if str(rule).strip()],
            verdict=self._clean_rag_text(metadata.get("verdict")),
            answer=self._clean_rag_text(metadata.get("answer")),
            result=metadata.get("result"),
            top_sources=[str(source) for source in list(metadata.get("top_sources") or []) if str(source).strip()],
            created_at=item.get("created_at"),
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


