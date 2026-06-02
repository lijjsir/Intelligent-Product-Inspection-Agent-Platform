from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine

from app.core.config import settings


def create_engine_rw() -> AsyncEngine:
    return create_async_engine(
        settings.db_url,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=max(1, int(settings.db_pool_size or 10)),
        max_overflow=max(0, int(settings.db_max_overflow or 20)),
        pool_timeout=max(1, int(settings.db_pool_timeout_sec or 10)),
    )


def create_engine_ro() -> AsyncEngine:
    return create_async_engine(
        settings.db_replica_url,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=max(1, int(settings.db_pool_size or 10)),
        max_overflow=max(0, int(settings.db_max_overflow or 20)),
        pool_timeout=max(1, int(settings.db_pool_timeout_sec or 10)),
    )
