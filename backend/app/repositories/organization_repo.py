import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization


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
