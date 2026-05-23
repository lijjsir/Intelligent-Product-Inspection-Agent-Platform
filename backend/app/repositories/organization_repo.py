import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.user import User


class OrganizationRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, org_id: str) -> Organization | None:
        try:
            uuid.UUID(str(org_id))
        except Exception:
            return None
        result = await self._session.execute(select(Organization).where(Organization.id == org_id))
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Organization | None:
        result = await self._session.execute(select(Organization).where(Organization.slug == slug))
        return result.scalar_one_or_none()

    async def create(self, org: Organization) -> Organization:
        self._session.add(org)
        await self._session.flush()
        return org

    async def list_all(self) -> list[tuple[Organization, int]]:
        result = await self._session.execute(
            select(Organization, func.count(User.id))
            .outerjoin(User, User.org_id == Organization.id)
            .where(Organization.deleted_at.is_(None))
            .group_by(Organization.id)
            .order_by(Organization.created_at.desc())
        )
        return [(row[0], int(row[1] or 0)) for row in result.all()]

    async def update(self, org: Organization, payload) -> Organization:
        if payload.name is not None:
            org.name = payload.name.strip()
        if payload.slug is not None:
            org.slug = payload.slug.strip()
        if payload.plan is not None:
            org.plan = payload.plan.strip()
        if payload.settings is not None:
            org.settings = payload.settings
        if payload.is_active is not None:
            org.is_active = payload.is_active
        await self._session.flush()
        return org

    async def soft_delete(self, org: Organization) -> Organization:
        from datetime import datetime

        org.deleted_at = datetime.utcnow()
        await self._session.flush()
        return org

    async def list_by_ids(self, org_ids: list[str]) -> list[Organization]:
        if not org_ids:
            return []
        result = await self._session.execute(
            select(Organization).where(Organization.id.in_(org_ids), Organization.deleted_at.is_(None))
        )
        return list(result.scalars().all())
