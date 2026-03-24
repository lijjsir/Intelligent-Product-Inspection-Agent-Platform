import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.permissions import (
    ROLE_AGENT_OPERATOR,
    ROLE_AI_QUALITY,
    ROLE_ANALYST,
    ROLE_INSPECTOR,
    ROLE_ORG_ADMIN,
    ROLE_PLATFORM_ADMIN,
    ROLE_SUPER_ADMIN,
    ROLE_VIEWER,
    ensure_valid_role,
)
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.repositories.user_repo import UserRepository


class UserService:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id
        self._repo = UserRepository(session)

    async def create_user(self, username: str, email: str, password: str, role: str, actor_role: str) -> User:
        ensure_valid_role(role)
        self._ensure_assignable_role(actor_role, role)
        normalized_username = username.strip()
        normalized_email = email.strip().lower()
        if await self._repo.get_by_username(self._org_id, normalized_username):
            raise ConflictError("username already exists")
        if await self._repo.get_by_email(self._org_id, normalized_email):
            raise ConflictError("email already exists")
        user = User(
            id=str(uuid.uuid4()),
            org_id=self._org_id,
            username=normalized_username,
            email=normalized_email,
            password_hash=hash_password(password),
            role=role,
            is_active=True,
        )
        return await self._repo.create(user)

    async def list_users(
        self,
        page: int,
        size: int,
        keyword: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[User], int]:
        offset = (page - 1) * size
        items = await self._repo.list(self._org_id, offset, size, keyword, role, is_active)
        total = await self._repo.count(self._org_id, keyword, role, is_active)
        return items, total

    async def get_user(self, user_id: str) -> User:
        user = await self._repo.get_by_id(self._org_id, user_id)
        if not user:
            raise NotFoundError("user not found")
        return user

    async def update_role(self, user_id: str, role: str, actor_role: str, actor_id: str) -> User:
        ensure_valid_role(role)
        if user_id == actor_id:
            raise ForbiddenError("cannot change own role")
        self._ensure_assignable_role(actor_role, role)
        user = await self.get_user(user_id)
        user.role = role
        await self._session.flush()
        return user

    async def update_status(self, user_id: str, is_active: bool, actor_id: str) -> User:
        if user_id == actor_id and not is_active:
            raise ForbiddenError("cannot deactivate self")
        user = await self.get_user(user_id)
        user.is_active = is_active
        await self._session.flush()
        return user

    async def reset_password(self, user_id: str, password: str, actor_id: str) -> User:
        if user_id == actor_id:
            raise ForbiddenError("use profile settings to change your own password")
        user = await self.get_user(user_id)
        user.password_hash = hash_password(password)
        await self._session.flush()
        return user

    async def update_profile(
        self,
        user_id: str,
        username: str | None = None,
        email: str | None = None,
        current_password: str | None = None,
        new_password: str | None = None,
    ) -> User:
        user = await self.get_user(user_id)

        if username is not None:
            normalized_username = username.strip()
            if normalized_username != user.username:
                existing = await self._repo.get_by_username(self._org_id, normalized_username)
                if existing and existing.id != user.id:
                    raise ConflictError("username already exists")
                user.username = normalized_username

        if email is not None:
            normalized_email = email.strip().lower()
            if normalized_email != user.email:
                existing = await self._repo.get_by_email(self._org_id, normalized_email)
                if existing and existing.id != user.id:
                    raise ConflictError("email already exists")
                user.email = normalized_email

        if current_password or new_password:
            if not current_password or not new_password:
                raise ForbiddenError("current_password and new_password are required")
            if not user.password_hash or not verify_password(current_password, user.password_hash):
                raise ForbiddenError("current password is invalid")
            user.password_hash = hash_password(new_password)

        await self._session.flush()
        return user

    @staticmethod
    def get_assignable_roles(actor_role: str) -> list[str]:
        if actor_role == ROLE_SUPER_ADMIN:
            return [
                ROLE_SUPER_ADMIN,
                ROLE_ORG_ADMIN,
                ROLE_INSPECTOR,
                ROLE_VIEWER,
                ROLE_ANALYST,
                ROLE_PLATFORM_ADMIN,
                ROLE_AI_QUALITY,
                ROLE_AGENT_OPERATOR,
            ]

        if actor_role == ROLE_ORG_ADMIN:
            return [
                ROLE_ORG_ADMIN,
                ROLE_INSPECTOR,
                ROLE_VIEWER,
                ROLE_ANALYST,
                ROLE_AI_QUALITY,
                ROLE_AGENT_OPERATOR,
            ]

        return []

    @staticmethod
    def _ensure_assignable_role(actor_role: str, target_role: str) -> None:
        if actor_role == ROLE_SUPER_ADMIN:
            return

        if actor_role == ROLE_ORG_ADMIN and target_role in {
            ROLE_ORG_ADMIN,
            ROLE_INSPECTOR,
            ROLE_VIEWER,
            ROLE_ANALYST,
            ROLE_AI_QUALITY,
            ROLE_AGENT_OPERATOR,
        }:
            return

        raise ForbiddenError(f"role {actor_role} cannot assign {target_role}")
