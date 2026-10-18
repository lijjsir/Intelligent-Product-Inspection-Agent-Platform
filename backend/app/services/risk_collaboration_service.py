"""Same-organization, version-pinned demo discussions using meetings and work items."""
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from app.core.config import settings
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.permissions import require_role
from app.models.collab import CollabMessage, CollabMessageReceipt
from app.models.meeting import MeetingRoom, MeetingRoomMember, MeetingMessage
from app.models.quality_risk import QualityRiskAssessment
from app.models.supervision import SupervisionRecord
from app.models.user import User
from app.repositories.collab_repo import CollabRepository
from app.repositories.meeting_repo import MeetingRepository
from app.schemas.meeting import MeetingBusinessContext
from app.schemas.user import CurrentUser
from app.services.demo_risk_workflow_service import DemoRiskWorkflowService, is_manual_demo
from app.services.risk_workflow_context_service import RiskWorkflowContextService
from app.services.quality_risk_service import stable_hash

KIND = "risk-collaborations"
MARKER = "risk_collaboration_id"


def bound_id(room):
    return (getattr(room, "memory_policy", None) or {}).get(MARKER)


async def check_room_access(db, org_id, user_id, role, room):
    """Run from native meeting/collab entry points, not only the case panel."""
    link_id = bound_id(room)
    if not link_id:
        return None
    current = CurrentUser(user_id=user_id, org_id=org_id, role=str(role))
    current.role = role  # Preserve effective permissions carried by PermissionRole.
    service = RiskCollaborationService(db, current)
    await service.guard()
    link = await db.scalar(select(SupervisionRecord).where(SupervisionRecord.id == link_id,
        SupervisionRecord.org_id == org_id, SupervisionRecord.kind == KIND))
    if not link or link.data.get("room_id") != str(room.id) or user_id not in link.data.get("participant_ids", []):
        raise ForbiddenError("不是本次研判协同的受邀专家")
    if link.data.get('execution_mode','demo') != service.demo.mode:
        raise ForbiddenError('该协同不属于当前业务环境')
    member = await db.scalar(select(MeetingRoomMember).where(MeetingRoomMember.org_id == org_id,
        MeetingRoomMember.room_id == room.id, MeetingRoomMember.user_id == user_id, MeetingRoomMember.deleted_at.is_(None)))
    if not member:
        raise ForbiddenError("当前账号已不在本次协同范围")
    await service.demo.risk.risk_case(link.data["case_id"])
    assessment = await db.scalar(select(QualityRiskAssessment.id).where(QualityRiskAssessment.id == link.data["assessment_id"],
        QualityRiskAssessment.org_id == org_id, QualityRiskAssessment.risk_case_id == link.data["case_id"],
        QualityRiskAssessment.deleted_at.is_(None)))
    if not assessment:
        raise ForbiddenError("协同关联的研判版本已不可访问")
    return link


class RiskCollaborationService:
    def __init__(self, db, current):
        self.db, self.current = db, current
        self.org_id, self.actor = str(current.org_id), str(current.user_id)
        self.demo = RiskWorkflowContextService(db, current)
        self.meetings, self.collab = MeetingRepository(db), CollabRepository(db)

    async def guard(self, write=False):
        actor = await self.demo.guard(write=write)
        if str(self.current.role) != "expert":
            raise ForbiddenError("本轮同单位研判协同向受邀专家开放")
        require_role("meeting", self.current.role)
        require_role("collab", self.current.role)
        return actor

    async def candidates(self):
        await self.guard()
        users = await self.db.scalars(select(User).where(User.org_id == self.org_id, User.is_active.is_(True),
            User.role == "expert", User.id != self.actor).order_by(User.username))
        return [{"id": u.id, "name": u.username} for u in users]

    @staticmethod
    def fingerprint(row):
        if not is_manual_demo(row):
            return stable_hash({key:getattr(row,key) for key in ('id','version','scope','risk_type','risk_level','evidence_ids','standard_matches','missing_inputs','possible_causes','recommendations','model_versions','reviewed_by','reviewed_at','review_comment')})
        return stable_hash({"id": row.id, "version": row.version, "scope": row.scope,
            "content": (row.model_versions or {}).get("demo_workflow", {}).get("content"),
            "basis_hash": (row.model_versions or {}).get("demo_workflow", {}).get("basis_hash")})

    async def create(self, case_id, payload):
        actor = await self.guard(write=True)
        case = await self.demo.risk.risk_case(case_id, lock=True)
        assessment = await self.demo.latest(case)
        if not assessment or assessment.id != str(payload.assessment_id):
            raise ConflictError("研判已有新版本，请核对最新提交版本后发起协同")
        if self.demo.is_demo and (not is_manual_demo(assessment) or assessment.status == "demo_draft"):
            raise ValidationError("请先提交人工演示研判，再基于锁定内容发起协同")
        if not self.demo.is_demo:
            await self.demo.ensure_current(case, assessment)
        validation = await self.demo.validation(case, assessment)
        if not validation["is_current"] or validation["basis_hash"] != payload.expected_basis_hash:
            raise ConflictError("研判依据已变化，请先重评并提交新版")
        coordinator = str(payload.coordinator_id)
        if coordinator == self.actor:
            raise ValidationError("请选择另一位同单位专家作为协同负责人")
        members = sorted({self.actor, coordinator, *map(str, payload.participant_ids)})
        users = list(await self.db.scalars(self.demo.read(select(User).where(User.org_id == self.org_id,
            User.id.in_(members), User.is_active.is_(True), User.role == "expert"))))
        if {u.id for u in users} != set(members):
            raise ValidationError("参与人须为本单位仍有效的专家账号，不能跨单位邀请")
        code = assessment.id  # Existing tenant/kind/code unique constraint.
        existing = await self.db.scalar(self.demo.read(select(SupervisionRecord).where(
            SupervisionRecord.org_id == self.org_id, SupervisionRecord.kind == KIND, SupervisionRecord.code == code)))
        if existing:
            if self.actor not in existing.data["participant_ids"]:
                raise ForbiddenError("本版本已有其他专家发起的协同，当前账号未受邀")
            if existing.data["assessment_hash"] != self.fingerprint(assessment):
                raise ConflictError("原协同固定的版本内容已变化，请创建新版研判")
            if existing.data["coordinator_id"] != coordinator or existing.data["participant_ids"] != members:
                raise ConflictError("本版本已有固定参与范围的协同，请进入原讨论")
            if existing.data["purpose"] != payload.purpose:
                raise ConflictError("本版本的协同议题已固定，新的意见请在原讨论中补充")
            return {**await self.serialize(existing), "reused": True}
        link_id = str(uuid5(NAMESPACE_URL, f"risk-collaboration:{self.org_id}:{assessment.id}"))
        mode = self.demo.mode
        context = MeetingBusinessContext(risk_case_id=case.id, risk_assessment_id=assessment.id,
            risk_assessment_version=assessment.version, execution_mode=mode)
        title = f"【{'演示协同' if self.demo.is_demo else '研判协同'}】{case.code} · 第{assessment.version}版"
        # All repositories flush only; the enclosing API transaction commits
        # the room, invitations, work item and mapping together.
        room = await self.meetings.create_room(org_id=self.org_id, user_id=self.actor, title=title[:120],
            access_code=link_id.replace("-", "")[:16].upper(), password_hash=None, visibility="restricted",
            allowed_data_domains=["quality"], memory_policy={MARKER: link_id, "business_context": context.model_dump(mode="json"),
                "candidate_default_scope": "meeting_room", "publish_requires_confirmation": True},
            audit_policy={"enabled": True, "auto_participation_mode": "off", "manual_risk_collaboration": True})
        for uid in members:
            if uid != self.actor:
                await self.meetings.add_member(org_id=self.org_id, room_id=room.id, user_id=uid,
                    role="host" if uid == coordinator else "member")
        thread = await self.collab.create_thread(org_id=self.org_id, thread_type="group", source_type="user", source_id=self.actor,
            target_type="meeting_room", target_id=room.id, title=title, created_by=self.actor, metadata_json={MARKER: link_id})
        for uid in members:
            await self.collab.add_participant(org_id=self.org_id, thread_id=thread.id, participant_type="user", participant_id=uid)
        origin = {"kind": "risk_assessment", "risk_case_id": case.id, "case_code": case.code,
            "risk_assessment_id": assessment.id, "risk_assessment_version": assessment.version,
            "execution_mode": mode, "collaboration_id": link_id, "room_id": room.id,
            "source_link": f"/app/risk-assessments?case_id={case.id}&assessment_id={assessment.id}&tab=collaboration"}
        description = f"【{'演示' if self.demo.is_demo else ''}同单位协同】{payload.purpose}\n固定事项 {case.code} 第 {assessment.version} 版。协同意见与独立复核分别记录。"
        message = await self.collab.create_message(org_id=self.org_id, thread_id=thread.id, sender_type="user", sender_id=self.actor,
            message_type="action_request", content=description, metadata_json={"source_context": origin,
                "source_link": origin["source_link"], "action_request": {"title": title, "description": description,
                    "source_context": origin, "source_link": origin["source_link"]}})
        for uid in members:
            if uid != self.actor:
                await self.collab.create_receipt(org_id=self.org_id, message_id=message.id, thread_id=thread.id,
                    recipient_type="user", recipient_id=uid, delivered_at=datetime.utcnow())
        link = SupervisionRecord(id=link_id, org_id=self.org_id, kind=KIND, code=code, name=title, status="active", version=1,
            created_by=self.actor, data={**origin, "case_id": case.id, "assessment_id": assessment.id,
                "assessment_version": assessment.version, "assessment_hash": self.fingerprint(assessment),
                "basis_hash": validation["basis_hash"], "room_id": room.id, "thread_id": thread.id, "message_id": message.id,
                "coordinator_id": coordinator, "participant_ids": members, "participant_names": {u.id: u.username for u in users},
                "purpose": payload.purpose, "request_key": str(payload.request_key)})
        self.db.add(link)
        await self.db.flush()
        return {**await self.serialize(link), "reused": False}

    async def list_for_case(self, case_id):
        await self.guard()
        await self.demo.risk.risk_case(case_id)
        rows = await self.db.scalars(select(SupervisionRecord).where(SupervisionRecord.org_id == self.org_id,
            SupervisionRecord.kind == KIND).order_by(SupervisionRecord.created_at.desc()))
        result = []
        for row in rows:
            if row.data.get("case_id") == case_id and row.data.get('execution_mode','demo') == self.demo.mode and self.actor in row.data.get("participant_ids", []):
                member = await self.meetings.get_member(self.org_id, row.data["room_id"], self.actor)
                if member:
                    result.append(await self.serialize(row))
        return result

    async def get(self, link_id):
        await self.guard()
        row = await self.db.scalar(select(SupervisionRecord).where(SupervisionRecord.id == link_id,
            SupervisionRecord.org_id == self.org_id, SupervisionRecord.kind == KIND))
        if not row:
            raise NotFoundError("研判协同不存在")
        room = await self.meetings.get_room(self.org_id, row.data["room_id"])
        if not room:
            raise NotFoundError("关联会议室已不可用")
        if bound_id(room) != row.id:
            raise ForbiddenError('协同与会议室的关联已变化，请重新核对访问范围')
        await check_room_access(self.db, self.org_id, self.actor, self.current.role, room)
        return await self.serialize(row, details=True)

    async def serialize(self, link, details=False):
        data = link.data
        case = await self.demo.risk.risk_case(data["case_id"])
        assessment = await self.db.scalar(select(QualityRiskAssessment).where(QualityRiskAssessment.org_id == self.org_id,
            QualityRiskAssessment.id == data["assessment_id"], QualityRiskAssessment.deleted_at.is_(None)))
        if not assessment:
            raise NotFoundError("协同关联的研判版本已不可用")
        validation = await self.demo.validation(case, assessment)
        latest = await self.demo.latest(case)
        receipts = (await self.collab.list_receipts(self.org_id, [data["message_id"]])).get(data["message_id"], [])
        coordinator = next((r for r in receipts if r.recipient_id == data["coordinator_id"]), None)
        room = await self.meetings.get_room(self.org_id, data["room_id"])
        request = await self.collab.get_message(self.org_id, data["message_id"])
        result = {"id": link.id, "title": link.name, "case_id": case.id, "case_code": case.code,
            "assessment_id": assessment.id, "assessment_version": assessment.version,
            "is_latest": bool(latest and latest.id == assessment.id),
            "basis_current": validation["is_current"] and data["assessment_hash"] == self.fingerprint(assessment),
            "execution_mode": data.get('execution_mode','demo'), "purpose": data["purpose"], "created_by": link.created_by,
            "created_at": link.created_at, "room_id": data["room_id"], "thread_id": data["thread_id"],
            "message_id": data["message_id"], "coordinator_id": data["coordinator_id"],
            "participants": [{"id": uid, "name": data["participant_names"].get(uid, "专家")} for uid in data["participant_ids"]],
            "status": coordinator.action_status if coordinator else "pending", "room_status": room.status if room else "unavailable",
            "decision_note": (request.metadata_json or {}).get("risk_decision_note", "") if request else "",
            "source_link": data["source_link"]}
        if details:
            messages = list(await self.db.scalars(select(MeetingMessage).where(MeetingMessage.org_id == self.org_id,
                MeetingMessage.room_id == data["room_id"], MeetingMessage.deleted_at.is_(None), MeetingMessage.message_type == "user")
                .order_by(MeetingMessage.seq_no.desc()).limit(200)))
            visible = [m for m in reversed(messages) if not (m.metadata_json or {}).get("private_recipient_user_id")
                       and not (m.metadata_json or {}).get("agent_sidecar_question")]
            result["discussion"] = [{"id": m.id, "author": m.username, "content": "该讨论已撤回" if (m.metadata_json or {}).get("recalled_at") else m.content,
                "created_at": m.created_at, "origin": "meeting", "seq_no": m.seq_no} for m in visible[-50:]]
            comments = await self.collab.list_messages(org_id=self.org_id, thread_id=data["thread_id"], limit=500)
            result["comments"] = [{"id": m.id, "author": data["participant_names"].get(m.sender_id, "专家"), "content": m.content,
                "created_at": m.created_at, "origin": "collab"} for m in comments
                if m.message_type == "text" and m.reply_to_message_id == data["message_id"]][-50:]
        return result
