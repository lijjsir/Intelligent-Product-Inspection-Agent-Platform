from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_config import ModelConfig


class ModelConfigRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_all(self, org_id: str) -> list[ModelConfig]:
        result = await self._session.execute(
            select(ModelConfig)
            .where(or_(ModelConfig.org_id.is_(None), ModelConfig.org_id == org_id))
            .order_by(ModelConfig.priority.asc(), ModelConfig.display_name.asc())
        )
        return list(result.scalars().all())

    async def get(self, org_id: str, config_id: str) -> ModelConfig | None:
        result = await self._session.execute(
            select(ModelConfig).where(
                ModelConfig.id == config_id,
                or_(ModelConfig.org_id.is_(None), ModelConfig.org_id == org_id),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, payload: dict) -> ModelConfig:
        obj = ModelConfig(**payload)
        self._session.add(obj)
        await self._session.flush()
        return obj

    async def save(self, model: ModelConfig, payload: dict) -> ModelConfig:
        for key, value in payload.items():
            setattr(model, key, value)
        await self._session.flush()
        return model

    async def delete(self, model: ModelConfig) -> None:
        await self._session.delete(model)
        await self._session.flush()

    async def list_active(self, org_id: str) -> list[ModelConfig]:
        result = await self._session.execute(
            select(ModelConfig)
            .where(
                or_(ModelConfig.org_id.is_(None), ModelConfig.org_id == org_id),
                ModelConfig.is_active.is_(True),
            )
            .order_by(ModelConfig.priority.asc())
        )
        return list(result.scalars().all())

    async def list_health_targets(self) -> list[ModelConfig]:
        result = await self._session.execute(
            select(ModelConfig)
            .where(ModelConfig.is_active.is_(True))
            .order_by(ModelConfig.priority.asc(), ModelConfig.display_name.asc())
        )
        return list(result.scalars().all())

    async def update_health(self, model: ModelConfig, *, health_status: str, health_message: str | None) -> ModelConfig:
        model.health_status = health_status
        model.health_message = health_message
        await self._session.flush()
        return model
