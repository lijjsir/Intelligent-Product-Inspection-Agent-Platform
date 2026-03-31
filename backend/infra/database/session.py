from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from infra.database.engine import create_engine_rw

_engine = create_engine_rw()
_async_session_factory = async_sessionmaker(_engine, expire_on_commit=False)


def create_session() -> AsyncSession:
    """Create a new async session. Caller is responsible for closing it."""
    return _async_session_factory()


@asynccontextmanager
async def get_session() -> AsyncSession:
    session: AsyncSession = _async_session_factory()
    try:
        yield session
    finally:
        await session.close()
