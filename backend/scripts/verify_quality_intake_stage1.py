"""Exercise real local API/MySQL in dedicated tenants; cleanup after browser verification."""
import argparse
import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import delete, select

from app.core.security import create_access_token
from app.models import Organization, User
from app.models.business_number import BusinessIdentifier, BusinessNumberSequence
from app.models.audit import AuditLog, AuditOutbox
from app.models.quality_risk import (
    ProductCategory,
    ProductIdentifier,
    EnterpriseProductRelation,
    QualityAttachment,
    QualityDataSource,
    QualityEvidenceItem,
    QualityIngestionJob,
    QualityProduct,
    QualityProductionBatch,
    QualitySourceRecord,
)
from app.models.supervision import SupervisionEvent, SupervisionRecord, SupervisionRevision, SupervisionRun
from app.services.object_storage import build_object_storage
from infra.database.session import get_session, reset_async_engine_pool

STATE = Path("runtime/quality_intake_stage1/auth.json")


async def setup():
    if STATE.exists():
        raise RuntimeError("先清理上一轮验证环境")
    orgs = [str(uuid4()), str(uuid4())]
    identities = {}
    async with get_session() as db:
        for oid in orgs:
            db.add(Organization(id=oid, name="质监接入隔离验证", slug=f"intake-stage1-{oid}", is_active=True,
                                settings={"quality_supervision_enabled": True}))
        for key, role, oid in [("user", "user", orgs[0]), ("peer", "user", orgs[0]), ("expert", "expert", orgs[0]),
                               ("admin", "admin", orgs[0]), ("outsider", "user", orgs[1])]:
            user_id = str(uuid4())
            username = f"intake-test-{user_id[:8]}"
            db.add(User(id=user_id, org_id=oid, username=username, email=f"{user_id}@example.com", role=role, is_active=True))
            token = create_access_token(user_id, {"org_id": oid, "role": role, "exp": int((datetime.now(timezone.utc)+timedelta(minutes=30)).timestamp())})
            identities[key] = {"token": token, "user_id": user_id, "org_id": oid, "username": username, "role": role}
        await db.commit()
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"orgs": orgs, "identities": identities}), encoding="utf-8")
    checks = []
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000/api/v1", timeout=60) as client:
        def headers(key="user"):
            return {"Authorization": f"Bearer {identities[key]['token']}"}
        async def post(path, payload, key="user"):
            response = await client.post(path, json=payload, headers=headers(key))
            assert response.is_success, (path, response.status_code, response.text[:300])
            return response.json()["data"]
        payload = {"record_type": "consumer_complaint", "content": {"text": "隔离验证：续航下降"}, "data_nature": "synthetic"}
        row = await post("/quality-data/events", payload)
        assert row["occurred_at"] is None and len(row["display_no"]) == 20
        assert (await post("/quality-data/events", payload))["duplicate"]
        for key in ["peer", "outsider"]:
            assert (await client.get(f"/quality-data/records/{row['id']}", headers=headers(key))).status_code == 404
        checks.append("未知出处/时间直接受理、重复请求复用、同组织与跨租户隔离")
        uploaded = await client.post("/quality-data/attachments", files=[("files", ("stage1-report.txt", b"isolated raw report", "text/plain"))], headers=headers())
        assert uploaded.is_success, uploaded.text[:300]
        attachment = uploaded.json()["data"][0]
        download = f"/quality-data/attachments/{attachment['id']}/download"
        assert (await client.get(download, headers=headers())).content == b"isolated raw report"
        assert (await client.get(download, headers=headers("peer"))).status_code == 404
        assert (await client.get(download)).status_code == 403
        await post("/quality-data/events", {"record_type": "inspection_report", "attachment_ids": [attachment["id"]], "data_nature": "synthetic"})
        checks.append("附件原件受理与鉴权下载，不把存储当解析完成")
        category = await post("/quality-products/categories", {"name": "电动自行车"}, "admin")
        product = await post("/quality-products", {"category_id": category["id"], "name": "隔离测试型号"}, "admin")
        assert category["display_no"].startswith("FL-") and product["display_no"].startswith("CP-")
        csv = ("原始内容,原始出处,外部编号,生产批次,product_id,category_id,data_nature\n"
               f"隔离投诉A,出处甲,001,000123,{product['id']},{category['id']},synthetic\n"
               f"隔离投诉B,出处乙,002,000124,{product['id']},{category['id']},synthetic\n").encode("utf-8-sig")
        async def preview(key):
            response = await client.post("/quality-data/imports", data={"request_key": key, "record_type": "consumer_complaint", "origin_label": "共同默认出处"},
                                         files={"file": ("stage1.csv", csv, "text/csv")}, headers=headers())
            assert response.is_success, response.text[:300]
            return response.json()["data"]
        job = await preview("isolated-import")
        assert job["valid_count"] == 2 and job["error_count"] == 0
        assert job["preview_rows"][0]["origin_label"] == "出处甲"
        result = await post(f"/quality-data/imports/{job['id']}/confirm", {})
        assert result["created_count"] == 2
        second = await preview("isolated-import-2")
        result2 = await post(f"/quality-data/imports/{second['id']}/confirm", {})
        assert result2["duplicate_count"] == 2 and result2["created_count"] == 0
        records = (await client.get("/quality-data/records", params={"ingestion_job_id": job["id"]}, headers=headers())).json()["data"]
        assert records["total"] == 2 and records["items"][0]["product_ref"]["product_id"] == product["id"]
        checks.append("中文CSV真实导入、引用/逐行出处保留、确认重试和重复计数")
        parallel = await asyncio.gather(*[post("/quality-data/events", {**payload, "external_record_id": f"parallel-{i}", "content": {"text": f"隔离并发材料{i}"}}) for i in range(20)])
        assert len({r["display_no"] for r in parallel}) == 20
        checks.append("20个真实并发API请求，经MySQL分配不同固定长度编号")
        repeated = await asyncio.gather(*[post("/quality-data/events", {**payload, "external_record_id": "concurrent-retry"}) for _ in range(10)])
        assert len({r["id"] for r in repeated}) == 1 and len({r["display_no"] for r in repeated}) == 1
        jobs = await asyncio.gather(*[preview("concurrent-preview") for _ in range(5)])
        assert len({j["id"] for j in jobs}) == 1
        checks.append("10个并发重试复用同一受理号，5个同键并发预览复用同一导入任务")
    STATE.with_name("validation.json").write_text(json.dumps({"checks": checks}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"checks": checks, "browser_fixture": str(STATE)}, ensure_ascii=False))


async def cleanup():
    if not STATE.exists():
        return
    state = json.loads(STATE.read_text(encoding="utf-8"))
    orgs = state["orgs"]
    async with get_session() as db:
        for org in await db.scalars(select(Organization).where(Organization.id.in_(orgs))):
            assert org.slug == f"intake-stage1-{org.id}", "拒绝清理非验证租户"
        storage = build_object_storage()
        for attachment in await db.scalars(select(QualityAttachment).where(QualityAttachment.org_id.in_(orgs))):
            storage.delete_object(bucket=attachment.bucket, object_key=attachment.object_key)
        await db.execute(delete(AuditOutbox).where(AuditOutbox.payload["org_id"].as_string().in_(orgs)))
        for model in [QualityEvidenceItem, QualitySourceRecord, QualityIngestionJob, QualityAttachment, QualityDataSource,
                      ProductIdentifier, EnterpriseProductRelation, QualityProductionBatch, QualityProduct, ProductCategory, BusinessIdentifier, BusinessNumberSequence, SupervisionRun, SupervisionRevision, SupervisionEvent, SupervisionRecord, AuditLog, User, Organization]:
            column = model.id if model is Organization else model.org_id
            await db.execute(delete(model).where(column.in_(orgs)))
        await db.commit()
    STATE.unlink()
    print("隔离验证租户与附件已清理，验证结果保留")


async def main():
    try:
        if args.cleanup:
            await cleanup()
        else:
            await setup()
    finally:
        await reset_async_engine_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()
    asyncio.run(main())
