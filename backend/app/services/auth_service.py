from sqlalchemy.ext.asyncio import AsyncSession

import uuid

from app.core.claims import build_auth_claims
from app.core.exceptions import ConflictError, ForbiddenError
from app.core.permissions import ROLE_ADMIN
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
        claims = build_auth_claims(user.role, getattr(org, "plan", None))
        access = create_access_token(
            subject=user.id,
            extra=claims.as_token_extra(user.org_id),
        )
        refresh = create_refresh_token(
            subject=user.id,
            extra=claims.as_token_extra(user.org_id),
        )
        return user, access, refresh

    async def register(
        self, create_org: bool | str = True, org_name: str | None = None, org_slug: str | None = None,
        username: str | None = None, email: str | None = None, password: str | None = None, role: str = "admin",
    ) -> tuple[User, str, str]:
        from app.core.exceptions import NotFoundError
        from app.core.permissions import ensure_valid_role
        if not isinstance(create_org, bool):
            password = email
            email = username
            username = org_slug
            org_slug = org_name
            org_name = str(create_org)
            create_org = True
        org_name = str(org_name or "")
        org_slug = str(org_slug or "")
        username = str(username or "")
        email = str(email or "")
        password = str(password or "")
        ensure_valid_role(role)

        if create_org:
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
            org_id = org.id
        else:
            org = await self._orgs.get_by_slug(org_slug)
            if not org:
                raise NotFoundError("organization not found")
            if not org.is_active:
                raise ForbiddenError("organization disabled")
            org_id = org.id
            existing_user = await self._users.get_by_username(org_id, username)
            if existing_user:
                raise ConflictError("username already exists in this organization")

        user = User(
            id=str(uuid.uuid4()),
            org_id=org_id,
            username=username,
            email=email,
            password_hash=hash_password(password),
            role=role,
            is_active=True,
        )
        await self._users.create(user)

        claims = build_auth_claims(user.role, getattr(org, "plan", None))
        access = create_access_token(
            subject=user.id,
            extra=claims.as_token_extra(user.org_id),
        )
        refresh = create_refresh_token(
            subject=user.id,
            extra=claims.as_token_extra(user.org_id),
        )
        return user, access, refresh
