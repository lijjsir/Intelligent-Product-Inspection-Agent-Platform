from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import TypeVar

from infra.database.session import reset_async_engine_pool

T = TypeVar("T")


async def _run_with_fresh_database_pool(awaitable: Awaitable[T]) -> T:
    await reset_async_engine_pool(close=False)
    try:
        return await awaitable
    finally:
        await reset_async_engine_pool(close=True)


def run_celery_async(awaitable: Awaitable[T]) -> T:
    return asyncio.run(_run_with_fresh_database_pool(awaitable))
