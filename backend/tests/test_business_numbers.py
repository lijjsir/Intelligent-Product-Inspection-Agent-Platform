import asyncio
import re
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.exceptions import ValidationError
from app.models import Base
from app.models.business_number import BusinessNumberSequence
from app.services.business_number_service import BusinessNumberService


@pytest.mark.asyncio
async def test_transactional_concurrent_numbers_and_capacity(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'numbers.db'}", connect_args={"timeout": 30})
    async with engine.begin() as conn:
        await conn.run_sync(lambda connection: Base.metadata.create_all(connection, tables=[Base.metadata.tables["business_number_sequences"], Base.metadata.tables["business_identifiers"]]))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    org = str(uuid4())
    async def allocate():
        async with factory.begin() as db:
            return await BusinessNumberService(db).allocate(org, "JC")
    numbers = await asyncio.gather(*[allocate() for _ in range(30)])
    assert len(set(numbers)) == 30
    assert all(re.fullmatch(r"JC-\d{8}-\d{8}", number) and len(number) == 20 for number in numbers)
    assert sorted(int(x[-8:]) for x in numbers) == list(range(1, 31))
    day = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    async with factory.begin() as db:
        db.add(BusinessNumberSequence(org_id=org, prefix="DR", business_date=day, last_value=99_999_998))
    async with factory.begin() as db:
        assert (await BusinessNumberService(db).allocate(org, "DR")).endswith("99999999")
    with pytest.raises(ValidationError, match="上限"):
        async with factory.begin() as db:
            await BusinessNumberService(db).allocate(org, "DR")
    async with factory() as db:
        assert await db.scalar(select(BusinessNumberSequence.last_value).where(BusinessNumberSequence.prefix == "DR")) == 99_999_999
    await engine.dispose()
