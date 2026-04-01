from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag_space import RagSpace, RagSpaceFile


class RagSpaceRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, *, org_id: str, created_by: str | None, name: str, description: str | None) -> RagSpace:
        obj = RagSpace(
            org_id=org_id,
            created_by=created_by,
            name=name,
            description=description,
            status="ready",
        )
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj, attribute_names=["created_at", "updated_at"])
        return obj

    async def get(self, *, org_id: str, rag_space_id: str) -> RagSpace | None:
        result = await self._session.execute(
            select(RagSpace).where(
                RagSpace.org_id == org_id,
                RagSpace.id == rag_space_id,
                RagSpace.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_for_org(self, *, org_id: str, limit: int = 200) -> list[RagSpace]:
        result = await self._session.execute(
            select(RagSpace)
            .where(
                RagSpace.org_id == org_id,
                RagSpace.deleted_at.is_(None),
            )
            .order_by(RagSpace.updated_at.desc(), RagSpace.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def increment_selected_count(self, *, org_id: str, rag_space_id: str) -> None:
        obj = await self.get(org_id=org_id, rag_space_id=rag_space_id)
        if obj is None:
            return
        obj.selected_count = int(obj.selected_count or 0) + 1
        await self._session.flush()

    async def recalculate_file_count(self, *, org_id: str, rag_space_id: str) -> None:
        obj = await self.get(org_id=org_id, rag_space_id=rag_space_id)
        if obj is None:
            return
        total = await self._session.scalar(
            select(func.count(RagSpaceFile.id)).where(
                RagSpaceFile.org_id == org_id,
                RagSpaceFile.rag_space_id == rag_space_id,
                RagSpaceFile.deleted_at.is_(None),
            )
        )
        obj.file_count = int(total or 0)
        await self._session.flush()


class RagSpaceFileRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(
        self,
        *,
        rag_space_id: str,
        org_id: str,
        uploaded_by: str | None,
        file_name: str,
        content_type: str | None,
        file_url: str,
        size_bytes: int,
        status: str = "ready",
    ) -> RagSpaceFile:
        obj = RagSpaceFile(
            rag_space_id=rag_space_id,
            org_id=org_id,
            uploaded_by=uploaded_by,
            file_name=file_name,
            content_type=content_type,
            file_url=file_url,
            size_bytes=size_bytes,
            status=status,
        )
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj, attribute_names=["created_at", "updated_at"])
        return obj

    async def list_for_space(self, *, org_id: str, rag_space_id: str, limit: int = 200) -> list[RagSpaceFile]:
        result = await self._session.execute(
            select(RagSpaceFile)
            .where(
                RagSpaceFile.org_id == org_id,
                RagSpaceFile.rag_space_id == rag_space_id,
                RagSpaceFile.deleted_at.is_(None),
            )
            .order_by(RagSpaceFile.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
