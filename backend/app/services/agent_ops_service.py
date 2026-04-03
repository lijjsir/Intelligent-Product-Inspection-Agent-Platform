from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.repositories.agent_ops_repo import (
    AgentDefinitionRepository,
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

    async def get_rag_analysis(self) -> RagAnalysisResponse:
        rag_repo = RagAnalysisRepository(self._session, self._org_id)
        stats_data = await rag_repo.get_rag_stats()
        recent_items_data = await rag_repo.get_recent_rag_items()

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
                query="",
                hit_rate=item["hit_rate"],
                citation_coverage=item["citation_coverage"],
                latency_ms=item["latency_ms"],
                created_at=item["created_at"],
            )
            for item in recent_items_data
        ]

        return RagAnalysisResponse(stats=stats, recent_items=recent_items)

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
