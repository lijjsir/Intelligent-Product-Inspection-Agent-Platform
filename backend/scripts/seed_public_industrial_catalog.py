"""Add the user-requested four public industrial catalogue examples to the verified main workspace."""
import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from app.models import Organization, User
from app.models.quality_risk import QualityProduct
from app.models.supervision import SupervisionRecord
from app.schemas.quality_risk import ProductCategoryCreate, ProductCreate
from app.schemas.supervision import RecordCreate
from app.schemas.user import CurrentUser
from app.services.quality_risk_service import QualityRiskService
from app.services.supervision_service import SupervisionService
from infra.database.session import get_session, reset_async_engine_pool

INPUT = Path(__file__).resolve().parent / 'data/industrial_catalog_public_2026_10_04.json'
OUTPUT = Path('runtime/public_industrial_catalog_2026_10_04_result.json')


async def main(apply):
    data = json.loads(INPUT.read_text(encoding='utf-8'))
    org_id = data['org_id']
    try:
        async with get_session() as db:
            org = await db.get(Organization, org_id)
            assert org and org.slug == 'cqupt', '拒绝写入未核对的组织'
            actor = await db.scalar(select(User).where(User.org_id == org_id, User.username == 'admin', User.role == 'admin', User.is_active.is_(True)))
            assert actor, '指定管理员不存在'
            print(json.dumps({'workspace': org.name, 'categories': [item['category_name'] for item in data['items']],
                'products': [item['model'] for item in data['items']], 'enterprise': data['enterprise']['name'], 'apply': apply}, ensure_ascii=False))
            if not apply:
                return
            current = CurrentUser(user_id=actor.id, org_id=org_id, role='admin')
            svc, enterprise_svc = QualityRiskService(db, current), SupervisionService(db, current)
            existing = list(await db.scalars(select(SupervisionRecord).where(SupervisionRecord.org_id == org_id,
                SupervisionRecord.kind == 'enterprises', SupervisionRecord.name == data['enterprise']['name'])))
            if len(existing) > 1:
                raise RuntimeError('已有多条同名企业，未自动覆盖')
            if existing:
                enterprise = existing[0]
                assert enterprise.status == 'active' and enterprise.data.get('credit_code') == data['enterprise']['data']['credit_code'], '已有企业内容不同，未自动覆盖'
                enterprise_id = enterprise.id
                enterprise_created = False
            else:
                enterprise = await enterprise_svc.create('enterprises', RecordCreate(name=data['enterprise']['name'], data=data['enterprise']['data']))
                enterprise_id = enterprise['id']
                enterprise_created = True
            records = []
            for item in data['items']:
                category = await svc.create_category(ProductCategoryCreate(name=item['category_name'], classification_basis=item['classification_basis']))
                previous = await db.scalar(select(QualityProduct).where(QualityProduct.org_id == org_id,
                    QualityProduct.category_id == category['id'], QualityProduct.name == item['name'],
                    QualityProduct.brand == item['brand'], QualityProduct.model == item['model'],
                    QualityProduct.manufacturer_enterprise_id == enterprise_id, QualityProduct.deleted_at.is_(None)))
                if previous:
                    product = {'id': previous.id, 'name': previous.name, 'model': previous.model}
                    created = False
                else:
                    product = await svc.create_product(ProductCreate(category_id=category['id'], name=item['name'], brand=item['brand'],
                        model=item['model'], manufacturer_enterprise_id=enterprise_id, attributes=item['attributes'], identifiers=item['identifiers']))
                    created = True
                records.append({'category_id': category['id'], 'category_name': category['name'], 'product_id': product['id'],
                    'name': product['name'], 'model': product['model'], 'created': created})
            await db.commit()
        # Verify in a fresh transaction, as the UI will read the records.
        async with get_session() as verify:
            current = CurrentUser(user_id=actor.id, org_id=org_id, role='admin')
            catalogue = await QualityRiskService(verify, current).product_catalog()
            by_id = {row['id']: row for row in catalogue['products']}
            for row in records:
                saved = by_id[row['product_id']]
                assert saved['model'] == row['model'] and saved['manufacturer_enterprise_name'] == data['enterprise']['name']
                assert saved['brand'] == '正泰' and saved['display_no'] and saved['identifiers']
            company = await verify.get(SupervisionRecord, enterprise_id)
            assert company.name == data['enterprise']['name'] and company.data['credit_code'] == data['enterprise']['data']['credit_code']
            report = {'org_id': org_id, 'enterprise_id': enterprise_id, 'enterprise_name': company.name,
                'enterprise_created': enterprise_created, 'records': records, 'verified': True, 'source_file': str(INPUT)}
            OUTPUT.parent.mkdir(parents=True, exist_ok=True)
            OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(report, ensure_ascii=False))
    finally:
        await reset_async_engine_pool()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    asyncio.run(main(parser.parse_args().apply))
