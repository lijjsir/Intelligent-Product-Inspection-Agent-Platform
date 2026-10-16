"""Assign the prepared R4 standard through its existing workflow, without approving it."""
import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path

from sqlalchemy import select

from app.core.exceptions import ConflictError, ValidationError
from app.core.permissions import has_permission
from app.models.standard_admission import StandardDocumentRevision
from app.models.task import InspectionTask
from app.models.user import User
from app.schemas.standard_admission import ReviewAssignment
from app.schemas.user import CurrentUser
from app.services.permission_service import PermissionService
from app.services.standard_review_service import StandardReviewService
from infra.database.session import get_session, reset_async_engine_pool

TASK_ID = "01a13879-0890-7980-9e72-05638bde71b8"
OUTPUT = Path("runtime/r4_start_20261014")


def state(revision):
    return {
        "revision_id": revision.id, "row_version": revision.row_version,
        "review_status": revision.review_status, "publication_status": revision.publication_status,
        "review_assignment": revision.review_assignment,
        "candidate_states": dict(Counter(c.get("status", "pending") for c in revision.candidates_json or [])),
    }


async def main(args):
    try:
        async with get_session() as db:
            task = await db.get(InspectionTask, TASK_ID)
            if not task or task.deleted_at:
                raise ValidationError("Prepared case task is unavailable")
            plan = (task.meta_data or {}).get("case_preparation") or {}
            revision = await db.get(StandardDocumentRevision, plan.get("standard_revision_id"))
            if not revision or revision.org_id != task.org_id:
                raise ValidationError("Prepared revision is unavailable in the case organization")
            admin = await db.scalar(select(User).where(User.org_id == task.org_id, User.username == "admin",
                User.role == "admin", User.is_active.is_(True), User.deleted_at.is_(None)))
            if not admin:
                raise ValidationError("No active administrator for the case organization")
            effective = (await PermissionService(db, task.org_id).user_permissions(admin.id))["effective"]
            if "standard_review_assign" not in effective or not has_permission("standard_review_assign", admin.role):
                raise ValidationError("Administrator is not authorized to assign standard reviews")
            service = StandardReviewService(db, CurrentUser(user_id=admin.id, org_id=task.org_id, role=admin.role))
            reviewers = await service.reviewers()
            targets = [u for u in reviewers if u["name"] == args.reviewer and u["id"] != revision.created_by]
            if len(targets) != 1:
                raise ValidationError("Choose an eligible independent expert account")
            target = targets[0]
            before = state(revision)
            existing = (revision.review_assignment or {}).get("reviewer_id")
            if existing and existing != target["id"]:
                raise ConflictError("The revision is already assigned to another expert; no reassignment performed")
            result = {"task_id": task.id, "reviewer": target["name"], "before": before,
                "applied": False, "already_assigned": existing == target["id"]}
            if args.apply and not existing:
                OUTPUT.mkdir(parents=True, exist_ok=True)
                before_path = OUTPUT / "assignment_before.json"
                if not before_path.exists():
                    before_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                payload = ReviewAssignment(expected_version=revision.row_version,
                    request_key=f"r4-start-20261014-{revision.id}-{target['id']}", operation="assign",
                    reviewer_id=target["id"],
                    reason="按用户开始办理 R4 案例的指示分派专业核验；首轮核对整车质量的历史适用范围、条款用途、方法与限值。本操作仅安排审核，不确认条款或结果。")
                await service.assign(revision.document_id, revision.id, payload.model_dump())
                after = state(revision)
                if any(after[k] != before[k] for k in ["review_status", "publication_status", "candidate_states"]):
                    raise AssertionError("Assignment must not approve or publish case content")
                await db.commit()
                result.update(applied=True, after=after)
                (OUTPUT / "assignment_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(result, ensure_ascii=False))
    finally:
        await reset_async_engine_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviewer", default="expert")
    parser.add_argument("--apply", action="store_true")
    asyncio.run(main(parser.parse_args()))
