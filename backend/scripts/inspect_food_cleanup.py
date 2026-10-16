import asyncio
import json

from sqlalchemy import String, or_, select
from app.models import Base
from app.models.quality_risk import ProductCategory
from app.models.business_number import BusinessIdentifier
from infra.database.session import get_session, reset_async_engine_pool

async def main():
    try:
        async with get_session() as db:
            rows = list(await db.scalars(select(ProductCategory).join(BusinessIdentifier,
                (BusinessIdentifier.entity_id == ProductCategory.id) & (BusinessIdentifier.org_id == ProductCategory.org_id)
                & (BusinessIdentifier.entity_kind == 'ProductCategory')).where(
                ProductCategory.name == '食品', BusinessIdentifier.display_no == 'FL-20261003-00000001')))
            print(json.dumps({'categories': [{'id': r.id, 'org_id': r.org_id, 'code': r.code, 'name': r.name} for r in rows]}, ensure_ascii=False))
            if len(rows) != 1:
                return
            category = rows[0]
            ids = {category.id}
            tokens = {category.id, category.code}
            for table in Base.metadata.sorted_tables:
                if 'org_id' not in table.c:
                    continue
                conditions = []
                for col in table.c:
                    if col.name in {'org_id', 'id', 'created_by', 'actor_id', 'user_id'}:
                        continue
                    if col.type.__class__.__name__ == 'UUIDBinary':
                        conditions.append(col.in_(ids))
                    elif col.type.__class__.__name__ in {'JSON', 'String', 'Text', 'LONGTEXT'}:
                        conditions.extend(col.cast(String).contains(token, autoescape=True) for token in tokens)
                if not conditions:
                    continue
                found = (await db.execute(select(table).where(table.c.org_id == category.org_id, or_(*conditions)).limit(30))).mappings().all()
                if found:
                    print(json.dumps({'table': table.name, 'rows': [{k: str(v) for k, v in r.items() if k in
                        {'id','task_id','result_id','record_id','status','name','title','product_id','quality_product_id','product_category_id','actor_role'}} for r in found]}, ensure_ascii=False))
    finally:
        await reset_async_engine_pool()

asyncio.run(main())
