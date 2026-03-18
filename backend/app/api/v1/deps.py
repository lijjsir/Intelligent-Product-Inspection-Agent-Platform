from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import safe_decode_token
from app.core.exceptions import ForbiddenError
from app.schemas.user import CurrentUser
from infra.database.session import get_session


async def get_db() -> AsyncSession:
    async with get_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_current_user(authorization: str = Header(default="")) -> CurrentUser:
    if not authorization.startswith("Bearer "):
        raise ForbiddenError("missing bearer token")
    token = authorization.split(" ", 1)[1]
    payload = safe_decode_token(token)
    return CurrentUser(
        user_id=payload.get("sub", ""),
        org_id=payload.get("org_id", ""),
        role=payload.get("role", ""),
    )
