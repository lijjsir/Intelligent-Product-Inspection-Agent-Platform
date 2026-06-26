from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime import utcnow
from app.models.product import ProductBatch, ProductLine, ProductSku


class ProductMasterRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_lines(self, org_id: str, *, include_inactive: bool = True) -> list[ProductLine]:
        stmt = select(ProductLine).where(ProductLine.org_id == org_id, ProductLine.deleted_at.is_(None))
        if not include_inactive:
            stmt = stmt.where(ProductLine.is_active.is_(True))
        result = await self._session.execute(stmt.order_by(ProductLine.code.asc(), ProductLine.created_at.asc()))
        return list(result.scalars().all())

    async def list_skus(self, org_id: str, *, include_inactive: bool = True) -> list[ProductSku]:
        stmt = select(ProductSku).where(ProductSku.org_id == org_id, ProductSku.deleted_at.is_(None))
        if not include_inactive:
            stmt = stmt.where(ProductSku.is_active.is_(True))
        result = await self._session.execute(stmt.order_by(ProductSku.code.asc(), ProductSku.created_at.asc()))
        return list(result.scalars().all())

    async def list_batches(self, org_id: str, *, include_inactive: bool = True) -> list[ProductBatch]:
        stmt = select(ProductBatch).where(ProductBatch.org_id == org_id, ProductBatch.deleted_at.is_(None))
        if not include_inactive:
            stmt = stmt.where(ProductBatch.is_active.is_(True))
        result = await self._session.execute(stmt.order_by(ProductBatch.batch_no.asc(), ProductBatch.created_at.asc()))
        return list(result.scalars().all())

    async def get_line(self, org_id: str, line_id: str) -> ProductLine | None:
        result = await self._session.execute(
            select(ProductLine).where(
                ProductLine.org_id == org_id,
                ProductLine.id == line_id,
                ProductLine.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_sku(self, org_id: str, sku_id: str) -> ProductSku | None:
        result = await self._session.execute(
            select(ProductSku).where(
                ProductSku.org_id == org_id,
                ProductSku.id == sku_id,
                ProductSku.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_batch(self, org_id: str, batch_id: str) -> ProductBatch | None:
        result = await self._session.execute(
            select(ProductBatch).where(
                ProductBatch.org_id == org_id,
                ProductBatch.id == batch_id,
                ProductBatch.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_line_by_code(self, org_id: str, code: str) -> ProductLine | None:
        result = await self._session.execute(
            select(ProductLine).where(
                ProductLine.org_id == org_id,
                ProductLine.code == code,
                ProductLine.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_sku_by_code(self, org_id: str, code: str) -> ProductSku | None:
        result = await self._session.execute(
            select(ProductSku).where(
                ProductSku.org_id == org_id,
                ProductSku.code == code,
                ProductSku.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_batch_by_sku_and_no(self, org_id: str, sku_id: str, batch_no: str) -> ProductBatch | None:
        result = await self._session.execute(
            select(ProductBatch).where(
                ProductBatch.org_id == org_id,
                ProductBatch.product_sku_id == sku_id,
                ProductBatch.batch_no == batch_no,
                ProductBatch.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def create_line(self, line: ProductLine) -> ProductLine:
        self._session.add(line)
        await self._session.flush()
        await self._session.refresh(line, attribute_names=["created_at", "updated_at"])
        return line

    async def create_sku(self, sku: ProductSku) -> ProductSku:
        self._session.add(sku)
        await self._session.flush()
        await self._session.refresh(sku, attribute_names=["created_at", "updated_at"])
        return sku

    async def create_batch(self, batch: ProductBatch) -> ProductBatch:
        self._session.add(batch)
        await self._session.flush()
        await self._session.refresh(batch, attribute_names=["created_at", "updated_at"])
        return batch

    async def update(self, item, payload: dict):
        for key, value in payload.items():
            setattr(item, key, value)
        await self._session.flush()
        await self._session.refresh(item, attribute_names=["updated_at"])
        return item

    async def soft_delete(self, item) -> None:
        item.deleted_at = utcnow()
        await self._session.flush()
