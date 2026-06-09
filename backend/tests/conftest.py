from pathlib import Path
import sys
import gc

import pytest
import pytest_asyncio

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from infra.database.session import reset_async_engine_pool
from app.core.config import settings


@pytest.fixture(autouse=True)
def default_paper_review_enabled_for_tests():
    previous = settings.paper_review_enabled
    settings.paper_review_enabled = True
    yield
    settings.paper_review_enabled = previous


@pytest_asyncio.fixture(autouse=True)
async def dispose_async_engine_pool_after_async_test():
    yield
    gc.collect()
    await reset_async_engine_pool()
    gc.collect()
