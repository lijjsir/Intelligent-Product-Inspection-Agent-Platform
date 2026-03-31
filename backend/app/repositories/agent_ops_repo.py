from __future__ import annotations

from typing import TypeVar

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_ops import AgentDefinition, IntentRoute, PromptVersion

T = TypeVar("T")


class AgentOpsRepository:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id

    async def _get_by_id(self, model: type[T], id: str) -> T | None:
        result = await self._session.execute(
            select(model).where(model.org_id == self._org_id, model.id == id, model.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()


class AgentDefinitionRepository(AgentOpsRepository):
    async def create(self, data: dict) -> AgentDefinition:
        obj = AgentDefinition(**data, org_id=self._org_id)
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj, attribute_names=["created_at", "updated_at"])
        return obj

    async def get(self, id: str) -> AgentDefinition | None:
        return await self._get_by_id(AgentDefinition, id)

    async def update(self, id: str, data: dict) -> AgentDefinition | None:
        obj = await self.get(id)
        if not obj:
            return None
        for key, value in data.items():
            if value is not None:
                setattr(obj, key, value)
        await self._session.flush()
        await self._session.refresh(obj, attribute_names=["updated_at"])
        return obj

    async def delete(self, id: str) -> bool:
        obj = await self.get(id)
        if not obj:
            return False
        from datetime import datetime
        obj.deleted_at = datetime.utcnow()
        await self._session.flush()
        return True

    async def list_paged(self, filters: dict, page: int, size: int) -> tuple[list[AgentDefinition], int]:
        base = select(AgentDefinition).where(
            AgentDefinition.org_id == self._org_id, AgentDefinition.deleted_at.is_(None)
        )
        if "name" in filters:
            base = base.where(AgentDefinition.name.like(f"%{filters['name']}%"))
        if "is_active" in filters:
            base = base.where(AgentDefinition.is_active == filters["is_active"])

        total = await self._session.scalar(select(func.count()).select_from(base.subquery()))
        items = await self._session.execute(
            base.order_by(AgentDefinition.created_at.desc()).offset((page - 1) * size).limit(size)
        )
        return list(items.scalars().all()), int(total or 0)

    async def list_all_active(self) -> list[AgentDefinition]:
        result = await self._session.execute(
            select(AgentDefinition).where(
                AgentDefinition.org_id == self._org_id,
                AgentDefinition.is_active == True,
                AgentDefinition.deleted_at.is_(None),
            ).order_by(AgentDefinition.name)
        )
        return list(result.scalars().all())


class PromptVersionRepository(AgentOpsRepository):
    async def create(self, data: dict) -> PromptVersion:
        obj = PromptVersion(**data, org_id=self._org_id)
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj, attribute_names=["created_at", "updated_at"])
        return obj

    async def get(self, id: str) -> PromptVersion | None:
        return await self._get_by_id(PromptVersion, id)

    async def update(self, id: str, data: dict) -> PromptVersion | None:
        obj = await self.get(id)
        if not obj:
            return None
        for key, value in data.items():
            if value is not None:
                setattr(obj, key, value)
        await self._session.flush()
        await self._session.refresh(obj, attribute_names=["updated_at"])
        return obj

    async def delete(self, id: str) -> bool:
        obj = await self.get(id)
        if not obj:
            return False
        from datetime import datetime
        obj.deleted_at = datetime.utcnow()
        await self._session.flush()
        return True

    async def list_paged(self, filters: dict, page: int, size: int) -> tuple[list[PromptVersion], int]:
        base = select(PromptVersion).where(
            PromptVersion.org_id == self._org_id, PromptVersion.deleted_at.is_(None)
        )
        if "name" in filters:
            base = base.where(PromptVersion.name.like(f"%{filters['name']}%"))
        if "status" in filters:
            base = base.where(PromptVersion.status == filters["status"])

        total = await self._session.scalar(select(func.count()).select_from(base.subquery()))
        items = await self._session.execute(
            base.order_by(PromptVersion.created_at.desc()).offset((page - 1) * size).limit(size)
        )
        return list(items.scalars().all()), int(total or 0)

    async def get_latest_version(self, name: str) -> PromptVersion | None:
        result = await self._session.execute(
            select(PromptVersion)
            .where(
                PromptVersion.org_id == self._org_id,
                PromptVersion.name == name,
                PromptVersion.deleted_at.is_(None),
            )
            .order_by(PromptVersion.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


class IntentRouteRepository(AgentOpsRepository):
    async def create(self, data: dict) -> IntentRoute:
        obj = IntentRoute(**data, org_id=self._org_id)
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj, attribute_names=["created_at", "updated_at"])
        return obj

    async def get(self, id: str) -> IntentRoute | None:
        return await self._get_by_id(IntentRoute, id)

    async def update(self, id: str, data: dict) -> IntentRoute | None:
        obj = await self.get(id)
        if not obj:
            return None
        for key, value in data.items():
            if value is not None:
                setattr(obj, key, value)
        await self._session.flush()
        await self._session.refresh(obj, attribute_names=["updated_at"])
        return obj

    async def delete(self, id: str) -> bool:
        obj = await self.get(id)
        if not obj:
            return False
        from datetime import datetime
        obj.deleted_at = datetime.utcnow()
        await self._session.flush()
        return True

    async def list_paged(self, filters: dict, page: int, size: int) -> tuple[list[IntentRoute], int]:
        base = select(IntentRoute).where(
            IntentRoute.org_id == self._org_id, IntentRoute.deleted_at.is_(None)
        )
        if "intent_name" in filters:
            base = base.where(IntentRoute.intent_name.like(f"%{filters['intent_name']}%"))
        if "is_active" in filters:
            base = base.where(IntentRoute.is_active == filters["is_active"])

        total = await self._session.scalar(select(func.count()).select_from(base.subquery()))
        items = await self._session.execute(
            base.order_by(IntentRoute.priority.desc(), IntentRoute.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return list(items.scalars().all()), int(total or 0)

    async def list_all_active(self) -> list[IntentRoute]:
        result = await self._session.execute(
            select(IntentRoute)
            .where(
                IntentRoute.org_id == self._org_id,
                IntentRoute.is_active == True,
                IntentRoute.deleted_at.is_(None),
            )
            .order_by(IntentRoute.priority.desc())
        )
        return list(result.scalars().all())
