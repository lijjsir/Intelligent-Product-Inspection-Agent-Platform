"""Case restoration, evidence supplementation and tenant boundaries."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from test_quality_risk_v4 import domain  # noqa: F401
from app.api.v1.quality_risk import router, service as api_service
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.models.quality_risk import QualityRiskAssessment, QualitySourceRecord, QualityEvidenceItem
from app.schemas.quality_risk import QualityEventCreate, RiskAnalyzeRequest, RiskCaseCreate, RiskReviewRequest
from app.schemas.user import CurrentUser
from app.services.quality_risk_service import QualityRiskService
from app.services.risk_decision_context_service import RiskDecisionContextService


async def make_case(service):
    source = await service("user").create_event(QualityEventCreate(
        record_type="supervision_inspection", content={"text": "真实抽检原文", "risk_level": "high"},
    ))
    case = await service("user").create_risk_case(RiskCaseCreate(
        title="研判工作区", scope_type="product", scope={"name": "产品A"}, source_record_ids=[source["id"]],
    ))
    return source, case


@pytest.mark.asyncio
async def test_workspace_restores_saved_versions_review_and_sources(domain):
    db, service = domain
    source, case = await make_case(service)
    first = await service("user").analyze_risk(case["id"], RiskAnalyzeRequest())
    await service("expert").review_risk(case["id"], RiskReviewRequest(decision="accept", comment="核对来源后确认"))
    second = await service("user").analyze_risk(case["id"], RiskAnalyzeRequest())
    await db.commit()
    # Exercise the actual response schema used by the frontend.
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[api_service] = lambda: service("expert")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/risk-cases/{case['id']}/workspace")
    assert response.status_code == 200, response.text
    workspace = response.json()["data"]
    assert workspace["case"]["id"] == case["id"]
    assert workspace["latest_assessment"]["id"] == second["id"]
    assert [v["version"] for v in workspace["assessment_versions"]] == [2, 1]
    assert workspace["records"][0]["id"] == source["id"]
    assert not workspace["unavailable_source_ids"]
    assert workspace['workflow_context']['enabled'] is False
    assert workspace['workflow_context']['can_author'] is False
    previous = await service("expert").get_assessment(first["id"])
    assert previous["review_comment"] == "核对来源后确认"
    assert previous["status"] == "accepted"


@pytest.mark.asyncio
async def test_supplement_invalidates_old_conclusion_without_overwriting_history(domain):
    db, service = domain
    source, case = await make_case(service)
    first = await service("user").analyze_risk(case["id"], RiskAnalyzeRequest())
    await service("expert").review_risk(case["id"], RiskReviewRequest(decision="accept", comment="初次确认"))
    extra = await service("user").create_event(QualityEventCreate(
        record_type="inspection_report", content={"text": "新增实测证据，需要重新核验"},
    ))
    updated = await service("expert").append_risk_sources(case["id"], [extra["id"], extra["id"]])
    assert updated["status"] == "awaiting_evidence"
    assert updated["source_record_ids"] == [source["id"], extra["id"]]
    repeated = await service("expert").append_risk_sources(case["id"], [extra["id"]])
    assert repeated["evidence_ids"] == updated["evidence_ids"]
    old = await service("expert").get_assessment(first["id"])
    assert old["status"] == "accepted" and old["review_comment"] == "初次确认"
    assert old["effective_status"] == "needs_reassessment"
    assert "risk_evidence_set_changed" in {item["code"] for item in old["source_validation"]["blockers"]}
    with pytest.raises(ValidationError):
        await RiskDecisionContextService(db, service("expert").current).accepted(case["id"])
    latest = await service("user").analyze_risk(case["id"], RiskAnalyzeRequest())
    assert latest["version"] == 2
    assert set(latest["evidence_ids"]) == set(updated["evidence_ids"])
    assert len(list(await db.scalars(select(QualityRiskAssessment)))) == 2


@pytest.mark.asyncio
async def test_workspace_hides_removed_sources_and_handles_case_without_assessment(domain):
    db, service = domain
    source, case = await make_case(service)
    row = await db.get(QualitySourceRecord, source["id"])
    row.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.flush()
    workspace = await service("expert").risk_workspace(case["id"])
    assert workspace["records"] == []
    assert workspace["unavailable_source_ids"] == [source["id"]]
    assert workspace["latest_assessment"] is None
    assert workspace["assessment_versions"] == []


@pytest.mark.asyncio
async def test_workspace_and_supplement_enforce_role_tenant_and_source_scope(domain):
    db, service = domain
    source, case = await make_case(service)
    with pytest.raises(ForbiddenError):
        await service("algorithm_engineer").risk_workspace(case["id"])
    foreign = QualityRiskService(db, CurrentUser(user_id=str(uuid4()), org_id=str(uuid4()), role="expert"))
    with pytest.raises(NotFoundError):
        await foreign.risk_workspace(case["id"])
    with pytest.raises(NotFoundError):
        await foreign.append_risk_sources(case["id"], [source["id"]])
    with pytest.raises(NotFoundError):
        await service("expert").append_risk_sources(case["id"], [source["id"], str(uuid4())])
    unchanged = await service("expert").risk_workspace(case["id"])
    assert unchanged["case"]["source_record_ids"] == [source["id"]]
    assert unchanged["case"]["status"] == "collecting"


@pytest.mark.asyncio
async def test_review_rejects_a_concurrently_replaced_version(domain):
    _, service = domain
    _, case = await make_case(service)
    old = await service("user").analyze_risk(case["id"], RiskAnalyzeRequest())
    latest = await service("user").analyze_risk(case["id"], RiskAnalyzeRequest())
    with pytest.raises(ConflictError):
        await service("expert").review_risk(case["id"], RiskReviewRequest(
            assessment_id=old["id"], decision="accept", comment="旧页面中的意见",
        ))
    reviewed = await service("expert").review_risk(case["id"], RiskReviewRequest(
        assessment_id=latest["id"], decision="accept", comment="核对了最新版本",
    ))
    assert reviewed["id"] == latest["id"] and reviewed["status"] == "accepted"


@pytest.mark.asyncio
async def test_mixed_evidence_does_not_make_a_fresh_assessment_stale(domain):
    _, service = domain
    source, case = await make_case(service)
    inference = await service("user").create_event(QualityEventCreate(
        record_type="expert_opinion", data_nature="inferred", content={"text": "辅助解释，不能替代实测证据"},
    ))
    await service("user").append_risk_sources(case["id"], [inference["id"]])
    await service("user").analyze_risk(case["id"], RiskAnalyzeRequest())
    workspace = await service("expert").risk_workspace(case["id"])
    codes = {item["code"] for item in workspace["latest_assessment"]["source_validation"]["blockers"]}
    assert "risk_evidence_set_changed" not in codes
    assert {item["id"] for item in workspace["records"]} == {source["id"], inference["id"]}


@pytest.mark.asyncio
async def test_relinking_existing_source_picks_up_newly_materialized_evidence(domain):
    db, service = domain
    source, case = await make_case(service)
    extra = QualityEvidenceItem(org_id=case["org_id"], source_record_id=source["id"], evidence_code="LATE-EXTRACTION",
        evidence_type="consumer_complaint", text="原始资料后续结构化片段", nature="observed", structured_data={},
        locator={"source_record_id": source["id"]}, content_hash="later-evidence")
    db.add(extra)
    await db.flush()
    result = await service("user").append_risk_sources(case["id"], [source["id"]])
    assert result["source_record_ids"] == [source["id"]]
    assert extra.id in result["evidence_ids"]
    assert result["status"] == "awaiting_evidence"
    assert (await service("user").append_risk_sources(case["id"], [source["id"]]))["evidence_ids"] == result["evidence_ids"]
