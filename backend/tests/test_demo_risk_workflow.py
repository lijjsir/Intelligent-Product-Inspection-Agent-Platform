from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.core.exceptions import ConflictError, ForbiddenError, ValidationError, NotFoundError
from app.core.permissions import PermissionRole
from app.core.quality_demo import DEMO_ORG_SLUG
from app.models.organization import Organization
from app.models.quality_risk import QualityRiskAssessment, QualitySourceRecord, QualityDataSource, QualityEvidenceItem, QualityAttachment
from app.schemas.demo_risk_workflow import DemoDraftCreate, DemoDraftSave, DemoDraftSubmit, DemoDraftReview, DemoDraftContent
from app.schemas.quality_risk import QualityEventCreate, RiskCaseCreate, RiskReviewRequest, RiskAnalyzeRequest
from app.schemas.user import CurrentUser
from app.services.demo_risk_workflow_service import DemoRiskWorkflowService
from app.services.quality_risk_service import QualityRiskService
from app.services.risk_decision_context_service import RiskDecisionContextService
from test_quality_risk_v4 import domain  # noqa: F401


async def setup(domain, monkeypatch):
    db, service = domain
    monkeypatch.setattr(settings, "quality_demo_enabled", True)
    org = await db.get(Organization, service("expert").org_id)
    org.slug, org.settings = DEMO_ORG_SLUG, {"quality_supervision_enabled": True, "execution_mode": "demo"}
    source = await service("expert").create_event(QualityEventCreate(record_type="consumer_complaint", content={"text": "【模拟】温升描述"}))
    case = await service("expert").create_risk_case(RiskCaseCreate(title="演示事项", scope_type="mixed", scope={"execution_mode": "demo"}, source_record_ids=[source["id"]]))
    def workflow(role="expert"):
        return DemoRiskWorkflowService(db, service(role).current)
    return db, service, workflow, case, source


async def create(w, case, base=None, key=None):
    ctx = await w.context(await w.risk.risk_case(case["id"]))
    return await w.create(case["id"], DemoDraftCreate(base_assessment_id=base, request_key=key or uuid4(), expected_basis_hash=ctx["basis_hash"]))


def content(source):
    return DemoDraftContent(summary="【演示】存在待核查温升线索", reasoning="引用原始描述，数量变化需要核查",
        limitations="全部为模拟资料；没有真实温升实测和标准适用核对", cited_record_ids=[source["id"]],
        missing_inputs=["真实检测资料", "标准适用条件"], recommendations=["补充资料后重新研判"], risk_level="unknown")


async def submitted(w, case, source, base=None):
    draft = await create(w, case, base)
    saved = await w.save(case["id"], draft["id"], DemoDraftSave(expected_revision=1, content=content(source)))
    return await w.submit(case["id"], draft["id"], DemoDraftSubmit(expected_revision=saved["demo_workflow"]["revision"]))


@pytest.mark.asyncio
async def test_complete_cycle_history_and_supplement_invalidates_review(domain, monkeypatch):
    db, service, wf, case, source = await setup(domain, monkeypatch)
    first = await submitted(wf(), case, source)
    assert first["status"] == "demo_submitted" and first["probability"] is None
    with pytest.raises(ForbiddenError):
        await wf().review(case["id"], first["id"], DemoDraftReview(expected_revision=3, decision="approve", comment="自审被阻止"))
    reviewed = await wf("expert2").review(case["id"], first["id"], DemoDraftReview(expected_revision=3, decision="approve", comment="已核对本版模拟资料与限制"))
    assert reviewed["status"] == reviewed["trust_status"] == "demo_reviewed"
    assert reviewed["effective_status"] == "demo_reviewed"
    assert reviewed["demo_workflow"]["content"] == first["demo_workflow"]["content"]
    assert reviewed["model_versions"]["llm_called"] is False and "demo_workflow" not in reviewed["model_versions"]
    with pytest.raises(ValidationError):
        await RiskDecisionContextService(db, service("expert").current).accepted(case["id"])
    extra = await service("expert").create_event(QualityEventCreate(record_type="inspection_report", content={"text": "新增模拟验证文字"}))
    await service("expert").append_risk_sources(case["id"], [extra["id"]])
    old = await service("expert").get_assessment(first["id"])
    assert old["status"] == "demo_reviewed" and old["review_comment"] == reviewed["review_comment"]
    assert old["effective_status"] == "needs_reassessment"
    second = await submitted(wf(), case, source, base=first["id"])
    assert second["version"] == 2
    await wf("expert2").review(case["id"], second["id"], DemoDraftReview(expected_revision=3, decision="approve", comment="新版独立复核"))
    workspace = await service("expert").risk_workspace(case["id"])
    assert [v["version"] for v in workspace["assessment_versions"]] == [2, 1]
    assert workspace["latest_assessment"]["demo_workflow"]["events"][-1]["actor_name"] == "expert2"
    assert workspace["demo_context"]["enabled"]
    assert (await service("expert").get_assessment(first["id"]))["review_comment"] == reviewed["review_comment"]


@pytest.mark.asyncio
async def test_saved_draft_refresh_optimistic_revisions_and_idempotent_create(domain, monkeypatch):
    db, service, wf, case, source = await setup(domain, monkeypatch)
    w, key = wf(), uuid4()
    first, again = await create(w, case, key=key), await create(w, case, key=key)
    assert first["id"] == again["id"]
    assert await db.scalar(select(func.count()).select_from(QualityRiskAssessment)) == 1
    with pytest.raises(ConflictError):
        await create(wf(), case, base=first["id"])
    saved = await wf().save(case["id"], first["id"], DemoDraftSave(expected_revision=1, content=content(source)))
    with pytest.raises(ConflictError):
        await wf().save(case["id"], first["id"], DemoDraftSave(expected_revision=1, content=content(source)))
    with pytest.raises(ConflictError):
        await wf().submit(case["id"], first["id"], DemoDraftSubmit(expected_revision=1))
    restored = await service("expert").get_assessment(first["id"])
    assert restored["demo_workflow"]["revision"] == 2 and restored["demo_workflow"]["content"] == saved["demo_workflow"]["content"]


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["revise", "request_evidence"])
async def test_review_returns_to_new_version_without_overwriting(domain, monkeypatch, decision):
    _, service, wf, case, source = await setup(domain, monkeypatch)
    first = await submitted(wf(), case, source)
    returned = await wf("expert2").review(case["id"], first["id"], DemoDraftReview(expected_revision=3, decision=decision, comment="请保留证据缺口并补充说明"))
    assert returned["status"] == "demo_" + decision
    with pytest.raises(ConflictError):
        await wf().save(case["id"], first["id"], DemoDraftSave(expected_revision=4, content=content(source)))
    newer = await create(wf(), case, base=first["id"])
    assert newer["version"] == 2 and newer["reviewed_by"] is None
    with pytest.raises(ConflictError):
        await wf("expert2").review(case["id"], first["id"], DemoDraftReview(expected_revision=4, decision="approve", comment="不能审旧版"))
    assert (await service("expert").get_assessment(first["id"]))["review_comment"] == returned["review_comment"]


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["content", "withdraw", "source", "scope", "authorization"])
async def test_stale_sources_block_submission_and_approval(domain, monkeypatch, change):
    db, _, wf, case, source = await setup(domain, monkeypatch)
    first = await submitted(wf(), case, source)
    row = await db.get(QualitySourceRecord, source["id"])
    if change == "content": row.content = {"text": "改动了原文"}
    elif change == "withdraw": row.deleted_at = datetime.utcnow()
    elif change == "source": (await db.get(QualityDataSource, row.source_id)).status = "inactive"
    elif change == "authorization": row.authorization_scope = "private"
    else:
        target = await wf().risk.risk_case(case["id"])
        target.scope = {**target.scope, "name": "改了范围"}
    await db.flush()
    with pytest.raises(ConflictError):
        await wf("expert2").review(case["id"], first["id"], DemoDraftReview(expected_revision=3, decision="approve", comment="来源变化不得通过"))
    old = await wf("expert2").risk.get_assessment(first["id"])
    assert old["effective_status"] == "needs_reassessment"
    assert old["reviewed_by"] is None


@pytest.mark.asyncio
async def test_permissions_formal_mode_disabled_and_owner_separation(domain, monkeypatch):
    db, service, wf, case, source = await setup(domain, monkeypatch)
    draft = await create(wf(), case)
    with pytest.raises(ForbiddenError):
        await wf("expert2").save(case["id"], draft["id"], DemoDraftSave(expected_revision=1, content=content(source)))
    for role in ("user", "admin", "algorithm_engineer"):
        with pytest.raises(ForbiddenError): await create(wf(role), case, base=draft["id"])
    with pytest.raises(ValidationError):
        await service("expert2").review_risk(case["id"], RiskReviewRequest(decision="accept", comment="不能正式确认"))
    with pytest.raises(ValidationError):
        await service("expert").analyze_risk(case["id"], RiskAnalyzeRequest())
    monkeypatch.setattr(settings, "quality_demo_enabled", False)
    with pytest.raises(ForbiddenError): await create(wf(), case, base=draft["id"])
    with pytest.raises(ValidationError):
        await service("expert2").review_risk(case["id"], RiskReviewRequest(decision="accept", comment="关闭前端演示标识也不能正式确认"))
    monkeypatch.setattr(settings, "quality_demo_enabled", True)
    (await db.get(Organization, case["org_id"])).slug = "ordinary-business"
    await db.flush()
    with pytest.raises(ForbiddenError): await create(wf(), case, base=draft["id"])


@pytest.mark.asyncio
async def test_required_content_citations_and_cross_organization(domain, monkeypatch):
    _, service, wf, case, source = await setup(domain, monkeypatch)
    draft = await create(wf(), case)
    with pytest.raises(ValidationError):
        await wf().submit(case["id"], draft["id"], DemoDraftSubmit(expected_revision=1))
    invalid = content(source).model_copy(update={"cited_record_ids": [str(uuid4())]})
    with pytest.raises(ValidationError):
        await wf().save(case["id"], draft["id"], DemoDraftSave(expected_revision=1, content=invalid))
    with pytest.raises(NotFoundError):
        await wf().create(str(uuid4()), DemoDraftCreate(expected_basis_hash="0"*64, request_key=uuid4()))
    # The content schema cannot forge a probability or a formal acceptance.
    from pydantic import ValidationError as SchemaError
    with pytest.raises(SchemaError): DemoDraftContent(probability=0.8)
    assert (await service("expert").get_assessment(draft["id"]))["status"] == "demo_draft"


@pytest.mark.asyncio
async def test_changed_draft_cannot_save_or_submit_and_new_version_preserves_it(domain, monkeypatch):
    db, service, wf, case, source = await setup(domain, monkeypatch)
    draft = await create(wf(), case)
    saved = await wf().save(case["id"], draft["id"], DemoDraftSave(expected_revision=1, content=content(source)))
    row = await db.get(QualitySourceRecord, source["id"])
    row.provenance = {**row.provenance, "object_binding_version": 1}
    await db.flush()
    with pytest.raises(ConflictError):
        await wf().submit(case["id"], draft["id"], DemoDraftSubmit(expected_revision=2))
    with pytest.raises(ConflictError):
        await wf().save(case["id"], draft["id"], DemoDraftSave(expected_revision=2, content=content(source)))
    newer = await create(wf(), case, base=draft["id"])
    assert newer["version"] == 2 and newer["demo_workflow"]["content"] == saved["demo_workflow"]["content"]
    assert (await service("expert").get_assessment(draft["id"]))["effective_status"] == "needs_reassessment"


@pytest.mark.asyncio
async def test_new_fragment_and_synthetic_enforcement(domain, monkeypatch):
    db, _, wf, case, source = await setup(domain, monkeypatch)
    first = await submitted(wf(), case, source)
    db.add(QualityEvidenceItem(org_id=case["org_id"], source_record_id=source["id"], evidence_code="LATE-DEMO",
        evidence_type="consumer_complaint", text="【模拟】新片段", nature="synthetic", structured_data={}, locator={}, content_hash="late"))
    await db.flush()
    with pytest.raises(ConflictError):
        await wf("expert2").review(case["id"], first["id"], DemoDraftReview(expected_revision=3, decision="approve", comment="新增片段必须重评"))
    returned = await wf("expert2").review(case["id"], first["id"], DemoDraftReview(expected_revision=3, decision="request_evidence", comment="请针对新片段重提"))
    assert returned["status"] == "demo_request_evidence"
    (await db.get(QualitySourceRecord, source["id"])).data_nature = "observed"
    await db.flush()
    with pytest.raises(ValidationError): await create(wf(), case, base=first["id"])


@pytest.mark.asyncio
async def test_live_permission_revocation_and_cross_org_case(domain, monkeypatch):
    db, service, wf, case, source = await setup(domain, monkeypatch)
    draft = await create(wf(), case)
    reviewer = wf("expert2")
    reviewer.current.role = PermissionRole("expert", set())
    with pytest.raises(ForbiddenError): await reviewer.context(await reviewer.risk.risk_case(case["id"]))
    target = await wf().risk.risk_case(case["id"])
    target.org_id = str(uuid4())
    await db.flush()
    with pytest.raises(NotFoundError):
        await wf().submit(case["id"], draft["id"], DemoDraftSubmit(expected_revision=1))


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["missing", "tampered"])
async def test_demo_review_checks_real_attachment_bytes(domain, monkeypatch, change):
    import hashlib
    db, service, wf, case, source = await setup(domain, monkeypatch)
    data = b"explicit simulated text, no real measurement"
    class Storage:
        value = (data, "text/plain")
        def get_bytes(self, **kwargs): return self.value
    storage = Storage()
    attachment = QualityAttachment(org_id=case["org_id"], file_name="simulated.txt", mime_type="text/plain", size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(), bucket="quality-demo-business", object_key="demo-verification.txt", uploaded_by=service("expert").actor)
    db.add(attachment)
    await db.flush()
    (await db.get(QualitySourceRecord, source["id"])).attachment_ids = [attachment.id]
    await db.flush()
    author = DemoRiskWorkflowService(db, service("expert").current, storage)
    first = await submitted(author, case, source)
    # Storage locators and full frozen bases never appear in public workflow DTOs.
    import json
    assert "object_key" not in json.dumps(first, default=str)
    storage.value = None if change == "missing" else (b"changed bytes", "text/plain")
    reviewer = DemoRiskWorkflowService(db, service("expert2").current, storage)
    with pytest.raises(ConflictError):
        await reviewer.review(case["id"], first["id"], DemoDraftReview(expected_revision=3, decision="approve", comment="不能确认变动的附件"))
    check = await reviewer.respond(await reviewer.risk.risk_case(case["id"]), await db.get(QualityRiskAssessment, first["id"]))
    assert "demo_attachment_unavailable" in {b["code"] for b in check["demo_validation"]["blockers"]}


@pytest.mark.asyncio
async def test_deleted_draft_never_reuses_its_version_and_citations_deduplicate(domain, monkeypatch):
    db, _, wf, case, source = await setup(domain, monkeypatch)
    first = await create(wf(), case)
    (await db.get(QualityRiskAssessment, first["id"])).deleted_at = datetime.utcnow()
    await db.flush()
    second = await create(wf(), case)
    assert second["version"] == second["demo_workflow"]["events"][0]["version"] == 2
    assert DemoDraftContent(cited_record_ids=[source["id"], source["id"]]).model_dump(mode="json")["cited_record_ids"] == [source["id"]]
