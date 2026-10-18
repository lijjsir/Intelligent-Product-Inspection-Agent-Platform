from datetime import datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import DateTime, DefaultClause, MetaData, func, select, text

from app.core.exceptions import ConflictError, ForbiddenError, ValidationError, NotFoundError
from app.models import Base
from app.models.collab import CollabMessage
from app.models.meeting import MeetingRoom, MeetingMessage, MeetingRoomMember
from app.models.quality_risk import QualityRiskAssessment
from app.models.supervision import SupervisionRecord
from app.models.user import User
from app.schemas.risk_collaboration import RiskCollaborationCreate
from app.schemas.collab import CollabMessageActionRequest, CollabMessageCreateRequest
from app.schemas.meeting import MeetingAgentRunRequest
from app.schemas.quality_risk import QualityEventCreate
from app.services.collab_service import CollabService
from app.services.meeting_service import MeetingService
from app.services.risk_collaboration_service import RiskCollaborationService
from test_quality_risk_v4 import domain  # noqa: F401
from test_demo_risk_workflow import setup, submitted, create


@pytest_asyncio.fixture
async def collaboration(domain, monkeypatch):
    db, service, wf, case, source = await setup(domain, monkeypatch)
    metadata = MetaData()
    for name in ("meeting_rooms", "meeting_room_members", "meeting_messages", "collab_threads", "collab_thread_participants",
                 "collab_messages", "collab_message_receipts", "message_attachments", "file_assets"):
        table = Base.metadata.tables[name].to_metadata(metadata)
        for column in table.c:
            column.server_default = DefaultClause(text("CURRENT_TIMESTAMP")) if isinstance(column.type, DateTime) and column.server_default is not None else None
    async with db.bind.begin() as conn:
        await conn.run_sync(metadata.create_all)
    async def noop(*args, **kwargs): pass
    from app.services import meeting_service, collab_service
    monkeypatch.setattr(meeting_service.meeting_stream_broker, "publish", noop)
    monkeypatch.setattr(collab_service.collab_stream_broker, "publish", noop)
    for method in ("_publish_work_item_event", "_publish_message_created", "_publish_receipt_updated"):
        monkeypatch.setattr(CollabService, method, noop)
    assessment = await submitted(wf(), case, source)
    def svc(role="expert"):
        return RiskCollaborationService(db, service(role).current)
    payload = RiskCollaborationCreate(assessment_id=assessment["id"], expected_basis_hash=assessment["demo_validation"]["basis_hash"],
        request_key=uuid4(), coordinator_id=service("expert2").actor, purpose="【演示】核对资料范围和温升证据缺口")
    return db, service, wf, case, source, assessment, svc, payload


@pytest.mark.asyncio
async def test_atomic_version_binding_reuse_and_native_work_item(collaboration):
    db, service, wf, case, source, assessment, svc, payload = collaboration
    first = await svc().create(case["id"], payload)
    again = await svc().create(case["id"], payload)
    assert first["id"] == again["id"] and again["reused"]
    assert await db.scalar(select(func.count()).select_from(MeetingRoom)) == 1
    assert first["assessment_id"] == assessment["id"] and first["assessment_version"] == assessment["version"]
    room = await db.get(MeetingRoom, first["room_id"])
    assert room.visibility == "restricted" and room.audit_policy["auto_participation_mode"] == "off"
    assert room.memory_policy["business_context"]["risk_assessment_id"] == assessment["id"]
    peer = CollabService(db, service("expert2").org_id, service("expert2").actor, role="expert")
    items = await peer.list_work_items(view="pending", item_type="action_request")
    assert len(items) == 1 and items[0].payload["source_context"]["risk_assessment_id"] == assessment["id"]
    assert "assessment_id=" + assessment["id"] in items[0].source_link
    assert first["id"] == (await svc("expert2").list_for_case(case["id"]))[0]["id"]
    assert (await wf().risk.get_assessment(assessment["id"]))["status"] == "demo_submitted"


@pytest.mark.asyncio
async def test_discussion_returns_to_case_and_private_text_is_excluded(collaboration):
    db, service, wf, case, _, assessment, svc, payload = collaboration
    link = await svc().create(case["id"], payload)
    peer = MeetingService(db, service("expert2").org_id, service("expert2").actor, role="expert")
    public = await peer.send_message(link["room_id"], "公开意见：@会议Agent 仍需真实测量，本房间只保留人工讨论")
    await peer.send_message(link["room_id"], "私聊仅本人和收件人可见", private_recipient_user_id=service("expert").actor)
    collab = CollabService(db, service("expert2").org_id, service("expert2").actor, role="expert")
    note = await collab.send_work_item_comment(link["thread_id"], CollabMessageCreateRequest(content="请求评论：需保留概率未知", reply_to_message_id=link["message_id"]))
    detail = await svc().get(link["id"])
    assert [m["id"] for m in detail["discussion"]] == [public.id]
    assert detail["comments"][0]["id"] == note.id
    assert (await wf().risk.get_assessment(assessment["id"]))["reviewed_by"] is None
    assert await db.scalar(select(func.count()).select_from(QualityRiskAssessment)) == 1
    from app.services.knowledge_source_service import KnowledgeSourceService
    with pytest.raises(ValidationError):
        await KnowledgeSourceService(db, service("expert").current).resolve("meeting_message", public.id)


@pytest.mark.asyncio
async def test_native_room_code_cannot_bypass_participation_or_scope(collaboration):
    db, service, wf, case, _, _, svc, payload = collaboration
    link = await svc().create(case["id"], payload)
    outsider = service("user")
    # Even an actual room code does not grant membership to an uninvited user.
    room = await db.get(MeetingRoom, link["room_id"])
    with pytest.raises(ForbiddenError):
        await MeetingService(db, outsider.org_id, outsider.actor, role="user").join_room(room.access_code)
    with pytest.raises(ForbiddenError): await svc("admin").get(link["id"])
    participant = await db.scalar(select(MeetingRoomMember).where(MeetingRoomMember.room_id == room.id, MeetingRoomMember.user_id == service("expert2").actor))
    participant.deleted_at = datetime.utcnow()
    await db.flush()
    with pytest.raises(ForbiddenError): await svc("expert2").get(link["id"])
    with pytest.raises(ForbiddenError):
        await CollabService(db, outsider.org_id, service("expert2").actor, role="expert").list_messages(link["thread_id"])
    assert await svc("expert2").list_for_case(case["id"]) == []


@pytest.mark.asyncio
async def test_foreign_inactive_self_and_draft_invitations_are_rejected(collaboration):
    db, service, wf, case, _, assessment, svc, payload = collaboration
    for uid in (service("expert").actor, service("admin").actor, str(uuid4())):
        with pytest.raises(ValidationError):
            await svc().create(case["id"], payload.model_copy(update={"coordinator_id": uid}))
    (await db.get(User, service("expert2").actor)).is_active = False
    await db.flush()
    with pytest.raises(ValidationError): await svc().create(case["id"], payload)
    assert await db.scalar(select(func.count()).select_from(MeetingRoom)) == 0


@pytest.mark.asyncio
async def test_linked_context_cannot_be_rebound_and_ai_is_disabled(collaboration):
    db, service, wf, case, _, assessment, svc, payload = collaboration
    link = await svc().create(case["id"], payload)
    meeting = MeetingService(db, service("expert").org_id, service("expert").actor, role="expert")
    with pytest.raises(ValidationError): await meeting.update_room_settings(link["room_id"], business_context={})
    with pytest.raises(ValidationError): await meeting.update_room_settings(link["room_id"], visibility="org")
    with pytest.raises(ValidationError): await meeting.update_room_settings(link["room_id"], auto_participation_mode="live")
    with pytest.raises(ValidationError): await meeting.run_general_agent(link["room_id"], MeetingAgentRunRequest(query="分析风险"))
    with pytest.raises(ValidationError): await meeting.create_room("伪造绑定", business_context={"risk_case_id": case["id"]})
    with pytest.raises(ValidationError): await meeting.add_agent_to_room(link["room_id"], "general")
    with pytest.raises(ValidationError): await meeting.update_member_role(link["room_id"], service("expert2").actor, "member")
    with pytest.raises(ValidationError): await meeting.delete_room(link["room_id"])


@pytest.mark.asyncio
async def test_receipt_progress_never_changes_independent_review(collaboration):
    db, service, wf, case, _, assessment, svc, payload = collaboration
    link = await svc().create(case["id"], payload)
    author = CollabService(db, service("expert").org_id, service("expert").actor, role="expert")
    peer = CollabService(db, service("expert2").org_id, service("expert2").actor, role="expert")
    with pytest.raises(ForbiddenError): await author.update_action(link["message_id"], CollabMessageActionRequest(action_status="done"))
    await peer.update_action(link["message_id"], CollabMessageActionRequest(action_status="accepted", decision_note="同意参与"))
    accepted = await peer.list_work_items(view="processed", item_type="action_request")
    assert accepted[0].allowed_actions == ["done"]
    await peer.update_action(link["message_id"], CollabMessageActionRequest(action_status="done", decision_note="已返回讨论意见"))
    assert (await svc().get(link["id"]))["status"] == "done"
    assert (await wf().risk.get_assessment(assessment["id"]))["status"] == "demo_submitted"
    assert (await wf().risk.get_assessment(assessment["id"]))["reviewed_by"] is None


@pytest.mark.asyncio
async def test_supplement_and_new_versions_keep_original_discussion_link(collaboration):
    db, service, wf, case, source, assessment, svc, payload = collaboration
    first = await svc().create(case["id"], payload)
    extra = await service("expert").create_event(QualityEventCreate(record_type="inspection_report", content={"text": "新增模拟片段"}))
    await service("expert").append_risk_sources(case["id"], [extra["id"]])
    with pytest.raises(ConflictError): await svc().create(case["id"], payload)
    newer = await submitted(wf(), case, source, base=assessment["id"])
    assert newer["version"] == 2
    old = await svc().get(first["id"])
    assert old["assessment_id"] == assessment["id"] and not old["basis_current"] and not old["is_latest"]
    second = await svc().create(case["id"], payload.model_copy(update={"assessment_id": newer["id"], "expected_basis_hash": newer["demo_validation"]["basis_hash"]}))
    assert second["id"] != first["id"] and len(await svc().list_for_case(case["id"])) == 2
