import gc

import pytest_asyncio

from infra.database.session import reset_async_engine_pool


@pytest_asyncio.fixture(autouse=True)
async def dispose_async_engine_pool_after_async_test():
    yield
    gc.collect()
    await reset_async_engine_pool()
    gc.collect()
