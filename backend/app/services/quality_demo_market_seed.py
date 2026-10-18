"""Optional stage-three synthetic series, anchored once; never rewrites records."""
from datetime import datetime, timedelta
from sqlalchemy import select

from app.core.config import settings
from app.models.organization import Organization
from app.models.quality_risk import QualityDataSource, QualitySourceRecord, QualityEvidenceItem
from app.models.supervision import SupervisionRecord
from app.services.quality_demo_seed import demo_id
from app.services.market_monitoring_service import iso, windows
from app.services.quality_risk_service import stable_hash


async def ensure_evidence(db):
    from app.schemas.user import CurrentUser
    from app.services.quality_risk_service import QualityRiskService
    svc = QualityRiskService(db, CurrentUser(user_id=demo_id("demo_analyst"), org_id=demo_id("organization"), role="expert"))
    for i in range(1, 12):
        row = await db.get(QualitySourceRecord, demo_id(f"market-record-{i}"))
        if row and row.deleted_at is None and row.data_nature == "synthetic":
            existing = await db.scalar(select(QualityEvidenceItem.id).where(QualityEvidenceItem.source_record_id == row.id))
            if not existing:
                await svc.materialize_evidence(row)


async def seed_market_demo(db):
    if not settings.quality_demo_enabled:
        raise ValueError("Only the isolated demo database may receive synthetic series")
    org = await db.get(Organization, demo_id("organization"))
    if not org or (org.settings or {}).get("execution_mode") != "demo":
        raise ValueError("Initialize the guarded demo first")
    marker = await db.get(SupervisionRecord, demo_id("market-seed"))
    if marker:
        await ensure_evidence(db)
        return {"reused": True, **marker.data}
    # The series remains fixed when initialization is repeated on another day.
    anchor = datetime.fromisoformat(org.settings["anchor_at"])
    from zoneinfo import ZoneInfo
    from datetime import timezone
    day = anchor.replace(tzinfo=timezone.utc).astimezone(ZoneInfo("Asia/Shanghai")).date()
    start, middle, end = windows(day)
    owner = demo_id("demo_analyst")
    source_id = demo_id("market-source")
    db.add(QualityDataSource(id=source_id, org_id=org.id, code="DEMO-MARKET-SERIES", name="演示市场时间序列（模拟）",
        source_type="mixed", connector_type="manual", config={"execution_mode": "demo", "as_of": day.isoformat()}, status="active", created_by=owner))
    entries = [("consumer_complaint", start + timedelta(days=2, hours=4), True)]
    entries += [("consumer_complaint", middle + timedelta(days=i, hours=4), True) for i in range(5)]
    entries += [("public_opinion", middle + timedelta(days=i, hours=6), True) for i in range(3)]
    entries += [("consumer_complaint", None, True), ("public_opinion", middle + timedelta(days=6, hours=5), False)]
    for i, (kind, occurred_at, linked) in enumerate(entries, 1):
        text = f"【演示模拟资料 {i:02d}】演示产品温升描述，用于数量线索验收，不是真实投诉、舆情或检测结论。"
        db.add(QualitySourceRecord(id=demo_id(f"market-record-{i}"), org_id=org.id, source_id=source_id,
            external_record_id=f"DEMO-QS-001-MKT-{i:02d}", record_type=kind, occurred_at=occurred_at, received_at=anchor,
            content={"text": text, "execution_mode": "demo", "demo_case_code": "DEMO-QS-001"}, content_hash=stable_hash({"market-seed": i}),
            enterprise_ref={"enterprise_id": demo_id("enterprise")} if linked else {"name": "未确认的原文名称"},
            product_ref={"product_id": demo_id("product"), "category_id": demo_id("category")} if linked else {"source_product_id": "未确认产品"},
            location={}, attachment_ids=[], provenance={"origin_label": "演示时间序列（模拟）", "seed_version": 3},
            authorization_scope="organization", data_nature="synthetic", normalization_status="normalized", normalization_errors=[], created_by=owner))
    from uuid import NAMESPACE_URL, uuid5
    for sid in (source_id, demo_id("source")):
        for kind in ("consumer_complaint", "public_opinion"):
            code = f"demo:{sid}:{kind}"
            db.add(SupervisionRecord(id=str(uuid5(NAMESPACE_URL, f"market:{org.id}:market-coverage:{code}")), org_id=org.id,
                kind="market-coverage", code=code, name="模拟资料覆盖声明", status="active", version=1, created_by=owner,
                data={"source_id": sid, "record_type": kind, "start_at": iso(start), "end_at": iso(end),
                      "execution_mode": "demo", "actor_id": owner, "at": iso(anchor),
                      "reason": "仅声明本次固定演示时间序列的覆盖范围，不代表真实市场资料完整性", "history": []}))
    data = {"execution_mode": "demo", "as_of": day.isoformat(), "record_count": len(entries), "seed_version": 3}
    db.add(SupervisionRecord(id=demo_id("market-seed"), org_id=org.id, kind="market-demo-seed", code="demo-v3",
                            name="阶段三模拟数据初始化", status="active", version=1, created_by=owner, data=data))
    await db.flush()
    await ensure_evidence(db)
    return {"reused": False, **data}
