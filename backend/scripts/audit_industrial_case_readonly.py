"""Inventory suitable actors and existing case assets; does not modify records."""
import asyncio, argparse, json
from pathlib import Path
from sqlalchemy import select
from infra.database.session import get_session, reset_async_engine_pool
from app.models.user import User
from app.models.quality_risk import ProductCategory, QualityProduct
from app.models.inspection_standard_library import InspectionStandardLibrary, StandardDocument


async def main(org_id, output):
    result = {'read_only': True, 'org_id': org_id}
    specs = [(User, 'users', ['id','role','username']),
             (InspectionStandardLibrary, 'libraries', ['id','name','product_category','spec_code']),
             (StandardDocument, 'documents', ['id','file_name','publication_status','current_revision_id']),
             (ProductCategory, 'categories', ['id','name']), (QualityProduct,'products',['id','name','model'])]
    try:
        async with get_session() as db:
            for model, key, fields in specs:
                q = select(model).where(model.org_id == org_id)
                if hasattr(model, 'deleted_at'): q = q.where(model.deleted_at.is_(None))
                if hasattr(model, 'is_active'): q = q.where(model.is_active.is_(True))
                result[key] = [{f: getattr(r,f) for f in fields} for r in (await db.scalars(q)).all()]
    finally:
        await reset_async_engine_pool()
    target=Path(output); target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--org-id',required=True);p.add_argument('--output',required=True)
    args=p.parse_args();asyncio.run(main(args.org_id,args.output))
