import copy
from datetime import datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.core.config import settings
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.models.meeting import MeetingMessage, MeetingRoomMember
from app.models.organization import Organization
from app.models.quality_risk import QualitySourceRecord
from app.models.supervision import SupervisionRecord
from app.schemas.collab import CollabMessageActionRequest
from app.schemas.demo_risk_workflow import DemoDraftReview
from app.schemas.demo_sampling import DemoSamplingCreate, DemoSamplingSave, DemoSamplingConfirm, DemoSamplingContent
from app.schemas.user import CurrentUser
from app.services.collab_service import CollabService
from app.services.demo_sampling_service import DemoSamplingService, KIND
from app.services.meeting_service import MeetingService
from app.services.risk_decision_context_service import RiskDecisionContextService
from test_quality_risk_v4 import domain  # noqa: F401
from test_risk_collaboration import collaboration  # noqa: F401


@pytest_asyncio.fixture
async def sampling(collaboration):
    db, service, wf, case, source, assessment, collab, payload = collaboration
    link = await collab().create(case["id"], payload)
    await wf("expert2").review(case["id"], assessment["id"], DemoDraftReview(expected_revision=3, decision="approve", comment="核对模拟来源与限制"))
    peer = CollabService(db, service("expert2").org_id, service("expert2").actor, role="expert")
    await peer.update_action(link["message_id"], CollabMessageActionRequest(action_status="accepted", decision_note="接受讨论"))
    await peer.update_action(link["message_id"], CollabMessageActionRequest(action_status="done", decision_note="仅建议补充真实测量"))
    meeting = MeetingService(db, service("expert2").org_id, service("expert2").actor, role="expert")
    public = await meeting.send_message(link["room_id"], "【模拟公开】应核实温升与标准")
    await meeting.send_message(link["room_id"], "私密内容不带入建议", private_recipient_user_id=service("expert").actor)
    def svc(role="expert"):
        return DemoSamplingService(db, service(role).current)
    candidate = (await svc().candidates(case["id"]))["items"][0]
    create = DemoSamplingCreate(assessment_id=assessment["id"], collaboration_id=link["id"], expected_context_hash=candidate["context_hash"])
    return db, service, wf, case, source, assessment, link, public, svc, create


def content():
    return DemoSamplingContent(rationale="【演示】投诉和舆情集中出现温升描述", focus="核查型号与使用条件，补充温升验证资料", limitations="模拟资料；数量、批次、地点、时间未知，真实标准适用性待核实")


@pytest.mark.asyncio
async def test_demo_suggestion_freezes_review_and_public_feedback_only(sampling):
    db, service, wf, case, source, assessment, link, public, svc, create = sampling
    first = await svc().create(case["id"], create)
    again = await svc().create(case["id"], create)
    assert first["id"] == again["id"] and again["reused"]
    assert await db.scalar(select(func.count()).select_from(SupervisionRecord).where(SupervisionRecord.kind == KIND)) == 1
    assert first["snapshot"]["assessment_id"] == assessment["id"]
    assert first["snapshot"]["review"]["reviewed_by"] == service("expert2").actor
    assert [m["id"] for m in first["snapshot"]["opinions"]] == [public.id]
    assert "私密内容" not in str(first)
    assert first["snapshot"]["llm_called"] is False
    saved = await svc().mutate(first["id"], DemoSamplingSave(expected_revision=1, content=content()))
    assert saved["revision"] == 2 and saved["content"]["sample_quantity"] is None
    assert (await svc().get(first["id"]))["content"] == saved["content"]
    confirmed = await svc().mutate(first["id"], DemoSamplingConfirm(expected_revision=2), confirm=True)
    assert confirmed["status"] == "demo_confirmed" and not confirmed["can_edit"]
    assert [e["action"] for e in confirmed["events"]] == ["created", "saved", "confirmed"]
    with pytest.raises(ConflictError): await svc().mutate(first["id"], DemoSamplingSave(expected_revision=3, content=content()))
    assert (await wf().risk.get_assessment(assessment["id"]))["status"] == "demo_reviewed"
    assert (await RiskDecisionContextService(db, service("expert").current).eligible())[0] == []
    assert not await db.scalar(select(SupervisionRecord.id).where(SupervisionRecord.kind == "sampling-plans"))


@pytest.mark.asyncio
async def test_revision_empty_confirm_and_other_author_blocked(sampling):
    _, _, _, case, _, _, _, _, svc, create = sampling
    first = await svc().create(case["id"], create)
    with pytest.raises(ValidationError): await svc().mutate(first["id"], DemoSamplingConfirm(expected_revision=1), confirm=True)
    with pytest.raises(ForbiddenError): await svc("expert2").mutate(first["id"], DemoSamplingSave(expected_revision=1, content=content()))
    await svc().mutate(first["id"], DemoSamplingSave(expected_revision=1, content=content()))
    with pytest.raises(ConflictError): await svc().mutate(first["id"], DemoSamplingSave(expected_revision=1, content=content()))
    assert (await svc("expert2").get(first["id"]))["can_edit"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["source", "public", "recalled", "removed", "review"])
async def test_changed_basis_retains_original_and_blocks_confirmation(sampling, change):
    db, _, _, case, source, assessment, _, public, svc, create = sampling
    first = await svc().create(case["id"], create)
    frozen = copy.deepcopy(first["snapshot"])
    public = await db.get(MeetingMessage, public.id)
    if change == "source":
        (await db.get(QualitySourceRecord, source["id"])).deleted_at = datetime.utcnow()
    elif change == "public": public.content = "公开意见已更正"
    elif change == "recalled": public.metadata_json = {**(public.metadata_json or {}), "recalled_at": datetime.utcnow().isoformat()}
    elif change == "removed": public.deleted_at = datetime.utcnow()
    else:
        from app.models.quality_risk import QualityRiskAssessment
        (await db.get(QualityRiskAssessment, assessment["id"])).review_comment = "复核意见变更"
    await db.flush()
    stale = await svc().get(first["id"])
    assert stale["snapshot"] == frozen and stale["effective_status"] == "needs_reassessment"
    with pytest.raises(ConflictError): await svc().mutate(first["id"], DemoSamplingConfirm(expected_revision=1), confirm=True)
    with pytest.raises(ConflictError): await svc().create(case["id"], create)
    if change != "source":
        current = (await svc().candidates(case["id"]))["items"][0]
        new = await svc().create(case["id"], create.model_copy(update={"expected_context_hash": current["context_hash"]}))
        assert new["id"] != first["id"] and len(await svc().list()) == 2


@pytest.mark.asyncio
async def test_authorization_environment_foreign_and_removed_member(sampling, monkeypatch):
    db, service, _, case, _, _, link, _, svc, create = sampling
    first = await svc().create(case["id"], create)
    with pytest.raises(ForbiddenError): await svc("admin").get(first["id"])
    with pytest.raises(ForbiddenError): await svc("user").candidates()
    foreign = str(uuid4())
    # A true second organization must not list or resolve this suggestion.
    db.add(Organization(id=foreign, name="其它单位", slug="foreign", settings={"quality_supervision_enabled": True}, is_active=True))
    await db.flush()
    other = DemoSamplingService(db, CurrentUser(user_id=service("expert").actor, org_id=foreign, role="expert"))
    with pytest.raises(ForbiddenError): await other.get(first["id"])
    with pytest.raises(NotFoundError): await svc().get(str(uuid4()))
    member = await db.scalar(select(MeetingRoomMember).where(MeetingRoomMember.room_id == link["room_id"], MeetingRoomMember.user_id == service("expert2").actor))
    member.deleted_at = datetime.utcnow(); await db.flush()
    with pytest.raises(ForbiddenError): await svc("expert2").get(first["id"])
    assert await svc("expert2").list() == []
    monkeypatch.setattr(settings, "quality_demo_enabled", False)
    with pytest.raises(ForbiddenError): await svc().get(first["id"])


@pytest.mark.asyncio
async def test_unreviewed_or_incomplete_collaboration_not_candidate(collaboration):
    db, service, _, case, _, assessment, collab, payload = collaboration
    await collab().create(case["id"], payload)
    svc = DemoSamplingService(db, service("expert").current)
    result = await svc.candidates(case["id"])
    assert result["items"] == [] and result["blockers"]
    from app.services.demo_risk_workflow_service import DemoRiskWorkflowService
    await DemoRiskWorkflowService(db, service("expert2").current).review(case["id"], assessment["id"], DemoDraftReview(expected_revision=3, decision="approve", comment="演示核对"))
    result = await svc.candidates(case["id"])
    assert result["items"] == [] and "完成" in result["blockers"][0]


@pytest.mark.asyncio
async def test_new_assessment_keeps_confirmed_suggestion_on_original_version(sampling):
    _, _, wf, case, _, assessment, _, _, svc, payload = sampling
    from test_demo_risk_workflow import create
    first = await svc().create(case["id"], payload)
    await svc().mutate(first["id"], DemoSamplingSave(expected_revision=1, content=content()))
    fixed = await svc().mutate(first["id"], DemoSamplingConfirm(expected_revision=2), confirm=True)
    newer = await create(wf(), case, base=assessment["id"])
    assert newer["version"] == 2
    old = await svc().get(first["id"])
    assert old["status"] == "demo_confirmed" and old["effective_status"] == "needs_reassessment"
    assert old["snapshot"] == fixed["snapshot"] and old["content"] == fixed["content"]
    assert old["confirmed_at"] == fixed["confirmed_at"]
    assert (await svc().candidates(case["id"]))["items"] == []
