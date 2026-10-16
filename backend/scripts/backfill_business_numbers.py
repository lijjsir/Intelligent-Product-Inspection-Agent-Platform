"""Add readable aliases without changing old IDs/codes. Dry-run unless --apply."""
import argparse
import asyncio
import json

from sqlalchemy import select

from app.models import (
    InspectionTask,
    PhysicalSample,
    ProductCategory,
    QualityDataSource,
    QualityIngestionJob,
    QualityProduct,
    QualityRiskCase,
    QualitySourceRecord,
    RiskPolicy,
    StandardExecutionRule,
)
from app.models.supervision import SupervisionRecord
from app.services.business_number_service import PREFIXES, BusinessNumberService
from infra.database.session import get_session, reset_async_engine_pool


async def run(apply):
    summary = {}
    for model in [ProductCategory, QualityProduct, QualityDataSource, QualitySourceRecord, QualityIngestionJob,
                  QualityRiskCase, RiskPolicy, StandardExecutionRule, PhysicalSample, InspectionTask, SupervisionRecord]:
        cursor = None
        count = 0
        while True:
            async with get_session() as db:
                statement = select(model).order_by(model.id).limit(200)
                if cursor:
                    statement = statement.where(model.id > cursor)
                rows = list(await db.scalars(statement))
                if not rows:
                    break
                for row in rows:
                    kind = row.kind if model is SupervisionRecord else model.__name__
                    if kind not in PREFIXES:
                        continue
                    numbers = BusinessNumberService(db)
                    await numbers.attach([row], kind)
                    if row.display_no is None:
                        count += 1
                        if apply:
                            await numbers.assign(row, kind)
                if apply:
                    await db.commit()
                cursor = rows[-1].id
        summary[model.__name__] = count
    await reset_async_engine_pool()
    print(json.dumps({"mode": "applied" if apply else "preview", "new_aliases": summary}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    asyncio.run(run(parser.parse_args().apply))
