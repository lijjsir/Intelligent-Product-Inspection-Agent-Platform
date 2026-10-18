"""Canonical references, immutable source content, traceability and safe retries."""
import io
import json
import hashlib
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI, UploadFile
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from test_quality_risk_v4 import domain  # noqa: F401
from app.api.v1.quality_risk import router, intake_service
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.models.quality_risk import ProductCategory, QualityProduct, QualityAttachment, QualityRiskCase, QualitySourceRecord
from app.models.supervision import SupervisionRecord
from app.schemas.quality_risk import ProductCategoryCreate, ProductCreate, QualityEventCreate, RecordObjectsUpdate, RiskCaseCreate, RiskAnalyzeRequest, RiskReviewRequest
from app.schemas.user import CurrentUser
from app.services.quality_risk_service import QualityRiskService


async def foundation(domain):
    db, service = domain
    admin = service("admin")
    category = await admin.create_category(ProductCategoryCreate(name="本组织产品类别"))
    product = await admin.create_product(ProductCreate(category_id=category["id"], name="产品A", model="MODEL-ABC"))
    company = SupervisionRecord(id=str(uuid4()), org_id=admin.org_id, code="ENT-A", name="企业档案A",
        kind="enterprises", status="active", version=1, created_by=admin.actor,
        data={"credit_code": "private-code", "address": "private-address"}, created_at=datetime.utcnow(), updated_at=datetime.utcnow())
    db.add(company)
    await db.flush()
    return category, product, company


@pytest.mark.asyncio
async def test_reference_options_are_lean_scoped_and_search_models(domain):
    db, service = domain
    category, product, company = await foundation(domain)
    foreign = SupervisionRecord(id=str(uuid4()), org_id=str(uuid4()), code="FOREIGN", name="不可泄漏企业",
        kind="enterprises", status="active", version=1, created_by=company.created_by, data={}, created_at=datetime.utcnow(), updated_at=datetime.utcnow())
    db.add(foreign); await db.flush()
    refs = await service("user").intake_references()
    assert refs["enterprises"] == [{"id": company.id, "name": company.name}]
    assert set(refs["products"][0]) == {"id", "name", "category_id", "brand", "model"}
    searched = await service("expert").intake_references("MODEL-ABC")
    assert searched["products"][0]["id"] == product["id"]
    assert searched["categories"][0]["id"] == category["id"]
    company.status = "archived"
    assert not (await service("expert").intake_references())["enterprises"]


@pytest.mark.asyncio
async def test_names_alone_never_confirm_identity_or_invent_time(domain):
    _, service = domain
    _, _, company = await foundation(domain)
    row = await service("user").create_event(QualityEventCreate(record_type="consumer_complaint",
        content={"text": "原话", "product_description": "产品A"}, enterprise_ref={"name": company.name}))
    context = await service("user").record_context(row["id"])
    assert context["record"]["occurred_at"] is None
    assert context["record"]["enterprise_ref"]["name"] == company.name
    assert all(item["status"] == "unlinked" for item in context["objects"].values())


@pytest.mark.asyncio
async def test_shared_objects_across_types_and_preserved_original_description(domain):
    _, service = domain
    category, product, company = await foundation(domain)
    ids = []
    for kind in ["consumer_complaint", "public_opinion", "inspection_report"]:
        row = await service("expert").create_event(QualityEventCreate(record_type=kind, content={"text": kind},
            enterprise_ref={"enterprise_id": company.id, "name": "原资料中的企业别称"},
            product_ref={"product_id": product["id"]}, origin_label="保留的原始出处"))
        ids.append(row["id"])
        context = await service("expert").record_context(row["id"])
        assert context["objects"]["enterprise"]["id"] == company.id
        assert context["objects"]["category"]["id"] == category["id"]
        assert context["objects"]["product"]["id"] == product["id"]
        assert context["record"]["enterprise_ref"]["name"] == "原资料中的企业别称"
    filtered = await service("expert").list_records(page=1, size=20, enterprise_id=company.id, product_id=product["id"])
    assert {item["id"] for item in filtered["items"]} == set(ids)


@pytest.mark.asyncio
async def test_binding_preserves_source_and_invalidates_old_risk_snapshot(domain):
    db, service = domain
    category, product, company = await foundation(domain)
    payload = QualityEventCreate(record_type="supervision_inspection", content={"text": "原始实测叙述", "risk_level": "high"},
        origin_label="原始出处", enterprise_ref={"name": "待核对企业"})
    row = await service("user").create_event(payload)
    case = await service("user").create_risk_case(RiskCaseCreate(title="待确认对象事项", scope_type="mixed", scope={"name": "原始范围"}, source_record_ids=[row["id"]]))
    assessment = await service("user").analyze_risk(case["id"], RiskAnalyzeRequest())
    await service("expert").review_risk(case["id"], RiskReviewRequest(decision="accept", comment="原版证据确认"))
    updated = await service("expert2").update_record_objects(row["id"], RecordObjectsUpdate(
        enterprise_id=company.id, product_id=product["id"], expected_version=0, reason="依据原件核对对象"))
    for key in ["id", "content", "content_hash", "occurred_at", "received_at", "attachment_ids"]:
        assert updated[key] == row[key]
    assert updated["enterprise_ref"]["name"] == "待核对企业"
    assert updated["provenance"]["origin_label"] == "原始出处"
    assert updated["provenance"]["object_binding_version"] == 1
    assert updated["provenance"]["object_binding_history"][0]["actor_id"] == service("expert2").actor
    assert updated["provenance"]["original_object_refs"]["enterprise_ref"] == row["enterprise_ref"]
    assert (await db.get(QualityRiskCase, case["id"])).status == "awaiting_evidence"
    old = await service("expert").get_assessment(assessment["id"])
    assert old["status"] == "accepted" and old["review_comment"] == "原版证据确认"
    assert old["effective_status"] == "needs_reassessment"
    assert (await service("user").create_event(payload))["duplicate"] is True
    assert await db.scalar(select(func.count()).select_from(QualitySourceRecord)) == 1
    same = await service("expert").update_record_objects(row["id"], RecordObjectsUpdate(enterprise_id=company.id,
        product_id=product["id"], category_id=category["id"], expected_version=1, reason="核对后无变化"))
    assert same["provenance"]["object_binding_version"] == 1
    with pytest.raises(ConflictError):
        await service("expert").update_record_objects(row["id"], RecordObjectsUpdate(expected_version=0, reason="过期页面"))
    assert (await service("expert").record_context(row["id"]))["related_cases"][0]["id"] == case["id"]


@pytest.mark.asyncio
async def test_deleted_inactive_foreign_and_mismatched_references_are_rejected(domain):
    db, service = domain
    category, product, company = await foundation(domain)
    other = await service("admin").create_category(ProductCategoryCreate(name="另一类别"))
    with pytest.raises(ValidationError):
        await service("user").create_event(QualityEventCreate(record_type="consumer_complaint", content={"text": "原文"},
            product_ref={"product_id": product["id"], "category_id": other["id"]}))
    company.status = "archived"; await db.flush()
    with pytest.raises(ValidationError):
        await service("expert").create_event(QualityEventCreate(record_type="consumer_complaint", content={"text": "原文"}, enterprise_ref={"enterprise_id": company.id}))
    (await db.get(ProductCategory, category["id"])).is_active = False; await db.flush()
    with pytest.raises(ValidationError):
        await service("user").create_event(QualityEventCreate(record_type="consumer_complaint", content={"text": "原文"}, product_ref={"product_id": product["id"]}))
    assert not (await service("expert").intake_references())["products"]
    with pytest.raises(NotFoundError):
        await service("user").create_event(QualityEventCreate(record_type="consumer_complaint", content={"text": "原文"}, product_ref={"product_id": str(uuid4())}))


@pytest.mark.asyncio
async def test_attachment_and_record_retries_are_idempotent_but_not_shared_between_private_owners(domain):
    db, service = domain
    class Storage:
        def __init__(self): self.writes = []
        def put_bytes(self, **data): self.writes.append(data); return {"bucket": data["bucket"], "object_key": data["object_key"]}
    store = Storage()
    owner = service("user"); owner.storage = store
    def upload(): return UploadFile(io.BytesIO(b"raw source bytes"), filename="report.txt")
    first = await owner.upload_attachment(upload())
    second = await owner.upload_attachment(upload())
    assert first["id"] == second["id"] and len(store.writes) == 1
    row = await owner.create_event(QualityEventCreate(record_type="inspection_report", attachment_ids=[first["id"]]))
    repeat = await owner.create_event(QualityEventCreate(record_type="inspection_report", attachment_ids=[second["id"]]))
    assert repeat["duplicate"] and repeat["id"] == row["id"]
    peer = QualityRiskService(db, CurrentUser(user_id=service("expert").actor, org_id=owner.org_id, role="user")); peer.storage = store
    other = await peer.upload_attachment(upload())
    assert other["id"] != first["id"]
    with pytest.raises(NotFoundError): await peer.accessible_attachment(first["id"])
    with pytest.raises(NotFoundError): await peer.record_context(row["id"])
    with pytest.raises(NotFoundError): await peer.update_record_objects(row["id"], RecordObjectsUpdate(expected_version=0, reason="不能修改他人资料"))
    (await db.get(QualityAttachment, first["id"])).deleted_at = datetime.utcnow(); await db.flush()
    assert (await owner.record_context(row["id"]))["unavailable_attachment_ids"] == [first["id"]]
    with pytest.raises(ConflictError): await owner.upload_attachment(upload())
    (await db.get(QualitySourceRecord, row["id"])).deleted_at = datetime.utcnow(); await db.flush()
    with pytest.raises(NotFoundError): await owner.record_context(row["id"])


@pytest.mark.asyncio
async def test_binding_api_contract_and_foreign_source_access(domain):
    db, service = domain
    _, product, company = await foundation(domain)
    row = await service("user").create_event(QualityEventCreate(record_type="consumer_complaint", content={"text": "原文"}))
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[intake_service] = lambda: service("expert")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/quality-data/reference-options")).status_code == 200
        response = await client.patch(f"/quality-data/records/{row['id']}/objects", json={"expected_version": 0,
            "product_id": product["id"], "enterprise_id": company.id, "reason": "核对关联"})
        assert response.status_code == 200, response.text
        context = (await client.get(f"/quality-data/records/{row['id']}/context")).json()["data"]
        assert context["objects"]["product"]["id"] == product["id"]
    foreign = QualityRiskService(db, CurrentUser(user_id=str(uuid4()), org_id=str(uuid4()), role="expert"))
    with pytest.raises(NotFoundError): await foreign.record_context(row["id"])
    with pytest.raises(NotFoundError): await foreign.update_record_objects(row["id"], RecordObjectsUpdate(expected_version=1, reason="跨组织"))
    with pytest.raises(ValidationError, match="系统记录"):
        await service("user").create_event(QualityEventCreate(record_type="consumer_complaint", content={"text": "原文"}, provenance={"object_binding_version": 99}))


@pytest.mark.asyncio
async def test_known_origin_reuses_the_same_record_across_manual_and_file_intake(domain):
    db, service = domain
    svc = service("expert")
    original = await svc.create_event(QualityEventCreate(record_type="consumer_complaint", origin_label="明确出处",
        external_record_id="EXT-001", content={"text": "原始投诉"}))
    rows = [{"record_type":"consumer_complaint", "origin_label":"明确出处", "external_record_id":"EXT-001", "text":"原始投诉"}]
    preview = await svc.preview_import(request_key="stage2-cross-transport", file=UploadFile(io.BytesIO(json.dumps(rows).encode()),filename="records.json"))
    result = await svc.confirm_import(preview["id"])
    assert result["created_count"] == 0 and result["duplicate_count"] == 1
    assert result["records"][0]["record_id"] == original["id"]
    assert await db.scalar(select(func.count()).select_from(QualitySourceRecord)) == 1


@pytest.mark.asyncio
async def test_unknown_origins_are_not_assumed_to_be_the_same_event(domain):
    db, service = domain
    svc = service("user")
    original = await svc.create_event(QualityEventCreate(record_type="consumer_complaint", content={"text":"相同原话"}))
    preview = await svc.preview_import(request_key="stage2-unknown-origin", record_type="consumer_complaint",
        file=UploadFile(io.BytesIO(b'[{"text":"'+"相同原话".encode()+b'"}]'),filename="unknown.json"))
    result = await svc.confirm_import(preview["id"])
    assert result["created_count"] == 1 and result["records"][0]["record_id"] != original["id"]


@pytest.mark.asyncio
async def test_legacy_foreign_object_references_never_reveal_foreign_names(domain):
    db, service = domain
    category, _, _ = await foundation(domain)
    product = QualityProduct(id=str(uuid4()), org_id=str(uuid4()), category_id=category["id"], name="不可泄漏的外组织产品", attributes={}, is_active=True)
    db.add(product); await db.flush()
    with pytest.raises(NotFoundError):
        await service("user").create_event(QualityEventCreate(record_type="consumer_complaint", content={"text":"原文"}, product_ref={"product_id":product.id}))
    row = await service("user").create_event(QualityEventCreate(record_type="consumer_complaint", content={"text":"历史记录"}))
    stored = await db.get(QualitySourceRecord,row["id"])
    stored.product_ref={"product_id":product.id}; await db.flush()
    context = await service("user").record_context(row["id"])
    assert context["objects"]["product"] == {"id":product.id,"name":None,"status":"unavailable"}
    assert product.id not in {item["id"] for item in (await service("user").intake_references())["products"]}


@pytest.mark.asyncio
async def test_assigned_reader_cannot_rebind_another_submitters_source(domain):
    _, service = domain
    row = await service("expert").create_event(QualityEventCreate(record_type="inspection_report",content={"text":"有明确提交人的原始资料"}))
    await service("expert").create_risk_case(RiskCaseCreate(title="受派事项",scope_type="mixed",scope={"name":"待核对"},
        assigned_to=service("user").actor,source_record_ids=[row["id"]]))
    assert (await service("user").record_context(row["id"]))["record"]["id"]==row["id"]
    with pytest.raises(ForbiddenError):
        await service("user").update_record_objects(row["id"],RecordObjectsUpdate(expected_version=0,reason="受派不代表可以修改他人资料"))


@pytest.mark.asyncio
async def test_revoked_legacy_attachment_is_not_recreated_with_a_new_id(domain):
    db, service = domain
    svc = service("user")
    legacy = QualityAttachment(id=str(uuid4()), org_id=svc.org_id, file_name="legacy.txt", mime_type="text/plain", size_bytes=3,
        sha256=hashlib.sha256(b"raw").hexdigest(), bucket="quality-data", object_key="legacy", uploaded_by=svc.actor, deleted_at=datetime.utcnow())
    db.add(legacy); await db.flush()
    with pytest.raises(ConflictError):
        await svc.upload_attachment(UploadFile(io.BytesIO(b"raw"),filename="legacy.txt"))
    assert await db.scalar(select(func.count()).select_from(QualityAttachment))==1


@pytest.mark.asyncio
async def test_retry_can_restore_missing_bytes_of_an_active_attachment(domain):
    _, service = domain
    class Storage:
        def __init__(self): self.files = {}
        def put_bytes(self, **data): self.files[data["object_key"]]=data["data"];return {"bucket":data["bucket"],"object_key":data["object_key"]}
        def object_exists(self, **data):return data["object_key"] in self.files
    svc=service("user");svc.storage=Storage()
    first=await svc.upload_attachment(UploadFile(io.BytesIO(b"raw"),filename="active.txt"))
    svc.storage.files.clear()
    second=await svc.upload_attachment(UploadFile(io.BytesIO(b"raw"),filename="active.txt"))
    assert first["id"]==second["id"] and list(svc.storage.files.values())==[b"raw"]
