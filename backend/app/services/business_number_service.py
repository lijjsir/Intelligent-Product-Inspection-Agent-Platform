from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.models.business_number import BusinessIdentifier, BusinessNumberSequence

PREFIXES = {
    "QualitySourceRecord": "ZL", "QualityIngestionJob": "DR", "InspectionTask": "JC",
    "QualityProduct": "CP", "ProductCategory": "FL", "QualityDataSource": "LY",
    "QualityRiskCase": "FX", "RiskPolicy": "GZ", "StandardExecutionRule": "GZ",
    "PhysicalSample": "YP", "ProductBatch": "PC", "QualityProductionBatch": "PC",
    "enterprises": "QY", "sampling-plans": "CJ", "samples": "YP",
    "inspection-sessions": "JC", "devices": "SB", "exposures": "TJ",
}


class BusinessNumberService:
    """Allocate and register numbers inside the caller's business transaction."""

    def __init__(self, db):
        self.db = db

    async def allocate(self, org_id: str, prefix: str) -> str:
        if prefix not in set(PREFIXES.values()):
            raise ValidationError("未知业务编号类型")
        day = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        values = {"org_id": org_id, "prefix": prefix, "business_date": day, "last_value": 1}
        dialect = self.db.get_bind().dialect.name
        if dialect == "mysql":
            from sqlalchemy.dialects.mysql import insert
            statement = insert(BusinessNumberSequence).values(**values)
            statement = statement.on_duplicate_key_update(
                last_value=BusinessNumberSequence.last_value + 1,
            )
        elif dialect == "sqlite":
            from sqlalchemy.dialects.sqlite import insert
            statement = insert(BusinessNumberSequence).values(**values)
            statement = statement.on_conflict_do_update(
                index_elements=["org_id", "prefix", "business_date"],
                set_={"last_value": BusinessNumberSequence.last_value + 1},
            )
        else:
            raise ValidationError("当前数据库不支持业务编号分配")
        await self.db.execute(statement)
        number = await self.db.scalar(select(BusinessNumberSequence.last_value).where(
            BusinessNumberSequence.org_id == org_id,
            BusinessNumberSequence.prefix == prefix,
            BusinessNumberSequence.business_date == day,
        ).with_for_update())
        if not number or number > 99_999_999:
            raise ValidationError("当日业务编号容量已达上限")
        return f"{prefix}-{day:%Y%m%d}-{number:08d}"

    async def assign(self, row, kind: str | None = None, reserved: str | None = None) -> str | None:
        kind = kind or type(row).__name__
        if kind not in PREFIXES:
            return None
        # Only persistent database sessions allocate identifiers.
        if not isinstance(self.db, AsyncSession):
            return None
        identifier = await self.db.get(BusinessIdentifier, (str(row.org_id), kind, str(row.id)))
        if identifier is None:
            number = reserved or await self.allocate(str(row.org_id), PREFIXES[kind])
            values = {"org_id": row.org_id, "entity_kind": kind, "entity_id": row.id, "display_no": number}
            if self.db.get_bind().dialect.name == "mysql":
                from sqlalchemy.dialects.mysql import insert
                statement = insert(BusinessIdentifier).values(**values)
                statement = statement.on_duplicate_key_update(display_no=BusinessIdentifier.display_no)
            else:
                from sqlalchemy.dialects.sqlite import insert
                statement = insert(BusinessIdentifier).values(**values).on_conflict_do_nothing(index_elements=["org_id", "entity_kind", "entity_id"])
            await self.db.execute(statement)
            identifier = await self.db.scalar(select(BusinessIdentifier).where(
                BusinessIdentifier.org_id == row.org_id, BusinessIdentifier.entity_kind == kind,
                BusinessIdentifier.entity_id == row.id,
            ).with_for_update().execution_options(populate_existing=True))
        row.display_no = identifier.display_no
        return identifier.display_no

    async def attach(self, rows, kind: str | None = None) -> None:
        rows = list(rows)
        if not rows or not isinstance(self.db, AsyncSession):
            return
        kind = kind or type(rows[0]).__name__
        if kind not in PREFIXES:
            return
        identifiers = await self.db.scalars(select(BusinessIdentifier).where(
            BusinessIdentifier.entity_kind == kind,
            BusinessIdentifier.entity_id.in_([row.id for row in rows]),
            BusinessIdentifier.org_id.in_([row.org_id for row in rows]),
        ).with_for_update(read=True))
        by_id = {(str(item.org_id), str(item.entity_id)): item.display_no for item in identifiers}
        for row in rows:
            row.display_no = by_id.get((str(row.org_id), str(row.id)))
