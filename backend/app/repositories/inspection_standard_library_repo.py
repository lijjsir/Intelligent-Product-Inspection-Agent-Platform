from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inspection_standard_library import InspectionStandardLibrary


class InspectionStandardLibraryRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_all(self, org_id: str) -> list[InspectionStandardLibrary]:
        result = await self._session.execute(
            select(InspectionStandardLibrary)
            .where(
                InspectionStandardLibrary.deleted_at.is_(None),
                InspectionStandardLibrary.org_id == org_id,
            )
            .order_by(
                InspectionStandardLibrary.product_family.asc(),
                InspectionStandardLibrary.created_at.desc(),
            )
        )
        return list(result.scalars().all())

    async def get(self, org_id: str, library_id: str) -> InspectionStandardLibrary | None:
        result = await self._session.execute(
            select(InspectionStandardLibrary).where(
                InspectionStandardLibrary.id == library_id,
                InspectionStandardLibrary.deleted_at.is_(None),
                InspectionStandardLibrary.org_id == org_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_product_family(self, org_id: str, product_family: str) -> InspectionStandardLibrary | None:
        result = await self._session.execute(
            select(InspectionStandardLibrary)
            .where(
                InspectionStandardLibrary.product_family == product_family,
                InspectionStandardLibrary.is_active.is_(True),
                InspectionStandardLibrary.deleted_at.is_(None),
                InspectionStandardLibrary.org_id == org_id,
            )
            .order_by(
                InspectionStandardLibrary.updated_at.desc(),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create(self, library: InspectionStandardLibrary) -> InspectionStandardLibrary:
        self._session.add(library)
        await self._session.flush()
        await self._session.refresh(library, attribute_names=["created_at", "updated_at"])
        return library

    async def update(self, library: InspectionStandardLibrary, payload: dict) -> InspectionStandardLibrary:
        for key, value in payload.items():
            setattr(library, key, value)
        await self._session.flush()
        await self._session.refresh(library, attribute_names=["updated_at"])
        return library

    async def soft_delete(self, library: InspectionStandardLibrary) -> None:
        from app.core.datetime import utcnow

        library.deleted_at = utcnow()
        await self._session.flush()
