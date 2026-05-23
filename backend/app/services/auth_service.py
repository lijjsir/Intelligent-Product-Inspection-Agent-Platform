from fastapi import Request
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
from app.services.auth_log_service import AuthLogService, _is_auth_logs_table_missing


class AuthService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._users = UserRepository(session)
        self._orgs = OrganizationRepository(session)
        self._auth_logs = AuthLogService(session)

    async def _record_login_log(self, **payload) -> None:
        try:
            await self._auth_logs.record_login(**payload)
        except Exception as exc:
            if _is_auth_logs_table_missing(exc):
                return
            raise

    async def login(self, org_id: str, username: str, password: str, request: Request | None = None) -> tuple[User, str, str]:
        org = await self._orgs.get_by_id(org_id)
        if not org:
            org = await self._orgs.get_by_slug(org_id)
            if org:
                org_id = org.id
        if not org or not org.is_active:
            await self._record_login_log(org_id=org_id, username=username, request=request, success=False, detail="invalid organization")
            raise ForbiddenError("invalid organization")
        user = await self._users.get_by_username(org_id, username)
        if not user or not user.password_hash:
            await self._record_login_log(org_id=org_id, username=username, request=request, success=False, detail="invalid credentials")
            raise ForbiddenError("invalid credentials")
        if not user.is_active:
            await self._record_login_log(org_id=org_id, username=username, request=request, success=False, user_id=user.id, detail="user disabled")
            raise ForbiddenError("user disabled")
        if not verify_password(password, user.password_hash):
            await self._record_login_log(org_id=org_id, username=username, request=request, success=False, user_id=user.id, detail="invalid credentials")
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
        await self._record_login_log(org_id=org_id, username=user.username, request=request, success=True, user_id=user.id)
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

            # Seed default alert rules for the new organization.
            from app.services.alert_rule_service import AlertRuleService
            await AlertRuleService.seed_default_rules(self._session, org_id)
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
