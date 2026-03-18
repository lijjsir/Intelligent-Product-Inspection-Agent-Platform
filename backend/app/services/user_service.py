import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import ensure_valid_role
from app.core.security import hash_password
from app.models.user import User
from app.repositories.user_repo import UserRepository


class UserService:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id
        self._repo = UserRepository(session)

    async def create_user(self, username: str, email: str, password: str, role: str) -> User:
        ensure_valid_role(role)
        if await self._repo.get_by_username(self._org_id, username):
            raise ConflictError("username already exists")
        if await self._repo.get_by_email(self._org_id, email):
            raise ConflictError("email already exists")
        user = User(
            id=str(uuid.uuid4()),
            org_id=self._org_id,
            username=username,
            email=email,
            password_hash=hash_password(password),
            role=role,
            is_active=True,
        )
        return await self._repo.create(user)

    async def list_users(self, page: int, size: int) -> tuple[list[User], int]:
        offset = (page - 1) * size
        items = await self._repo.list(self._org_id, offset, size)
        total = await self._repo.count(self._org_id)
        return items, total

    async def get_user(self, user_id: str) -> User:
        user = await self._repo.get_by_id(self._org_id, user_id)
        if not user:
            raise NotFoundError("user not found")
        return user

    async def update_role(self, user_id: str, role: str) -> User:
        ensure_valid_role(role)
        user = await self.get_user(user_id)
        user.role = role
        await self._session.flush()
        return user

    async def update_status(self, user_id: str, is_active: bool) -> User:
        user = await self.get_user(user_id)
        user.is_active = is_active
        await self._session.flush()
        return user

    async def reset_password(self, user_id: str, password: str) -> User:
        user = await self.get_user(user_id)
        user.password_hash = hash_password(password)
        await self._session.flush()
        return user
