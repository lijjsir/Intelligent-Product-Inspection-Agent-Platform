"""An organization-scoped review queue over existing standard revisions."""
from datetime import datetime, timezone
from sqlalchemy import select
from app.core.datetime import utcnow
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.permissions import has_permission
from app.models.user import User
from app.models.standard_admission import StandardDocumentRevision
from app.models.inspection_standard_library import StandardDocument, InspectionStandardLibrary
from app.services.permission_service import PermissionService
from app.services.standard_admission_service import StandardAdmissionService


class StandardReviewService:
    def __init__(self, session, current):
        self.session, self.current = session, current
        self.admission = StandardAdmissionService(session, current.org_id, current.user_id)

    async def reviewers(self):
        if not has_permission("standard_review_assign", self.current.role):
            raise ForbiddenError("审核分派由管理员处理")
        users = list(await self.session.scalars(select(User).where(
            User.org_id == self.current.org_id, User.role == "expert",
            User.is_active.is_(True), User.deleted_at.is_(None))))
        result = []
        for user in users:
            permissions = await PermissionService(self.session, self.current.org_id).user_permissions(user.id)
            if "standard_admission_review" in permissions["effective"]:
                result.append({"id": user.id, "name": user.username})
        return result

    async def queue(self, *, scope="mine", keyword="", domain="", page=1, size=30):
        rows = (await self.session.execute(select(StandardDocumentRevision, StandardDocument, InspectionStandardLibrary)
            .join(StandardDocument, StandardDocument.current_revision_id == StandardDocumentRevision.id)
            .join(InspectionStandardLibrary, InspectionStandardLibrary.id == StandardDocument.library_id)
            .where(StandardDocumentRevision.org_id == self.current.org_id, StandardDocument.org_id == self.current.org_id,
                   InspectionStandardLibrary.org_id == self.current.org_id, StandardDocument.deleted_at.is_(None),
                   InspectionStandardLibrary.deleted_at.is_(None), InspectionStandardLibrary.is_active.is_(True))
            .order_by(StandardDocumentRevision.created_at, StandardDocumentRevision.id))).all()
        ids = {r.review_assignment.get("reviewer_id") for r, _, _ in rows if r.review_assignment}
        names = {u.id: u.username for u in await self.session.scalars(select(User).where(
            User.org_id == self.current.org_id, User.deleted_at.is_(None), User.id.in_(ids)))} if ids else {}
        result = []
        for revision, document, library in rows:
            assignment = revision.review_assignment or {}
            candidates = revision.candidates_json or []
            pending = sum(c.get("status", "pending") == "pending" for c in candidates)
            confirmed = sum(c.get("status") == "confirmed" for c in candidates)
            needs_work = revision.publication_status == "unpublished" and (
                revision.review_status != "approved" or pending > 0)
            own = revision.created_by == self.current.user_id
            assigned = assignment.get("reviewer_id")
            qualifies = str(self.current.role) == "expert" and has_permission("standard_admission_review", self.current.role)
            result.append({
                "document_id": document.id, "revision_id": revision.id, "revision_no": revision.revision_no,
                "row_version": revision.row_version, "library_id": library.id, "library_name": library.name,
                "created_by": revision.created_by,
                "standard_no": revision.snapshot.get("standard_no"), "standard_name": revision.snapshot.get("standard_name"),
                "domain": revision.snapshot.get("domain") or library.domain or "未分类",
                "product_category": revision.snapshot.get("product_category"), "processing_status": revision.processing_status,
                "review_status": revision.review_status, "publication_status": revision.publication_status,
                "pending_count": pending, "confirmed_count": confirmed, "candidate_count": len(candidates),
                "excluded_count": len(candidates) - pending - confirmed, "needs_work": needs_work,
                "is_author": own, "assigned_to_me": assigned == self.current.user_id,
                "review_assignment": {**assignment, "reviewer_name": names.get(assigned, "")},
                "can_claim": qualifies and not own and not assigned and needs_work,
                "can_review": qualifies and not own and assigned == self.current.user_id and revision.publication_status == "unpublished",
                "created_at": revision.created_at,
            })
        totals = {"pending": sum(x["needs_work"] for x in result),
                  "mine": sum(x["needs_work"] and x["assigned_to_me"] for x in result),
                  "unassigned": sum(x["needs_work"] and not x["review_assignment"].get("reviewer_id") for x in result),
                  "awaiting_publish": sum(x["review_status"] == "approved" and x["publication_status"] == "unpublished" for x in result)}
        domains = sorted({x["domain"] for x in result})
        filters = {
            "mine": lambda x: x["assigned_to_me"] and x["needs_work"],
            "unassigned": lambda x: x["needs_work"] and not x["review_assignment"].get("reviewer_id"),
            "authored": lambda x: x["is_author"] and x["publication_status"] == "unpublished",
            "pending": lambda x: x["needs_work"],
            "awaiting_publish": lambda x: x["review_status"] == "approved" and x["publication_status"] == "unpublished",
            "all": lambda x: True,
        }
        if scope not in filters:
            raise ValidationError("未知审核队列范围")
        matching = [x for x in result if filters[scope](x) and (not domain or x["domain"] == domain)
                    and (not keyword or keyword.lower() in f'{x["standard_no"]} {x["standard_name"]} {x["library_name"]}'.lower())]
        return {"items": matching[(page-1)*size:page*size], "total": len(matching), "page": page, "size": size,
                "totals": totals, "domains": domains}

    async def assign(self, document_id, revision_id, payload):
        document, revision = await self.admission.revision(document_id, revision_id, lock=True)
        operation = payload["operation"]
        admin = has_permission("standard_review_assign", self.current.role)
        qualifies = str(self.current.role) == "expert" and has_permission("standard_admission_review", self.current.role)
        assignment = revision.review_assignment or {}
        if operation == "assign" and not admin:
            raise ForbiddenError("仅管理员可分派审核任务")
        if operation in {"claim", "release"} and not admin and not qualifies:
            raise ForbiddenError("领取或退回审核任务需专业核验权限")
        _, revision, repeated = await self.admission._action(document_id, revision_id, "assignment", payload)
        if repeated:
            return await self.admission.serialize(revision)
        if operation == "assign":
            if not admin:
                raise ForbiddenError("仅管理员可分派审核任务")
            target = payload.get("reviewer_id")
            if target not in {u["id"] for u in await self.reviewers()}:
                raise ValidationError("需选择本组织仍具备专业核验权限的专家")
        elif operation == "claim":
            if not qualifies:
                raise ForbiddenError("领取审核任务需专业核验权限")
            target = self.current.user_id
            if assignment.get("reviewer_id") not in {None, target}:
                raise ConflictError("此修订已分派给另一位专家")
            if assignment.get("reviewer_id") == target:
                raise ConflictError("已承担此修订审核，无需重复领取")
        else:
            if not admin and (not qualifies or assignment.get("reviewer_id") != self.current.user_id):
                raise ForbiddenError("仅管理员或当前审核人可退回分派")
            target = None
        if target and target == revision.created_by:
            raise ForbiddenError("不能分派本人提交的修订供本人核验")
        if revision.publication_status != "unpublished":
            raise ConflictError("已发布修订只读；补充要求请建立新稿")
        due = payload.get("due_at") if operation=="assign" else assignment.get("due_at")
        if due:
            try:
                parsed = datetime.fromisoformat(due.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    raise ValueError()
                due = parsed.astimezone(timezone.utc).isoformat()
            except ValueError:
                raise ValidationError("期限需带时区的完整日期时间") from None
        if not repeated:
            revision.review_assignment = {"reviewer_id": target, "assigned_by": self.current.user_id,
                "assigned_at": utcnow().isoformat(), "due_at": due, "domain": revision.snapshot.get("domain") or document.domain,
                "mode": operation, "reason": payload["reason"]}
            revision.row_version += 1
            await self.session.flush()
        return await self.admission.serialize(revision)
