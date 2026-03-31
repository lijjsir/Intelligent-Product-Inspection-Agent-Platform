from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.repositories.agent_ops_repo import (
    AgentDefinitionRepository,
    IntentRouteRepository,
    PromptVersionRepository,
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

    async def list_agents(self, query: AgentDefinitionListQuery) -> tuple[list[AgentDefinitionResponse], int]:
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
        obj = await self._agent_repo.create(body.model_dump())
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
        stats = RagAnalysisStats(
            total_queries=0,
            avg_hit_rate=0.0,
            avg_citation_coverage=0.0,
            empty_recall_count=0,
            avg_latency_ms=0.0,
        )
        return RagAnalysisResponse(stats=stats, recent_items=[])
