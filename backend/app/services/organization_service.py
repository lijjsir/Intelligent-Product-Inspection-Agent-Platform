from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.organization import Organization
from app.repositories.organization_repo import OrganizationRepository
from app.repositories.user_repo import UserRepository
from app.schemas.organization import OrganizationCreate, OrganizationUpdate


class OrganizationService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._repo = OrganizationRepository(session)
        self._users = UserRepository(session)

    async def list_organizations(self) -> list[tuple[Organization, int]]:
        return await self._repo.list_all()

    async def create_organization(self, payload: OrganizationCreate) -> Organization:
        existing = await self._repo.get_by_slug(payload.slug.strip())
        if existing:
            raise ConflictError("organization slug already exists")
        org = Organization(
            id=str(uuid.uuid4()),
            name=payload.name.strip(),
            slug=payload.slug.strip(),
            plan=payload.plan.strip(),
            settings=payload.settings or {},
            is_active=True,
        )
        return await self._repo.create(org)

    async def update_organization(self, org_id: str, payload: OrganizationUpdate) -> Organization:
        org = await self._repo.get_by_id(org_id)
        if not org or getattr(org, "deleted_at", None) is not None:
            raise NotFoundError("organization not found")
        if payload.slug and payload.slug.strip() != org.slug:
            existing = await self._repo.get_by_slug(payload.slug.strip())
            if existing and existing.id != org.id:
                raise ConflictError("organization slug already exists")
        return await self._repo.update(org, payload)

    async def delete_organization(self, org_id: str) -> None:
        org = await self._repo.get_by_id(org_id)
        if not org or getattr(org, "deleted_at", None) is not None:
            raise NotFoundError("organization not found")
        await self._repo.soft_delete(org)

    async def get_organization_users(self, org_id: str):
        org = await self._repo.get_by_id(org_id)
        if not org or getattr(org, "deleted_at", None) is not None:
            raise NotFoundError("organization not found")
        users = await self._users.list_by_org_id(org_id)
        return org, users

    async def assign_users(self, org_id: str, user_ids: list[str], action: str) -> int:
        org = await self._repo.get_by_id(org_id)
        if not org or getattr(org, "deleted_at", None) is not None:
            raise NotFoundError("organization not found")
        if action == "remove":
            raise ValidationError("remove action is not supported until user org binding becomes optional")
        next_org_id = org_id if action == "assign" else None
        return await self._users.bulk_update_org(user_ids, next_org_id)
