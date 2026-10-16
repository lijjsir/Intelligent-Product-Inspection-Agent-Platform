import asyncio
import json
from sqlalchemy import select, func
from app.models import Organization, User
from app.models.quality_risk import ProductCategory, QualityProduct
from app.models.supervision import SupervisionRecord
from infra.database.session import get_session, reset_async_engine_pool

ORG_ID = '26c1c3e4-658b-498d-aab7-39b194de478c'

async def main():
    try:
        async with get_session() as db:
            org = await db.get(Organization, ORG_ID)
            assert org, '指定工作组织不存在'
            print(json.dumps({'org': {'id': org.id, 'name': org.name, 'slug': org.slug}}, ensure_ascii=False))
            admins = list(await db.scalars(select(User).where(User.org_id == ORG_ID, User.role == 'admin', User.is_active.is_(True))))
            print(json.dumps({'admins': [{'id': u.id, 'username': u.username} for u in admins]}, ensure_ascii=False))
            for model, kind in [(ProductCategory, None), (QualityProduct, None), (SupervisionRecord, 'enterprises')]:
                stmt = select(model).where(model.org_id == ORG_ID)
                if kind:
                    stmt = stmt.where(SupervisionRecord.kind == kind)
                else:
                    stmt = stmt.where(model.deleted_at.is_(None))
                rows = list(await db.scalars(stmt))
                print(json.dumps({'table': model.__tablename__, 'rows': [{'id': r.id, 'name': r.name,
                    'model': getattr(r, 'model', None), 'brand': getattr(r, 'brand', None)} for r in rows]}, ensure_ascii=False))
    finally:
        await reset_async_engine_pool()

asyncio.run(main())
