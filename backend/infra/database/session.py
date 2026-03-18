from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from infra.database.engine import create_engine_rw

_engine = create_engine_rw()
_session_factory = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def get_session() -> AsyncSession:
    session: AsyncSession = _session_factory()
    try:
        yield session
    finally:
        await session.close()
