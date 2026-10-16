from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.models.task import InspectionTask
from app.schemas.quality_risk import ProductCategoryCreate, ProductCreate, ProductionBatchCreate, QualityEventCreate
from app.schemas.supervision import EnterpriseData
from app.schemas.supervision import RecordCreate
from app.schemas.user import CurrentUser
from app.services.quality_risk_service import QualityRiskService
from app.services.supervision_service import SupervisionService
from app.services.supervision_imports import preview, confirm
from app.services.task_service import TaskService
from test_quality_risk_v4 import domain, uid  # noqa: F401


async def product(service, name="通勤车"):
    category = await service.create_category(ProductCategoryCreate(name="电动自行车"))
    return await service.create_product(ProductCreate(category_id=category["id"], name=name))


@pytest.mark.asyncio
@pytest.mark.parametrize("initial_batch,expected", [
    (None, None),
    ({}, None),
    ({"original_batch_no": "000001"}, ("000001", None)),
    ({"production_date": "2026-10-04"}, (None, date(2026, 10, 4))),
    ({"original_batch_no": "000001", "production_date": "2026-10-04"}, ("000001", date(2026, 10, 4))),
])
async def test_product_creation_registers_only_a_known_initial_batch(domain, initial_batch, expected):
    _, service = domain
    admin = service("admin")
    category = await admin.create_category(ProductCategoryCreate(name="电线电缆"))
    created = await admin.create_product(ProductCreate(category_id=category["id"], name="初始批次电缆",
        initial_batch=initial_batch))
    batches = await admin.product_batches(created["id"])
    if expected is None:
        assert batches == []
    else:
        assert len(batches) == 1
        assert (batches[0]["original_batch_no"], batches[0]["production_date"]) == expected
        assert batches[0]["product_id"] == created["id"] and batches[0]["display_no"].startswith("PC-")


@pytest.mark.asyncio
async def test_failed_initial_batch_rolls_back_product_identifiers_and_batch(domain, monkeypatch):
    from sqlalchemy import select
    from app.models.business_number import BusinessIdentifier, BusinessNumberSequence
    from app.models.quality_risk import ProductIdentifier, QualityProduct, QualityProductionBatch

    db, service = domain
    admin = service("admin")
    category = await admin.create_category(ProductCategoryCreate(name="电线电缆"))
    save_batch = admin.save_production_batch

    async def save_then_fail(product_id, payload):
        await save_batch(product_id, payload)
        raise ValidationError("模拟批次保存失败")

    monkeypatch.setattr(admin, "save_production_batch", save_then_fail)
    with pytest.raises(ValidationError, match="模拟批次保存失败"):
        await admin.create_product(ProductCreate(category_id=category["id"], name="失败电缆",
            identifiers=[{"identifier_type": "source_product_id", "identifier_value": "failure-sample"}],
            initial_batch={"original_batch_no": "000001"}))
    assert not await db.scalar(select(QualityProduct.id).where(QualityProduct.name == "失败电缆"))
    assert not await db.scalar(select(ProductIdentifier.id).where(ProductIdentifier.identifier_value == "failure-sample"))
    assert not await db.scalar(select(QualityProductionBatch.id).where(QualityProductionBatch.original_batch_no == "000001"))
    assert not await db.scalar(select(BusinessIdentifier.entity_id).where(BusinessIdentifier.org_id == admin.org_id,
        BusinessIdentifier.entity_kind.in_(["QualityProduct", "QualityProductionBatch"])))
    assert not await db.scalar(select(BusinessNumberSequence.prefix).where(BusinessNumberSequence.org_id == admin.org_id,
        BusinessNumberSequence.prefix.in_(["CP", "PC"])))


@pytest.mark.asyncio
async def test_catalog_batches_belong_to_their_product_and_exclude_deleted_and_other_tenants(domain):
    from app.models.quality_risk import QualityProductionBatch
    from app.schemas.quality_risk import ProductCatalogResponse

    db, service = domain
    admin = service("admin")
    first = await product(admin, "第一产品")
    second = await admin.create_product(ProductCreate(category_id=first["category_id"], name="第二产品"))
    batch_a = await admin.save_production_batch(first["id"], ProductionBatchCreate(original_batch_no="B001"))
    batch_b = await admin.save_production_batch(second["id"], ProductionBatchCreate(original_batch_no="B001"))
    deleted = await admin.save_production_batch(first["id"], ProductionBatchCreate(original_batch_no="B-REMOVED"))
    await admin.delete_foundation("batch", deleted["id"], first["id"])
    db.add(QualityProductionBatch(org_id=uid(), product_id=first["id"], original_batch_no="OTHER-TENANT", created_by=admin.actor))
    await db.flush()
    catalog = ProductCatalogResponse.model_validate(await admin.product_catalog(with_batches=True))
    products = {item.id: item for item in catalog.products}
    assert [batch.id for batch in products[first["id"]].batches] == [batch_a["id"]]
    assert [batch.id for batch in products[second["id"]].batches] == [batch_b["id"]]
    assert products[first["id"]].batches[0].display_no == batch_a["display_no"]
    assert "batches" not in (await service("user").product_catalog())["products"][0]


@pytest.mark.asyncio
async def test_batch_numbers_are_not_supplier_numbers_and_date_is_not_identity(domain):
    _, service = domain
    admin = service("admin")
    p = await product(admin)
    payload = ProductionBatchCreate(production_date=date(2026, 10, 1))
    first = await admin.save_production_batch(p["id"], payload)
    second = await admin.save_production_batch(p["id"], payload)
    assert first["original_batch_no"] is None
    assert first["display_no"].startswith("PC-")
    assert first["id"] != second["id"] and first["display_no"] != second["display_no"]
    numbered = await admin.save_production_batch(p["id"], ProductionBatchCreate(original_batch_no="00001"))
    assert numbered["original_batch_no"] == "00001"
    with pytest.raises(ConflictError):
        await admin.save_production_batch(p["id"], ProductionBatchCreate(original_batch_no="00001"))
    updated = await admin.save_production_batch(p["id"], ProductionBatchCreate(original_batch_no="00001", production_date=date(2026, 10, 2)), numbered["id"])
    assert updated["display_no"] == numbered["display_no"]


@pytest.mark.asyncio
async def test_batch_reads_writes_and_associations_are_scoped(domain):
    db, service = domain
    admin = service("admin")
    p = await product(admin)
    batch = await admin.save_production_batch(p["id"], ProductionBatchCreate())
    assert (await service("user").product_batches(p["id"]))[0]["id"] == batch["id"]
    with pytest.raises(ForbiddenError):
        await service("expert").save_production_batch(p["id"], ProductionBatchCreate())
    other_product = await admin.create_product(ProductCreate(category_id=p["category_id"], name="其他车型"))
    with pytest.raises(NotFoundError):
        await admin.production_batch(other_product["id"], batch["id"])
    foreign = QualityRiskService(db, CurrentUser(user_id=uid(), org_id=uid(), role="admin"))
    with pytest.raises(NotFoundError):
        await foreign.product_batches(p["id"])
    with pytest.raises(NotFoundError):
        await service("user").create_event(QualityEventCreate(record_type="inspection_report", content={"raw_text": "报告"},
            product_ref={"product_id": other_product["id"], "production_batch_id": batch["id"]}))


@pytest.mark.asyncio
async def test_unknown_batch_links_only_explicit_references_not_same_date(domain):
    db, service = domain
    admin = service("admin")
    p = await product(admin)
    first = await admin.save_production_batch(p["id"], ProductionBatchCreate())
    second = await admin.save_production_batch(p["id"], ProductionBatchCreate())
    record = await service("user").create_event(QualityEventCreate(record_type="inspection_report", content={"raw_text": "批次报告"},
        product_ref={"product_id": p["id"], "production_batch_id": first["id"]}))
    db.add(InspectionTask(id=uid(), org_id=admin.org_id, created_by=admin.actor, product_id=p["id"], quality_product_id=p["id"],
        spec_code="TEST", image_urls=[], image_items=[], status="pending", meta_data={"quality_batch_id": first["id"]}))
    await db.flush()
    linked = await admin.product_links(p["id"], first["id"])
    assert [r["id"] for r in linked["records"]] == [record["id"]]
    assert len(linked["tasks"]) == 1 and linked["tasks"][0]["has_result"] is False
    assert await admin.product_links(p["id"], second["id"]) == {"records": [], "tasks": []}
    with pytest.raises(ForbiddenError):
        await service("user").product_links(p["id"])


@pytest.mark.asyncio
async def test_enterprise_import_needs_names_not_manual_codes_or_roles(domain):
    db, service = domain
    assert EnterpriseData().role is None
    svc = SupervisionService(db, service("admin").current)
    content = "企业名称,统一社会信用代码,详细地址\n甲公司,,重庆\n乙公司,,\n".encode("utf-8-sig")
    result = await preview(svc, "enterprises", "enterprises.csv", content, {})
    assert result["can_confirm"] and result["valid_count"] == 2
    assert all(row["code"] is None and row["data"]["role"] is None for row in result["rows"])
    outcome = await confirm(svc, "enterprises", result["preview_id"])
    assert outcome["accepted"] == 2
    first = await svc.get("enterprises", outcome["record_ids"][0])
    assert first.display_no.startswith("QY-")
    assert first.data["role"] is None
    assert await confirm(svc, "enterprises", result["preview_id"]) == outcome
    again = await preview(svc, "enterprises", "enterprises.csv", content, {})
    assert not again["can_confirm"] and len(again["errors"]) == 2


@pytest.mark.asyncio
async def test_manufacturer_reference_cannot_point_to_another_organization(domain):
    _, service = domain
    admin = service("admin")
    category = await admin.create_category(ProductCategoryCreate(name="电线电缆"))
    with pytest.raises(ValidationError):
        await admin.create_product(ProductCreate(category_id=category["id"], name="电缆", manufacturer_enterprise_id=uid()))


@pytest.mark.asyncio
async def test_task_stores_batch_reference_without_inventing_supplier_number(domain):
    db, service = domain
    admin = service("admin")
    p = await product(admin)
    batch = await admin.save_production_batch(p["id"], ProductionBatchCreate())
    svc = TaskService(db, admin.org_id)
    svc._standard_repo.get_active_by_spec_code = AsyncMock(return_value=None)
    svc._resolve_spec_from_standard = AsyncMock(return_value=SimpleNamespace(spec_code="TEST"))
    svc._repo.find_recent_image_hashes = AsyncMock(return_value=set())
    task = await svc.create_task(created_by=admin.actor, product_id="", spec_code="TEST", image_urls=["https://example.com/image.png"],
        priority=5, metadata=None, product_category_id=p["category_id"], quality_product_id=p["id"], quality_batch_id=batch["id"])
    assert task.meta_data["quality_batch_id"] == batch["id"]
    assert task.meta_data["quality_batch_display_no"] == batch["display_no"]
    assert task.meta_data["batch_no"] is None
    assert (await admin.product_links(p["id"], batch["id"]))["tasks"][0]["id"] == task.id
    another = await admin.create_product(ProductCreate(category_id=p["category_id"], name="其他车型"))
    with pytest.raises(ValidationError):
        await svc.create_task(created_by=admin.actor, product_id="", spec_code="TEST", image_urls=["https://example.com/other.png"],
            priority=5, metadata=None, quality_product_id=another["id"], quality_batch_id=batch["id"])


@pytest.mark.asyncio
async def test_delete_unused_batch_product_category_and_recreate_identity(domain):
    _, service = domain
    admin = service("admin")
    p = await product(admin)
    batch = await admin.save_production_batch(p["id"], ProductionBatchCreate(original_batch_no="0001"))
    with pytest.raises(ConflictError, match="产品批次"):
        await admin.delete_foundation("product", p["id"])
    with pytest.raises(ConflictError, match="产品"):
        await admin.delete_foundation("category", p["category_id"])
    await admin.delete_foundation("batch", batch["id"], p["id"])
    assert await admin.product_batches(p["id"]) == []
    recreated = await admin.save_production_batch(p["id"], ProductionBatchCreate(original_batch_no="0001"))
    assert recreated["display_no"] != batch["display_no"]
    await admin.delete_foundation("batch", recreated["id"], p["id"])
    await admin.delete_foundation("product", p["id"])
    await admin.delete_foundation("category", p["category_id"])
    assert await admin.product_catalog() == {"products": [], "categories": []}


@pytest.mark.asyncio
async def test_deletion_rejects_raw_material_and_task_references(domain):
    db, service = domain
    admin = service("admin")
    p = await product(admin)
    batch = await admin.save_production_batch(p["id"], ProductionBatchCreate(original_batch_no="0002"))
    await service("user").create_event(QualityEventCreate(record_type="inspection_report", content={"raw_text": "保留原始证据"},
        product_ref={"product_id": p["id"], "production_batch_ref": "0002"}))
    with pytest.raises(ConflictError, match="业务资料"):
        await admin.delete_foundation("batch", batch["id"], p["id"])
    with pytest.raises(ConflictError, match="业务资料"):
        await admin.delete_foundation("product", p["id"])
    second = await admin.create_product(ProductCreate(category_id=p["category_id"], name="任务引用车型"))
    db.add(InspectionTask(id=uid(), org_id=admin.org_id, created_by=admin.actor, product_id=second["id"], quality_product_id=second["id"],
        spec_code="TEST", image_urls=[], image_items=[], status="done", meta_data={}))
    await db.flush()
    with pytest.raises(ConflictError, match="检测任务"):
        await admin.delete_foundation("product", second["id"])


@pytest.mark.asyncio
async def test_enterprise_deletion_is_admin_only_tenant_scoped_and_checks_products(domain):
    db, service = domain
    admin = service("admin")
    enterprise = await SupervisionService(db, admin.current).create("enterprises", RecordCreate(name="测试制造商", data={}))
    with pytest.raises(ForbiddenError):
        await service("expert").delete_foundation("enterprise", enterprise["id"])
    foreign = QualityRiskService(db, CurrentUser(user_id=uid(), org_id=uid(), role="admin"))
    with pytest.raises(NotFoundError):
        await foreign.delete_foundation("enterprise", enterprise["id"])
    p = await product(admin)
    from app.schemas.quality_risk import ProductUpdate
    await admin.update_product(p["id"], ProductUpdate(manufacturer_enterprise_id=enterprise["id"]))
    with pytest.raises(ConflictError, match="产品"):
        await admin.delete_foundation("enterprise", enterprise["id"])
    await admin.delete_foundation("product", p["id"])
    await admin.delete_foundation("enterprise", enterprise["id"])
    with pytest.raises(NotFoundError):
        await SupervisionService(db, admin.current).get("enterprises", enterprise["id"])


@pytest.mark.asyncio
async def test_deletion_cleans_product_identifiers_keeps_audit_and_number_history(domain):
    db, service = domain
    admin = service("admin")
    category = await admin.create_category(ProductCategoryCreate(name="电线电缆"))
    payload = ProductCreate(category_id=category["id"], name="电缆", model="A1", identifiers=[{"identifier_type": "barcode", "identifier_value": "000123"}])
    first = await admin.create_product(payload)
    await admin.delete_foundation("product", first["id"])
    again = await admin.create_product(payload)
    assert again["display_no"] != first["display_no"] and again["identifiers"][0]["identifier_value"] == "000123"
    from sqlalchemy import select
    from app.models.audit import AuditOutbox
    from app.models.business_number import BusinessIdentifier
    audit = await db.scalar(select(AuditOutbox).where(AuditOutbox.payload["resource_id"].as_string() == first["id"]))
    assert audit.payload["action"] == "delete" and audit.payload["snapshot"]["model"] == "A1"
    assert await db.scalar(select(BusinessIdentifier).where(BusinessIdentifier.entity_id == first["id"]))
