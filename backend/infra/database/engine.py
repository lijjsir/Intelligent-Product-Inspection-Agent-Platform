from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine

from app.core.config import settings


def create_engine_rw() -> AsyncEngine:
    return create_async_engine(settings.db_url, pool_pre_ping=True, pool_recycle=1800)


def create_engine_ro() -> AsyncEngine:
    return create_async_engine(settings.db_replica_url, pool_pre_ping=True, pool_recycle=1800)
