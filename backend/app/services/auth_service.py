from sqlalchemy.ext.asyncio import AsyncSession

import uuid

from app.core.exceptions import ConflictError, ForbiddenError
from app.core.permissions import ROLE_ORG_ADMIN
from app.core.security import create_access_token, create_refresh_token, hash_password, verify_password
from app.models.organization import Organization
from app.models.user import User
from app.repositories.organization_repo import OrganizationRepository
from app.repositories.user_repo import UserRepository


class AuthService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._users = UserRepository(session)
        self._orgs = OrganizationRepository(session)

    async def login(self, org_id: str, username: str, password: str) -> tuple[User, str, str]:
        org = await self._orgs.get_by_id(org_id)
        if not org:
            org = await self._orgs.get_by_slug(org_id)
            if org:
                org_id = org.id
        if not org or not org.is_active:
            raise ForbiddenError("invalid organization")
        user = await self._users.get_by_username(org_id, username)
        if not user or not user.password_hash:
            raise ForbiddenError("invalid credentials")
        if not user.is_active:
            raise ForbiddenError("user disabled")
        if not verify_password(password, user.password_hash):
            raise ForbiddenError("invalid credentials")
        access = create_access_token(
            subject=user.id,
            extra={"org_id": user.org_id, "role": user.role},
        )
        refresh = create_refresh_token(
            subject=user.id,
            extra={"org_id": user.org_id, "role": user.role},
        )
        return user, access, refresh

    async def register(
        self, org_name: str, org_slug: str, username: str, email: str, password: str
    ) -> tuple[User, str, str]:
        existing_org = await self._orgs.get_by_slug(org_slug)
        if existing_org:
            raise ConflictError("organization already exists")

        org = Organization(
            id=str(uuid.uuid4()),
            name=org_name,
            slug=org_slug,
            plan="standard",
            is_active=True,
        )
        await self._orgs.create(org)

        user = User(
            id=str(uuid.uuid4()),
            org_id=org.id,
            username=username,
            email=email,
            password_hash=hash_password(password),
            role=ROLE_ORG_ADMIN,
            is_active=True,
        )
        await self._users.create(user)

        access = create_access_token(
            subject=user.id,
            extra={"org_id": user.org_id, "role": user.role},
        )
        refresh = create_refresh_token(
            subject=user.id,
            extra={"org_id": user.org_id, "role": user.role},
        )
        return user, access, refresh
