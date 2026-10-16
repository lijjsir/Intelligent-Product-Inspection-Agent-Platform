"""Register the user's local MVTec AD industrial test samples, without launching tasks."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from sqlalchemy import select

from app.models import Organization, User
from app.models.quality_risk import ProductCategory, ProductIdentifier, QualityProduct, QualityProductionBatch
from app.schemas.quality_risk import ProductCategoryCreate, ProductCreate
from app.schemas.user import CurrentUser
from app.services.inspection_standard_library_service import InspectionStandardLibraryService
from app.services.quality_risk_service import QualityRiskService
from infra.database.session import get_session, reset_async_engine_pool

INPUT = Path(__file__).resolve().parent / "data/mvtec_industrial_catalog_2026_10_04.json"
OUTPUT = Path("runtime/mvtec_industrial_catalog_2026_10_04_result.json")


def snapshot(catalogue):
    return hashlib.sha256(json.dumps(catalogue, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


async def main(apply):
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    org_id = data["org_id"]
    records = []
    try:
        async with get_session() as db:
            org = await db.get(Organization, org_id)
            assert org and org.slug == "cqupt", "指定工作组织不匹配"
            actor = await db.scalar(select(User).where(User.org_id == org_id, User.username == "admin",
                                                     User.role == "admin", User.is_active.is_(True)))
            assert actor, "指定管理员不存在"
            print(json.dumps({"workspace": org.name, "apply": apply,
                              "products": [item["name"] for item in data["items"]],
                              "excluded": data["excluded"], "tasks_will_be_created": False}, ensure_ascii=False))
            if not apply:
                return
            # The whole addition is a single transaction and uses the normal catalogue services.
            await db.scalar(select(Organization.id).where(Organization.id == org_id).with_for_update())
            current = CurrentUser(user_id=actor.id, org_id=org_id, role="admin")
            svc = QualityRiskService(db, current)
            before = await svc.product_catalog(include_inactive=True)
            previous_category_ids = {item["id"] for item in before["categories"]}
            previous_product_ids = {item["id"] for item in before["products"]}
            for item in data["items"]:
                existing_category = list(await db.scalars(select(ProductCategory).where(
                    ProductCategory.org_id == org_id, ProductCategory.name == item["category_name"],
                    ProductCategory.deleted_at.is_(None))))
                assert len(existing_category) <= 1, "类别存在歧义，未覆盖"
                if existing_category:
                    row = existing_category[0]
                    assert row.is_active, "同名类别未启用，未自动修改"
                    category = svc.category_response(row)
                    category_created = False
                else:
                    category = await svc.create_category(ProductCategoryCreate(
                        name=item["category_name"], classification_basis=item["classification_basis"],
                        description=item["category_description"]))
                    category_created = True
                identifier_value = item["identifiers"][0]["identifier_value"]
                matches = list(await db.scalars(select(QualityProduct).join(
                    ProductIdentifier, ProductIdentifier.product_id == QualityProduct.id).where(
                    QualityProduct.org_id == org_id, QualityProduct.deleted_at.is_(None),
                    ProductIdentifier.org_id == org_id, ProductIdentifier.deleted_at.is_(None),
                    ProductIdentifier.identifier_type == "source_product_id",
                    ProductIdentifier.identifier_value == identifier_value)))
                assert len(matches) <= 1, "来源标识存在歧义，未覆盖"
                if matches:
                    row = matches[0]
                    assert row.category_id == category["id"] and row.name == item["name"] and row.is_active
                    assert row.model is None and row.brand is None and row.manufacturer_enterprise_id is None
                    assert row.attributes == item["attributes"], "已有测试档案已改变，未覆盖"
                    product_id, product_created = row.id, False
                else:
                    product = await svc.create_product(ProductCreate(
                        category_id=category["id"], name=item["name"], attributes=item["attributes"],
                        identifiers=item["identifiers"]))
                    product_id, product_created = product["id"], True
                records.append({"dataset_category": item["folder"], "category_id": category["id"],
                                "category_name": category["name"], "category_created": category_created,
                                "product_id": product_id, "name": item["name"], "created": product_created})
            await db.commit()
        async with get_session() as verify:
            current = CurrentUser(user_id=actor.id, org_id=org_id, role="admin")
            catalogue = await QualityRiskService(verify, current).product_catalog(include_inactive=True)
            old_only = {"categories": [item for item in catalogue["categories"] if item["id"] in previous_category_ids],
                        "products": [item for item in catalogue["products"] if item["id"] in previous_product_ids]}
            assert snapshot(before) == snapshot(old_only), "原有档案在操作期间发生变化，需核对"
            by_id = {item["id"]: item for item in catalogue["products"]}
            categories = {item["id"]: item for item in catalogue["categories"]}
            for item in records:
                saved = by_id[item["product_id"]]
                assert saved["name"] == item["name"] and saved["category_id"] == item["category_id"]
                assert saved["display_no"] and categories[item["category_id"]]["display_no"]
                assert saved["brand"] is None and saved["model"] is None and saved["manufacturer_enterprise_id"] is None
                assert any(ref["identifier_value"] == f'mvtec-ad:{item["dataset_category"]}' for ref in saved["identifiers"])
                assert not await verify.scalar(select(QualityProductionBatch.id).where(
                    QualityProductionBatch.product_id == item["product_id"], QualityProductionBatch.deleted_at.is_(None)))
                item["display_no"] = saved["display_no"]
            standards = await InspectionStandardLibraryService(verify, org_id).list_items(size=200)
            report = {"org_id": org_id, "verified": True, "preserved_existing_catalogue": True,
                      "created_products": sum(item["created"] for item in records),
                      "created_categories": sum(item["category_created"] for item in records),
                      "records": records, "excluded": data["excluded"],
                      "available_standards": [{key: row.get(key) for key in (
                          "id", "name", "spec_code", "inspection_spec_id", "applicable_category_ids", "applicable_product_ids")}
                          for row in standards["items"]],
                      "standard_configuration_changed": False, "tasks_created": 0}
            OUTPUT.parent.mkdir(parents=True, exist_ok=True)
            OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(report, ensure_ascii=False))
    finally:
        await reset_async_engine_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    asyncio.run(main(parser.parse_args().apply))
