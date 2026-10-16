"""Isolated risk-to-sampling flow and source changes at each decision boundary."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import DateTime, DefaultClause, MetaData, func, select, text
from test_quality_risk_v4 import domain  # noqa: F401 -- shared isolated database fixture

from agent.subgraphs.supervision.agents import AGENTS
from app.api.v1.deps import get_current_user, get_db
from app.api.v1.supervision import router
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.models.base import Base
from app.models.organization import Organization
from app.models.quality_risk import PhysicalSample, QualityRiskAssessment, QualitySourceRecord
from app.models.supervision import BusinessReview, SupervisionRun
from app.schemas.quality_risk import (
    PhysicalSampleCreate,
    QualityEventCreate,
    RiskAnalyzeRequest,
    RiskCaseCreate,
    RiskReviewRequest,
)
from app.schemas.supervision import (
    FeedbackData,
    RecordCreate,
    RecordUpdate,
    ReviewDecision,
    ReviewRequest,
    RunRequest,
)
from app.services.risk_decision_context_service import RiskDecisionContextService
from app.services.supervision_service import SupervisionService


@pytest_asyncio.fixture
async def flow(domain, monkeypatch):  # noqa: F811 -- pytest injects the imported fixture
    db, risk = domain
    meta = MetaData()
    for name in ["business_reviews", "supervision_events"]:
        table = Base.metadata.tables[name].to_metadata(meta)
        for column in table.c:
            if isinstance(column.type, DateTime) and column.server_default is not None:
                column.server_default = DefaultClause(text("CURRENT_TIMESTAMP"))
    async with db.bind.begin() as conn:
        await conn.run_sync(meta.create_all)
    org = await db.get(Organization, risk("user").org_id)
    org.settings = {"quality_supervision_enabled": True, "laboratory_validation_enabled": False}
    record = await risk("user").create_event(QualityEventCreate(record_type="supervision_inspection",
        content={"text": "隔离账号提供的真实来源弱信号，仍需现场验证"}))
    case = await risk("user").create_risk_case(RiskCaseCreate(title="隔离抽查闭环", scope_type="category",
        scope={"name": "电动自行车"}, source_record_ids=[record["id"]]))
    assessment = await risk("user").analyze_risk(case["id"], RiskAnalyzeRequest())
    await risk("expert").review_risk(case["id"], RiskReviewRequest(decision="accept", comment="隔离独立复核受限线索",
        risk_level="high", recommendations=["安排代表性抽查，发生概率未校准"]))
    await db.commit()

    def svc(role="expert"):
        return SupervisionService(db, risk(role).current)

    async def execute(self, snapshot, agent, **kwargs):
        return await AGENTS[agent].run(snapshot)

    monkeypatch.setattr(SupervisionService, "execute_agent_via_manager", execute)
    return db, risk, svc, record, case, assessment


async def plan(flow):
    _, _, svc, _, case, _ = flow
    return await svc().create("sampling-plans", RecordCreate(name="隔离风险抽查方案", data={
        "candidates": [{"case_id": case["id"], "sample_count": 2, "unit_cost": 10}],
        "budget": 100, "max_samples": 3, "max_staff_hours": 3, "hours_per_sample": 1,
        "required_categories": ["电动自行车"]}))


async def analyzed(flow):
    db, _, svc, _, _, _ = flow
    created = await plan(flow)
    run = await svc().queue_run("sampling-plans", created["id"], RunRequest(version=created["version"],
        operation="sampling", request_key=str(uuid4())))
    result = await svc().execute_run(run["id"])
    assert result["status"] == "completed", result
    await db.commit()
    return await svc().get("sampling-plans", created["id"]), result


@pytest.mark.asyncio
async def test_new_risk_completes_sampling_analysis_review_and_feedback(flow):
    db, _, svc, _, case, _ = flow
    p, result = await analyzed(flow)
    persisted = await db.scalar(select(SupervisionRun).where(SupervisionRun.id == result["id"])
        .execution_options(populate_existing=True))
    assert persisted.output["consumed_sources"][case["id"]] == 1
    assert p.data["analysis"]["selected"][0]["sample_count"] == 2
    review = await svc().submit_review("sampling-plans", p.id, ReviewRequest(version=p.version, operation="sampling.approve"))
    with pytest.raises(ForbiddenError):
        await svc().review_decision(review["id"], ReviewDecision(decision="accept", comment="本人不能批准"))
    await svc("expert2").review_decision(review["id"], ReviewDecision(decision="accept", comment="隔离另一专家批准抽查"))
    assert p.status == "approved" and p.data["sampling_batches"][0]["risk_ref"] == p.data["risk_refs"][0]
    assert not p.data["task_ids"]  # This plan does not request laboratory validation.
    await svc().feedback("sampling-plans", p.id, FeedbackData(version=p.version, outcome="new_evidence",
        text="隔离处置反馈提示重新核验", occurred_at=datetime.now(timezone.utc)))
    with pytest.raises(ValidationError):
        await svc().sampling_analysis_contexts(p)
    replacement = await svc().reassessment("sampling-plans", p.id)
    assert replacement["id"] != p.id and replacement["status"] == "draft" and p.status == "approved"
    assert "analysis" not in replacement["data"] and "sampling_batches" not in replacement["data"]
    assert replacement["data"]["risk_refs"] == p.data["risk_refs"]
    assert replacement["data"]["reassessment_basis"]["feedback"][0]["text"] == "隔离处置反馈提示重新核验"
    edited = await svc().update("sampling-plans", replacement["id"], RecordUpdate(version=replacement["version"],
        data={key: value for key, value in replacement["data"].items() if key not in {"risk_refs", "reassessment_basis"}}))
    assert edited["data"]["reassessment_basis"] == replacement["data"]["reassessment_basis"]


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["create", "queued", "during_run", "submit", "accept", "after_approval"])
async def test_changed_sources_cannot_enter_or_continue_sampling(flow, stage, monkeypatch):
    db, risk, svc, record, _, _ = flow
    review, p, run = None, None, None
    if stage in {"submit", "accept", "after_approval"}:
        p, _ = await analyzed(flow)
        if stage in {"accept", "after_approval"}:
            review = await svc().submit_review("sampling-plans", p.id, ReviewRequest(version=p.version, operation="sampling.approve"))
        if stage == "after_approval":
            await svc("expert2").review_decision(review["id"], ReviewDecision(decision="accept", comment="隔离批准"))
    elif stage in {"queued", "during_run"}:
        p = await plan(flow)
        run = await svc().queue_run("sampling-plans", p["id"], RunRequest(version=p["version"], operation="sampling", request_key=str(uuid4())))
    source = await db.get(QualitySourceRecord, record["id"])

    async def change_source():
        source.content = {"text": "来源版本已变化"}
        await db.flush()

    if stage == "during_run":
        async def execute(self, snapshot, agent, **kwargs):
            result = await AGENTS[agent].run(snapshot)
            await change_source()
            return result
        monkeypatch.setattr(SupervisionService, "execute_agent_via_manager", execute)
    else:
        await change_source()
    if stage == "create":
        with pytest.raises(ValidationError):
            await plan(flow)
    elif stage in {"queued", "during_run"}:
        result = await svc().execute_run(run["id"])
        assert result["status"] == "stale" and result["output"] is None
    elif stage == "submit":
        with pytest.raises(ValidationError):
            await svc().submit_review("sampling-plans", p.id, ReviewRequest(version=p.version, operation="sampling.approve"))
    elif stage == "accept":
        with pytest.raises(ValidationError):
            await svc("expert2").review_decision(review["id"], ReviewDecision(decision="accept", comment="失效来源不能批准"))
        stored = await db.get(BusinessReview, review["id"])
        assert stored.status == "pending" and p.status != "approved"
    else:
        org = await db.get(Organization, risk("user").org_id)
        org.settings = {**org.settings, "laboratory_validation_enabled": True}
        with pytest.raises(ValidationError):
            await risk("expert2").create_physical_sample(PhysicalSampleCreate(sampling_plan_id=p.id))
        assert p.status == "approved" and p.data["sampling_batches"]  # History remains intact.
    assert (await db.scalar(select(func.count()).select_from(PhysicalSample))) == 0


@pytest.mark.asyncio
async def test_new_assessment_version_requires_explicit_plan_refresh(flow):
    _db, risk, svc, _, case, _ = flow
    p = await plan(flow)
    await risk("user").analyze_risk(case["id"], RiskAnalyzeRequest())
    with pytest.raises(ValidationError):
        await svc().snapshot(await svc().get("sampling-plans", p["id"]))
    await risk("expert2").review_risk(case["id"], RiskReviewRequest(decision="accept", comment="隔离复核第二版", risk_level="medium"))
    with pytest.raises(ValidationError):
        await svc().snapshot(await svc().get("sampling-plans", p["id"]))
    updated = await svc().update("sampling-plans", p["id"], RecordUpdate(version=p["version"], data={
        key: value for key, value in p["data"].items() if key != "risk_refs"}))
    assert updated["data"]["risk_refs"][0]["version"] == 2
    assert await svc().snapshot(await svc().get("sampling-plans", p["id"]))


@pytest.mark.asyncio
async def test_current_candidate_and_market_endpoints_exclude_withdrawn_evidence(flow):
    db, risk, _svc, record, case, _ = flow
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: risk("expert2").current

    async def session():
        yield db

    app.dependency_overrides[get_db] = session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        candidates = (await client.get("/quality-supervision/sampling-candidates")).json()["data"]
        assert candidates["items"][0]["id"] == case["id"] and candidates["items"][0]["assessment_version"] == 1
        report = (await client.get("/quality-supervision/analytics")).json()["data"]
        assert report["unknown_time_count"] == 1 and report["current_count"] == 0
        (await db.get(QualitySourceRecord, record["id"])).deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await db.flush()
        candidates = (await client.get("/quality-supervision/sampling-candidates")).json()["data"]
        assert not candidates["items"] and candidates["excluded_count"] == 1
        report = (await client.get("/quality-supervision/analytics")).json()["data"]
        assert report["excluded_count"] == 1 and not report["risk_refs"]


@pytest.mark.asyncio
async def test_unverified_or_cross_tenant_risk_status_is_not_a_candidate(flow):
    db, risk, _, _, case, assessment = flow
    other = risk("expert").current.model_copy(update={"org_id": str(uuid4())})
    with pytest.raises(NotFoundError):
        await RiskDecisionContextService(db, other).accepted(case["id"])
    row = await db.get(QualityRiskAssessment, assessment["id"])
    row.model_versions = {**row.model_versions, "review_verification": {}}
    await db.flush()
    with pytest.raises(ValidationError):
        await RiskDecisionContextService(db, risk("expert2").current).accepted(case["id"])


@pytest.mark.asyncio
async def test_market_time_windows_use_actual_offsets_and_skip_unknown_times():
    def item(at):
        return {"data": {"occurred_at": at}}
    result = await AGENTS["market_monitoring"].run({"as_of": "2026-10-14T00:00:00Z",
        "cases": [item(None), item("invalid"), item("2026-10-14T08:00:00+08:00"),
            item("2026-09-14T08:00:00+08:00"), item("2026-10-14T08:01:00+08:00")]})
    assert (result["current_count"], result["previous_count"], result["unknown_time_count"]) == (1, 1, 2)
