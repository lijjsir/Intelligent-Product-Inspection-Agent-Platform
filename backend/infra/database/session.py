from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from infra.database.engine import create_engine_rw

_engine = create_engine_rw()
_async_session_factory = async_sessionmaker(_engine, expire_on_commit=False)


def create_session() -> AsyncSession:
    """Create a new async session. Caller is responsible for closing it."""
    return _async_session_factory()


async def reset_async_engine_pool(*, close: bool = True) -> None:
    """Reset pooled async DB connections.

    Celery tasks use asyncio.run per invocation. aiomysql connections are bound to
    the event loop where they were created, so worker tasks must not reuse pooled
    connections from a previous loop.
    """
    await _engine.dispose(close=close)


@asynccontextmanager
async def get_session() -> AsyncSession:
    session: AsyncSession = _async_session_factory()
    try:
        yield session
    finally:
        await session.close()
