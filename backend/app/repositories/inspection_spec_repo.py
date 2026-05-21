from __future__ import annotations

from sqlalchemy import case, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inspection_spec import InspectionSpec, InspectionSpecItem


class InspectionSpecRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_all(self, org_id: str) -> list[InspectionSpec]:
        result = await self._session.execute(
            select(InspectionSpec)
            .where(
                InspectionSpec.deleted_at.is_(None),
                or_(InspectionSpec.org_id == org_id, InspectionSpec.org_id.is_(None)),
            )
            .order_by(
                case((InspectionSpec.org_id == org_id, 0), else_=1),
                InspectionSpec.spec_code.asc(),
                InspectionSpec.version.desc(),
            )
        )
        return list(result.scalars().all())

    async def get(self, org_id: str, inspection_spec_row_id: str) -> InspectionSpec | None:
        result = await self._session.execute(
            select(InspectionSpec).where(
                InspectionSpec.id == inspection_spec_row_id,
                or_(InspectionSpec.org_id == org_id, InspectionSpec.org_id.is_(None)),
            )
        )
        return result.scalar_one_or_none()

    async def get_for_write(
        self,
        org_id: str,
        inspection_spec_row_id: str,
        include_global: bool = False,
    ) -> InspectionSpec | None:
        conditions = [InspectionSpec.org_id == org_id]
        if include_global:
            conditions.append(InspectionSpec.org_id.is_(None))
        result = await self._session.execute(
            select(InspectionSpec).where(
                InspectionSpec.id == inspection_spec_row_id,
                or_(*conditions),
            )
        )
        return result.scalar_one_or_none()

    async def get_active_spec(self, org_id: str, spec_code: str) -> InspectionSpec | None:
        result = await self._session.execute(
            select(InspectionSpec)
            .where(
                InspectionSpec.spec_code == spec_code,
                InspectionSpec.is_active.is_(True),
                or_(InspectionSpec.org_id == org_id, InspectionSpec.org_id.is_(None)),
            )
            .order_by(
                case((InspectionSpec.org_id == org_id, 0), else_=1),
                InspectionSpec.created_at.desc(),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create_spec(self, payload: dict, items: list[dict]) -> InspectionSpec:
        spec = InspectionSpec(**payload)
        self._session.add(spec)
        await self._session.flush()
        for row in items:
            self._session.add(InspectionSpecItem(**row))
        await self._session.flush()
        await self._session.refresh(spec, attribute_names=["created_at", "updated_at"])
        return spec

    async def save_spec(self, spec: InspectionSpec, payload: dict) -> InspectionSpec:
        for key, value in payload.items():
            setattr(spec, key, value)
        await self._session.flush()
        await self._session.refresh(spec, attribute_names=["updated_at"])
        return spec

    async def list_items(self, spec_row_id: str) -> list[InspectionSpecItem]:
        result = await self._session.execute(
            select(InspectionSpecItem)
            .where(InspectionSpecItem.spec_row_id == spec_row_id)
            .order_by(InspectionSpecItem.created_at.asc())
        )
        return list(result.scalars().all())

    async def list_items_map(self, spec_row_ids: list[str]) -> dict[str, list[InspectionSpecItem]]:
        if not spec_row_ids:
            return {}
        result = await self._session.execute(
            select(InspectionSpecItem)
            .where(InspectionSpecItem.spec_row_id.in_(spec_row_ids))
            .order_by(InspectionSpecItem.spec_row_id.asc(), InspectionSpecItem.created_at.asc())
        )
        items_map: dict[str, list[InspectionSpecItem]] = {spec_row_id: [] for spec_row_id in spec_row_ids}
        for item in result.scalars().all():
            items_map.setdefault(item.spec_row_id, []).append(item)
        return items_map

    async def replace_items(self, spec_row_id: str, items: list[dict]) -> None:
        await self._session.execute(delete(InspectionSpecItem).where(InspectionSpecItem.spec_row_id == spec_row_id))
        for row in items:
            self._session.add(InspectionSpecItem(**row))
        await self._session.flush()

    async def delete_spec(self, spec: InspectionSpec) -> None:
        await self._session.execute(delete(InspectionSpecItem).where(InspectionSpecItem.spec_row_id == spec.id))
        await self._session.delete(spec)
        await self._session.flush()
