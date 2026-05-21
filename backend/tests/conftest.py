from pathlib import Path
import sys
import gc

import pytest_asyncio

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from infra.database.session import reset_async_engine_pool


@pytest_asyncio.fixture(autouse=True)
async def dispose_async_engine_pool_after_async_test():
    yield
    gc.collect()
    await reset_async_engine_pool()
    gc.collect()
