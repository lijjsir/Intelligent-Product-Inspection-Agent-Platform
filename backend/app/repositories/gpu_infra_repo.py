from __future__ import annotations

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gpu_infra import GpuComputeNode, GpuJobLease


class GpuComputeNodeRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, payload: dict) -> GpuComputeNode:
        obj = GpuComputeNode(**payload)
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj)
        return obj

    async def get(self, *, org_id: str, node_id: str) -> GpuComputeNode | None:
        result = await self._session.execute(
            select(GpuComputeNode).where(
                GpuComputeNode.id == node_id,
                GpuComputeNode.org_id == org_id,
                GpuComputeNode.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_name_or_host(self, *, org_id: str, name: str, host: str) -> GpuComputeNode | None:
        result = await self._session.execute(
            select(GpuComputeNode).where(
                GpuComputeNode.org_id == org_id,
                GpuComputeNode.deleted_at.is_(None),
                or_(GpuComputeNode.name == name, GpuComputeNode.host == host),
            )
        )
        return result.scalar_one_or_none()

    async def list(self, *, org_id: str) -> list[GpuComputeNode]:
        rows = (
            (
                await self._session.execute(
                    select(GpuComputeNode)
                    .where(GpuComputeNode.org_id == org_id, GpuComputeNode.deleted_at.is_(None))
                    .order_by(GpuComputeNode.updated_at.desc(), GpuComputeNode.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def list_online(self, *, org_id: str) -> list[GpuComputeNode]:
        rows = (
            (
                await self._session.execute(
                    select(GpuComputeNode)
                    .where(
                        GpuComputeNode.org_id == org_id,
                        GpuComputeNode.deleted_at.is_(None),
                        GpuComputeNode.status == "online",
                    )
                    .order_by(GpuComputeNode.load_score.asc().nullsfirst(), GpuComputeNode.updated_at.desc())
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def save(self, obj: GpuComputeNode, payload: dict) -> GpuComputeNode:
        for key, value in payload.items():
            setattr(obj, key, value)
        await self._session.flush()
        await self._session.refresh(obj)
        return obj

    async def soft_delete(self, obj: GpuComputeNode) -> None:
        from sqlalchemy import func

        obj.deleted_at = func.now()
        await self._session.flush()


class GpuJobLeaseRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, payload: dict) -> GpuJobLease:
        obj = GpuJobLease(**payload)
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj)
        return obj

    async def list_active_for_resource(self, *, org_id: str, resource_type: str, resource_id: str) -> list[GpuJobLease]:
        rows = (
            (
                await self._session.execute(
                    select(GpuJobLease).where(
                        GpuJobLease.org_id == org_id,
                        GpuJobLease.resource_type == resource_type,
                        GpuJobLease.resource_id == resource_id,
                        GpuJobLease.deleted_at.is_(None),
                        GpuJobLease.status == "leased",
                    )
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def save(self, obj: GpuJobLease, payload: dict) -> GpuJobLease:
        for key, value in payload.items():
            setattr(obj, key, value)
        await self._session.flush()
        await self._session.refresh(obj)
        return obj
