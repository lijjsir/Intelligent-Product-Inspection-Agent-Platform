from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.models.organization import Organization
from app.models.quality_risk import QualityDataSource, QualityProduct, QualityRiskCase, QualitySourceRecord
from app.models.supervision import SupervisionRecord
from app.schemas.market_monitoring import MarketScan, MarketRuleUpdate, MarketCoverage, MarketFocus, SignalConversion
from app.schemas.quality_risk import DataSourceCreate, ProductCategoryCreate, ProductCreate, QualityEventCreate
from app.services.market_monitoring_service import MarketMonitoringService, windows, classify
from test_quality_risk_v4 import domain  # noqa: F401

DAY = date(2026, 10, 16)


async def setup(domain, monkeypatch, previous=1, current=4, covered=True, nature="observed"):
    monkeypatch.setattr(settings, "quality_demo_enabled", False)
    db, service = domain
    admin = service("admin")
    org = await db.get(Organization, admin.org_id)
    org.settings = {"quality_supervision_enabled": True}
    cat = await admin.create_category(ProductCategoryCreate(code="C", name="类别"))
    product = await admin.create_product(ProductCreate(name="产品", category_id=cat["id"]))
    source = await admin.create_source(DataSourceCreate(code="S", name="受理来源", source_type="mixed", connector_type="manual"))
    monitor = MarketMonitoringService(db, service("expert").current)
    start, middle, end = windows(DAY)
    if covered:
        await monitor.set_coverage(MarketCoverage(source_id=source["id"], record_type="consumer_complaint",
            start_at=start.replace(tzinfo=timezone.utc), end_at=end.replace(tzinfo=timezone.utc), reason="已核对来源覆盖"))
    records = []
    for index in range(previous + current):
        event = await service("expert").create_event(QualityEventCreate(source_id=source["id"], record_type="consumer_complaint",
            occurred_at=(start if index < previous else middle).replace(tzinfo=timezone.utc) + timedelta(hours=index),
            content={"text": f"原始投诉{index}"}, product_ref={"product_id": product["id"]}, data_nature=nature))
        records.append(event)
    await db.flush()
    return db, monitor, service, product, source, records


def test_complete_windows_shanghai_boundaries():
    before_midnight = datetime(2026, 10, 16, 15, 59, tzinfo=timezone.utc)
    after_midnight = datetime(2026, 10, 16, 16, 0, tzinfo=timezone.utc)
    assert windows(now=before_midnight)[2] == datetime(2026, 10, 15, 16)
    assert windows(now=after_midnight)[2] == datetime(2026, 10, 16, 16)
    start, middle, end = windows(DAY)
    assert end - middle == middle - start == timedelta(days=7)
    with pytest.raises(ValidationError):
        windows(date(2100, 1, 1))


def test_rule_thresholds_zero_and_coverage():
    rule = {"min_current": 3, "min_increase": 3, "growth_factor": 2}
    assert classify(0, 3, True, rule) == ("new_cluster", None)
    assert classify(1, 4, True, rule) == ("quantity_growth", 300)
    assert classify(2, 4, True, rule)[0] == "normal"
    assert classify(10, 13, True, rule)[0] == "normal"
    assert classify(0, 9, False, rule) == ("insufficient_coverage", None)


@pytest.mark.asyncio
async def test_signal_snapshot_and_idempotent_conversion(domain, monkeypatch):
    db, monitor, _, product, _, records = await setup(domain, monkeypatch)
    report = await monitor.report(MarketScan(as_of=DAY), persist=True)
    group = report["groups"][0]
    assert group["status"] == "quantity_growth"
    assert group["previous_count"] == 1 and group["current_count"] == 4
    assert set(group["source_record_ids"]) == {r["id"] for r in records}
    assert group["rule"]["algorithm"] == "count-growth-v1"
    assert (await monitor.detail(group["signal_id"]))["is_current"]
    first = await monitor.convert(group["signal_id"], SignalConversion())
    second = await monitor.convert(group["signal_id"], SignalConversion())
    assert first["case"]["id"] == second["case"]["id"]
    assert first["reused"] is False and second["reused"] is True
    assert first["case"]["scope"]["product_id"] == product["id"]
    assert first["case"]["status"] == "collecting"
    assert await db.scalar(select(func.count()).select_from(QualityRiskCase)) == 1
    repeated = await monitor.report(MarketScan(as_of=DAY), persist=True)
    assert repeated["groups"][0]["signal_id"] == group["signal_id"]
    assert repeated["groups"][0]["case_id"] == first["case"]["id"]


@pytest.mark.asyncio
async def test_missing_coverage_has_no_signal_and_cannot_assume_zero(domain, monkeypatch):
    db, monitor, *_ = await setup(domain, monkeypatch, previous=0, current=8, covered=False)
    report = await monitor.report(MarketScan(as_of=DAY), persist=True)
    assert report["groups"][0]["status"] == "insufficient_coverage"
    assert report["groups"][0]["signal_id"] is None
    assert report["groups"][0]["growth_percent"] is None
    assert not list(await db.scalars(select(SupervisionRecord).where(SupervisionRecord.kind == "market-signal")))


@pytest.mark.asyncio
async def test_missing_time_pending_identity_and_partial_day_are_separate(domain, monkeypatch):
    _, monitor, service, product, source, _ = await setup(domain, monkeypatch, previous=0, current=3)
    for text, occurred, ref in [("未知日期", None, {"product_id": product["id"]}),
                                ("仅名称", windows(DAY)[1], {"source_product_id": "原文产品"}),
                                ("本日资料", windows(DAY)[2], {"product_id": product["id"]})]:
        await service("expert").create_event(QualityEventCreate(source_id=source["id"], record_type="consumer_complaint",
            occurred_at=occurred.replace(tzinfo=timezone.utc) if occurred else None, content={"text": text}, product_ref=ref))
    r = await monitor.report(MarketScan(as_of=DAY), persist=True)
    assert len(r["missing_time"]) == 1 and len(r["pending_objects"]) == 1
    assert r["totals"]["consumer_complaint"]["current"] == 4
    assert r["groups"][0]["current_count"] == 3
    assert r["groups"][0]["status"] == "new_cluster"
    assert r["groups"][0]["growth_percent"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["withdraw", "object", "coverage", "rule", "source", "add"])
async def test_changed_basis_rejects_conversion(domain, monkeypatch, change):
    db, monitor, service, product, source, records = await setup(domain, monkeypatch)
    r = await monitor.report(MarketScan(as_of=DAY), persist=True)
    signal = r["groups"][0]["signal_id"]
    record = await db.get(QualitySourceRecord, records[-1]["id"])
    if change == "withdraw":
        record.deleted_at = datetime.utcnow()
    elif change == "object":
        record.product_ref = {"product_name": "产品"}
    elif change == "source":
        (await db.get(QualityDataSource, source["id"])).status = "inactive"
    elif change == "coverage":
        start, middle, end = windows(DAY)
        await monitor.set_coverage(MarketCoverage(source_id=source["id"], record_type="consumer_complaint",
            start_at=middle.replace(tzinfo=timezone.utc), end_at=end.replace(tzinfo=timezone.utc), reason="覆盖声明修正"))
    elif change == "add":
        await service("expert").create_event(QualityEventCreate(source_id=source["id"], record_type="consumer_complaint",
            occurred_at=windows(DAY)[1].replace(tzinfo=timezone.utc), content={"text": "迟到资料"}, product_ref={"product_id": product["id"]}))
    else:
        await monitor.update_rule(MarketRuleUpdate(expected_version=1, min_current=10, reason="调整阈值"))
    await db.flush()
    assert not (await monitor.detail(signal))["is_current"]
    with pytest.raises(ConflictError):
        await monitor.convert(signal, SignalConversion())
    assert await db.scalar(select(func.count()).select_from(QualityRiskCase)) == 0


@pytest.mark.asyncio
async def test_focus_reuses_canonical_object_and_preserves_history(domain, monkeypatch):
    db, monitor, _, product, *_ = await setup(domain, monkeypatch)
    p = MarketFocus(object_type="product", object_id=product["id"], reason="跟踪异常")
    first, second = await monitor.add_focus(p), await monitor.add_focus(p)
    assert first["id"] == second["id"] and second["reused"]
    assert len(await monitor.focus_list()) == 1
    await monitor.remove_focus(first["id"], "阶段观察完成")
    assert not await monitor.focus_list()
    assert (await monitor.add_focus(p))["id"] == first["id"]
    row = await db.get(SupervisionRecord, first["id"])
    assert [x["action"] for x in row.data["history"]] == ["add", "remove", "add"]
    (await db.get(QualityProduct, product["id"])).is_active = False
    await db.flush()
    assert (await monitor.focus_list())[0]["available"] is False
    with pytest.raises(NotFoundError):
        await monitor.add_focus(p)


@pytest.mark.asyncio
async def test_roles_cross_org_and_synthetic_exclusion(domain, monkeypatch):
    db, monitor, service, product, _, records = await setup(domain, monkeypatch, nature="synthetic")
    assert not (await monitor.report(MarketScan(as_of=DAY), persist=True))["groups"]
    for role in ("user", "algorithm_engineer"):
        with pytest.raises(ForbiddenError):
            await MarketMonitoringService(db, service(role).current).report(MarketScan(as_of=DAY))
    for r in records:
        row = await db.get(QualitySourceRecord, r["id"])
        row.data_nature = "observed"
        row.org_id = str(uuid4())
    await db.flush()
    assert not (await monitor.report(MarketScan(as_of=DAY)))["groups"]
    with pytest.raises(NotFoundError):
        await monitor.add_focus(MarketFocus(object_type="product", object_id=str(uuid4()), reason="外组织ID"))


@pytest.mark.asyncio
async def test_rules_concurrency_and_timezone_validation(domain, monkeypatch):
    _, monitor, *_ = await setup(domain, monkeypatch)
    await monitor.update_rule(MarketRuleUpdate(expected_version=1, reason="调整规则", min_current=6))
    with pytest.raises(ConflictError):
        await monitor.update_rule(MarketRuleUpdate(expected_version=1, reason="陈旧规则"))
    from pydantic import ValidationError as PydanticError
    with pytest.raises(PydanticError):
        MarketCoverage(source_id=str(uuid4()), record_type="consumer_complaint", start_at="2026-01-01", end_at="2026-02-01", reason="无时区")


@pytest.mark.asyncio
async def test_legacy_enterprise_alias_and_inactive_object(domain, monkeypatch):
    db, monitor, _, product, _, records = await setup(domain, monkeypatch)
    company = SupervisionRecord(id=str(uuid4()), org_id=monitor.org_id, kind="enterprises", code="ENT",
        name="企业", status="active", version=1, created_by=monitor.actor, data={})
    db.add(company)
    await db.flush()
    for r in records:
        (await db.get(QualitySourceRecord, r["id"])).enterprise_ref = {"id": company.id, "name": "历史原始名称"}
    await db.flush()
    report = await monitor.report(MarketScan(as_of=DAY, object_type="enterprise"), persist=True)
    assert report["groups"][0]["object_id"] == company.id
    assert report["groups"][0]["object_name"] == "企业"
    company.status = "archived"
    await db.flush()
    report = await monitor.report(MarketScan(as_of=DAY, object_type="enterprise"))
    assert not report["groups"] and len(report["pending_objects"]) == 5
    with pytest.raises(NotFoundError):
        await monitor.detail(str(uuid4()))


@pytest.mark.asyncio
async def test_demo_is_server_controlled_and_does_not_count_real_data(domain, monkeypatch):
    db, monitor, *_ = await setup(domain, monkeypatch)
    org = await db.get(Organization, monitor.org_id)
    org.settings = {**org.settings, "execution_mode": "demo"}
    await db.flush()
    with pytest.raises(ForbiddenError):
        await monitor.report(MarketScan(as_of=DAY))
    monkeypatch.setattr(settings, "quality_demo_enabled", True)
    demo = MarketMonitoringService(db, monitor.current)
    assert not (await demo.report(MarketScan(as_of=DAY)))["groups"]
