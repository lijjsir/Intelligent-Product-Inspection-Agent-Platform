"""Provision only the guarded, dedicated local acceptance database."""
import asyncio
import json
import argparse

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.quality_demo import demo_schema_metadata, validate_demo_settings
from infra.database.session import _engine
from app.services.object_storage import build_object_storage
from app.services.quality_demo_seed import seed_quality_demo


async def initialize(market=False):
    if not settings.quality_demo_enabled:
        raise RuntimeError("Demo initialization is disabled in this process")
    validate_demo_settings(settings)
    async with _engine.connect() as connection:
        acquired = await connection.scalar(text("SELECT GET_LOCK('piap_quality_demo.bootstrap', 20)"))
        if acquired != 1:
            raise RuntimeError("Another demo initialization is running")
        try:
            names = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
            if names and "quality_demo_environment" not in names:
                raise RuntimeError("Nonempty database has no demo ownership marker; refusing to modify it")
            if "quality_demo_environment" in names:
                marker = await connection.scalar(text("SELECT marker FROM quality_demo_environment LIMIT 1"))
                if marker != "piap-quality-demo-v1":
                    raise RuntimeError("Demo ownership marker does not match")
            await connection.execute(text("CREATE TABLE IF NOT EXISTS quality_demo_environment (marker VARCHAR(64) PRIMARY KEY)"))
            await connection.execute(text("INSERT IGNORE INTO quality_demo_environment(marker) VALUES ('piap-quality-demo-v1')"))
            await connection.commit()
            # ORM timestamps use CURRENT_TIMESTAMP(3); MySQL requires matching
            # fractional precision on their DATETIME columns. Do not change the
            # shared ORM metadata or import legacy migration seed data.
            metadata = demo_schema_metadata()
            await connection.run_sync(metadata.create_all)
            await connection.commit()
            async with AsyncSession(bind=connection, expire_on_commit=False) as db:
                result = await seed_quality_demo(db, build_object_storage())
                if market:
                    from app.services.quality_demo_market_seed import seed_market_demo
                    result["market"] = await seed_market_demo(db)
                await db.commit()
            print(json.dumps(result, ensure_ascii=False))
        finally:
            await connection.execute(text("SELECT RELEASE_LOCK('piap_quality_demo.bootstrap')"))
            await connection.commit()


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", action="store_true", help="Add the fixed stage-three simulated series once")
    args = parser.parse_args()
    try:
        await initialize(market=args.market)
    finally:
        await _engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
