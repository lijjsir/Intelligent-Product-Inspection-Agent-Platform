
# ruff: noqa: F811
import io
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import UploadFile
from openpyxl import Workbook
from test_quality_risk_v4 import domain  # noqa: F401 -- shared isolated SQLite fixture

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.schemas.quality_risk import ProductCategoryCreate, ProductCreate, QualityEventCreate
from app.schemas.user import CurrentUser
from app.services.quality_risk_service import QualityRiskService


def file(name, content):
    return UploadFile(io.BytesIO(content), filename=name)


@pytest.mark.asyncio
async def test_unknown_time_and_origin_accept_without_preconfigured_source(domain):
    _, service = domain
    row = await service("user").create_event(QualityEventCreate(record_type="consumer_complaint", content={"text": "续航降低"}))
    assert row["occurred_at"] is None
    assert row["normalization_status"] == "stored"
    assert row["display_no"].startswith("ZL-") and len(row["display_no"]) == 20
    assert row["authorization_scope"] == "private"
    assert row["provenance"].get("origin_label") is None


@pytest.mark.asyncio
async def test_import_preserves_refs_origins_and_counts_retries(domain):
    _, service = domain
    category = await service("admin").create_category(ProductCategoryCreate(name="电动自行车"))
    product = await service("admin").create_product(ProductCreate(category_id=category["id"], name="演示型号"))
    assert product["display_no"].startswith("CP-")
    rows = [{"record_type": "consumer_complaint", "text": "续航降低", "product_id": product["id"], "category_id": category["id"],
             "enterprise_name": "来源描述企业", "production_batch_ref": "000012", "origin_label": "出处A", "external_record_id": "001"}]
    content = json.dumps(rows).encode()
    svc = service("user")
    preview = await svc.preview_import(request_key="json-one", file=file("a.json", content), origin_label="共同出处")
    assert preview["error_count"] == 0
    assert preview["preview_rows"][0]["origin_label"] == "出处A"
    result = await svc.confirm_import(preview["id"])
    assert (result["created_count"], result["duplicate_count"], result["failed_count"]) == (1, 0, 0)
    assert await svc.confirm_import(preview["id"]) == result
    second = await svc.preview_import(request_key="json-two", file=file("b.json", content))
    second = await svc.confirm_import(second["id"])
    assert (second["created_count"], second["duplicate_count"]) == (0, 1)
    record = await svc.get_record(result["records"][0]["record_id"])
    assert record["product_ref"]["product_id"] == product["id"]
    assert record["product_ref"]["production_batch_ref"] == "000012"
    assert record["enterprise_ref"]["name"] == "来源描述企业"
    assert record["provenance"]["import_row"] == 1
    with pytest.raises(ConflictError):
        await svc.preview_import(request_key="json-one", file=file("a.json", b"[]"))


@pytest.mark.asyncio
async def test_chinese_csv_and_xlsx_share_validation_and_origin(domain):
    _, service = domain
    svc = service("user")
    csv = "原始内容,原始出处,生产批次\n投诉原话,甲来源,000123\n\n另一条原话,乙来源,000124\n".encode("utf-8-sig")
    preview = await svc.preview_import(request_key="cn-csv", file=file("a.csv", csv), record_type="consumer_complaint")
    assert preview["valid_count"] == 2 and preview["error_count"] == 0
    assert preview["preview_rows"][1]["provenance"]["import_row"] == 4
    workbook = Workbook()
    workbook.active.append(["原始内容", "原始出处", "生产批次"])
    workbook.active.append(["投诉原话", "甲来源", "000123"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    xlsx = await svc.preview_import(request_key="cn-xlsx", file=file("a.xlsx", buffer.getvalue()), record_type="consumer_complaint")
    assert xlsx["preview_rows"][0]["product_ref"]["production_batch_ref"] == "000123"
    await svc.confirm_import(preview["id"])
    result = await svc.confirm_import(xlsx["id"])
    assert result["duplicate_count"] == 1


@pytest.mark.asyncio
async def test_errors_cancel_and_overflow_cannot_silently_confirm(domain):
    _, service = domain
    svc = service("user")
    content = json.dumps([{"text": "原始材料", "product_id": str(uuid4())}]).encode()
    preview = await svc.preview_import(request_key="bad-ref", file=file("a.json", content), record_type="consumer_complaint")
    assert preview["error_count"] == 1
    with pytest.raises(ConflictError):
        await svc.confirm_import(preview["id"])
    await svc.cancel_import(preview["id"])
    with pytest.raises(ConflictError):
        await svc.confirm_import(preview["id"])
    too_many = json.dumps([{"text": "原文"}] * 5001).encode()
    with pytest.raises(ValidationError, match="5000"):
        await svc.preview_import(request_key="too-many", file=file("a.json", too_many), record_type="consumer_complaint")


@pytest.mark.asyncio
async def test_peer_cannot_read_private_records_or_import_jobs(domain):
    _, service = domain
    svc = service("user")
    row = await svc.create_event(QualityEventCreate(record_type="consumer_complaint", content={"text": "私有原文"}))
    peer = QualityRiskService(svc.db, CurrentUser(user_id=service("expert").actor, org_id=svc.org_id, role="user"))
    with pytest.raises(NotFoundError):
        await peer.get_record(row["id"])
    assert (await peer.list_records(page=1, size=20))["total"] == 0
    preview = await svc.preview_import(request_key="private-job", file=file("a.json", b'[{"text":"test"}]'), record_type="consumer_complaint")
    with pytest.raises(NotFoundError):
        await peer.ingestion_job(preview["id"])


@pytest.mark.asyncio
async def test_utc_time_and_external_id_conflict(domain):
    _, service = domain
    svc = service("user")
    payload = QualityEventCreate(record_type="consumer_complaint", origin_label="真实出处", external_record_id="001",
                                occurred_at="2026-10-03T10:00:00+08:00", content={"text": "原文"})
    first = await svc.create_event(payload)
    assert first["occurred_at"] == datetime(2026, 10, 3, 2, tzinfo=timezone.utc).replace(tzinfo=None)
    assert (await svc.create_event(payload))["duplicate"]
    with pytest.raises(ConflictError):
        await svc.create_event(payload.model_copy(update={"content": {"text": "不同内容"}}))
    other = await svc.create_event(payload.model_copy(update={"origin_label": "另一出处"}))
    assert other["id"] != first["id"]


@pytest.mark.asyncio
async def test_attachment_only_submission_and_download_scope(domain, monkeypatch):
    class Storage:
        def put_bytes(self, **kwargs):
            return {"bucket": kwargs["bucket"], "object_key": kwargs["object_key"]}
    monkeypatch.setattr("app.services.quality_risk_service.build_object_storage", Storage)
    _, service = domain
    svc = service("user")
    attachment = await svc.upload_attachment(file("report.txt", b"raw report"))
    assert attachment["download_url"].endswith(f'{attachment["id"]}/download')
    row = await svc.create_event(QualityEventCreate(record_type="inspection_report", attachment_ids=[attachment["id"]]))
    assert row["content"] == {}
    peer = QualityRiskService(svc.db, CurrentUser(user_id=service("expert").actor, org_id=svc.org_id, role="user"))
    with pytest.raises(NotFoundError):
        await peer.accessible_attachment(attachment["id"])
    with pytest.raises(ValidationError):
        await svc.create_event(QualityEventCreate(record_type="consumer_complaint"))


@pytest.mark.asyncio
async def test_naive_import_time_defaults_to_shanghai_and_bad_headers_are_rejected(domain):
    _, service = domain
    svc = service("user")
    payload = json.dumps([{"text": "原文", "occurred_at": "2026-10-03T10:00:00"}]).encode()
    preview = await svc.preview_import(request_key="local-time", file=file("a.json", payload), record_type="consumer_complaint")
    assert preview["preview_rows"][0]["occurred_at"] == "2026-10-03T02:00:00"
    assert preview["preview_rows"][0]["provenance"]["source_timezone"] == "Asia/Shanghai"
    with pytest.raises(ValidationError, match="表头"):
        await svc.preview_import(request_key="headers", file=file("a.csv", b"text,text\na,b\n"), record_type="consumer_complaint")


@pytest.mark.asyncio
async def test_standard_files_use_existing_standard_library_not_business_intake(domain):
    _, service = domain
    with pytest.raises(ValidationError, match="标准库"):
        await service("user").create_event(QualityEventCreate(record_type="standard_document", content={"text": "标准原文"}))
    preview = await service("user").preview_import(request_key="standard-in-business", file=file("a.json", b'[{"text":"standard text","record_type":"standard_document"}]'))
    assert preview["error_count"] == 1
    with pytest.raises(ConflictError):
        await service("user").confirm_import(preview["id"])
