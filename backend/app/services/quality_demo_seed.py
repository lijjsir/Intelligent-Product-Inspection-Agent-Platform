"""Idempotent draft-only scenario. Never approves risk, standards or knowledge."""
import hashlib
import os
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from app.core.quality_demo import DEMO_CASE_CODE, DEMO_ORG_SLUG
from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.models.organization import Organization
from app.models.user import User
from app.models.quality_risk import (
    ProductCategory, QualityProduct, QualityAttachment, QualityDataSource,
    QualitySourceRecord, QualityEvidenceItem, QualityRiskCase, QualityRiskAssessment,
)
from app.models.supervision import SupervisionRecord
from app.services.quality_risk_service import stable_hash
from app.services.risk_evidence_validation_service import record_definition, evidence_definition

ACCOUNTS = (("demo_admin", "admin", "PIAP_QUALITY_DEMO_ADMIN_PASSWORD"),
            ("demo_analyst", "expert", "PIAP_QUALITY_DEMO_ANALYST_PASSWORD"),
            ("demo_reviewer", "expert", "PIAP_QUALITY_DEMO_REVIEWER_PASSWORD"))


def demo_id(name: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"piap-quality-demo:{name}"))


async def seed_quality_demo(db, storage, passwords=None) -> dict:
    if not settings.quality_demo_enabled:
        raise ValueError("Demo seeding is not enabled in this process")
    passwords = passwords or {name: os.environ.get(key, "") for name, _, key in ACCOUNTS}
    if any(len(passwords.get(name, "")) < 16 for name, _, _ in ACCOUNTS):
        raise ValueError("Initialize the three local demo account passwords first (at least 16 characters)")
    org_id = demo_id("organization")
    org = await db.get(Organization, org_id)
    if not org:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        org = Organization(id=org_id, slug=DEMO_ORG_SLUG, name="质量监督隔离演示组织", plan="standard",
            settings={"quality_supervision_enabled": True, "laboratory_validation_enabled": True,
                      "execution_mode": "demo", "demo_seed_version": 1, "anchor_at": now.isoformat()}, is_active=True)
        db.add(org)
    elif org.slug != DEMO_ORG_SLUG or (org.settings or {}).get("execution_mode") != "demo":
        raise ValueError("Existing organization is not the expected demo organization; refusing to overwrite")
    await db.flush()
    for name, role, _ in ACCOUNTS:
        user = await db.get(User, demo_id(name))
        if not user:
            db.add(User(id=demo_id(name), org_id=org_id, username=name, email=f"{name}@quality-demo.example.com",
                        password_hash=hash_password(passwords[name]), role=role, is_active=True))
        elif user.org_id != org_id or user.username != name or user.role != role or not verify_password(passwords[name], user.password_hash):
            raise ValueError("Existing demo identity differs; passwords and roles are never reset by reseeding")
        elif user.email == f"{name}@quality-demo.invalid":
            # Repair only the reserved-address placeholder from the initial
            # bootstrap; EmailStr intentionally rejects .invalid at login.
            user.email = f"{name}@quality-demo.example.com"
    await db.flush()
    case = await db.get(QualityRiskCase, demo_id("case"))
    if case:
        if case.org_id != org_id or case.code != DEMO_CASE_CODE:
            raise ValueError("Demo case identity differs; refusing to overwrite")
        return {"case_id": case.id, "case_code": case.code, "organization_slug": org.slug,
                "reused": True, "seed_version": 1, "execution_mode": "demo"}

    owner, admin = demo_id("demo_analyst"), demo_id("demo_admin")
    db.add(SupervisionRecord(id=demo_id("enterprise"), org_id=org_id, kind="enterprises", code="DEMO-ENT-001",
        name="演示企业A（虚构）", status="active", version=1, created_by=admin,
        data={"execution_mode": "demo", "synthetic": True}, created_at=datetime.utcnow(), updated_at=datetime.utcnow()))
    db.add(ProductCategory(id=demo_id("category"), org_id=org_id, code="DEMO-APPLIANCE", name="演示小家电",
        classification_basis="仅供功能验收的虚构类别，不对应正式分类或标准", is_active=True))
    db.add(QualityProduct(id=demo_id("product"), org_id=org_id, category_id=demo_id("category"), name="演示产品A",
        brand="演示品牌（虚构）", model="DEMO-A", manufacturer_enterprise_id=demo_id("enterprise"),
        attributes={"execution_mode": "demo", "synthetic": True}, is_active=True))
    db.add(QualityDataSource(id=demo_id("source"), org_id=org_id, code="DEMO-QS-SOURCE", name="隔离演示资料源",
        source_type="public_opinion", connector_type="manual", config={"execution_mode": "demo"}, status="active", created_by=admin))
    await db.flush()
    attachment_text = "演示测量资料\n这是一份虚构文本，用于验收资料引用与附件下载；不是实际检测报告，不包含真实设备测量。\n"
    content = attachment_text.encode("utf-8")
    key = f"quality-demo/{DEMO_CASE_CODE}/simulated-measurements.txt"
    storage.put_bytes(bucket="quality-demo-business", object_key=key, data=content, content_type="text/plain; charset=utf-8")
    db.add(QualityAttachment(id=demo_id("attachment"), org_id=org_id, file_name="演示测量资料（非真实报告）.txt",
        mime_type="text/plain", size_bytes=len(content), sha256=hashlib.sha256(content).hexdigest(),
        bucket="quality-demo-business", object_key=key, uploaded_by=owner))
    anchor = datetime.fromisoformat(org.settings["anchor_at"])
    records, evidence = [], []
    for index, (kind, text) in enumerate([
        ("consumer_complaint", "【演示投诉】虚构用户描述产品使用时温升异常，仅供流程验收。"),
        ("public_opinion", "【演示舆情】虚构公开记录提及演示产品发热，不是实际市场事件。"),
        ("inspection_report", "【演示测量资料】附件为模拟文本，不是实际检测报告，不能据此确认正式风险。"),
    ], 1):
        row = QualitySourceRecord(id=demo_id(f"record-{index}"), org_id=org_id, source_id=demo_id("source"),
            external_record_id=f"{DEMO_CASE_CODE}-{index:02d}", record_type=kind,
            occurred_at=anchor-timedelta(days=index), received_at=anchor,
            content={"text": text, "execution_mode": "demo", "demo_case_code": DEMO_CASE_CODE},
            content_hash=stable_hash({"case": DEMO_CASE_CODE, "record": index}),
            enterprise_ref={"id": demo_id("enterprise"), "name": "演示企业A（虚构）"},
            product_ref={"product_id": demo_id("product"), "category_id": demo_id("category")},
            location={"location_method": "unknown"}, attachment_ids=[demo_id("attachment")] if index == 3 else [],
            provenance={"origin_label": "隔离演示资料（虚构）", "execution_mode": "demo", "seed_version": 1},
            authorization_scope="organization", data_nature="synthetic", normalization_status="normalized",
            normalization_errors=[], created_by=owner)
        item = QualityEvidenceItem(id=demo_id(f"evidence-{index}"), org_id=org_id,
            evidence_code=f"DEMO-EV-{index:02d}", source_record_id=row.id, evidence_type=kind, text=text,
            structured_data={"execution_mode": "demo"}, attachment_id=demo_id("attachment") if index == 3 else None,
            nature="synthetic", locator={"source_record_id": row.id}, content_hash=stable_hash({"text": text}))
        db.add_all([row, item]); records.append(row); evidence.append(item)
    await db.flush()
    scope = {"name": "演示产品A", "product_id": demo_id("product"), "category_id": demo_id("category"),
             "enterprise_id": demo_id("enterprise"), "execution_mode": "demo"}
    case = QualityRiskCase(id=demo_id("case"), org_id=org_id, code=DEMO_CASE_CODE, title="演示产品温升异常",
        scope_type="product", scope=scope, status="awaiting_evidence", source_record_ids=[r.id for r in records],
        evidence_ids=[e.id for e in evidence], created_by=owner, assigned_to=owner)
    db.add(case)
    db.add(QualityRiskAssessment(id=demo_id("assessment-1"), org_id=org_id, risk_case_id=case.id, version=1,
        scope=scope, risk_type=None, risk_level="unknown", evidence_ids=[], standard_matches=[], conflicts=[],
        missing_inputs=["当前全部为模拟资料，尚无真实检测证据", "等待两名不同专家执行后续演示研判与复核"],
        possible_causes=[], recommendations=[], trust_status="unverified", probability=None, status="awaiting_evidence",
        submitted_by=owner, model_versions={"execution_mode": "demo", "initialization": "draft_only", "llm_called": False,
            "evidence_basis": {"evidence_ids": [e.id for e in evidence], "records": {r.id: record_definition(r) for r in records},
                               "evidence": {e.id: evidence_definition(e) for e in evidence}, "attachment_hashes": {}}}))
    await db.flush()
    return {"case_id": case.id, "case_code": case.code, "organization_slug": org.slug,
            "reused": False, "seed_version": 1, "execution_mode": "demo"}
