from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import or_, select

from worker.celery_app import celery_app
from worker.asyncio_runner import run_celery_async


@celery_app.task(name="worker.tasks.supervision_task.execute_supervision_run")
def execute_supervision_run(run_id: str, org_id: str):
    return run_celery_async(_execute(run_id, org_id))


async def _execute(run_id, org_id):
    from infra.database.session import get_session
    from app.models.supervision import SupervisionRun
    from app.models.user import User
    from app.schemas.user import CurrentUser
    from app.services.supervision_service import SupervisionService

    async with get_session() as db:
        run = await db.scalar(
            select(SupervisionRun).where(
                SupervisionRun.id == run_id, SupervisionRun.org_id == org_id
            )
        )
        if not run:
            return {"status": "not_found"}
        user = await db.scalar(
            select(User).where(
                User.id == run.created_by, User.org_id == org_id, User.is_active.is_(True)
            )
        )
        if not user or user.role not in {"user", "expert"}:
            run.status = "cancelled"
            await db.commit()
            return {"status": "cancelled"}
        svc = SupervisionService(db, CurrentUser(user_id=user.id, org_id=org_id, role=user.role))
        await svc.require_enabled()
        result = await svc.execute_run(run_id)
        await db.commit()
        return result


@celery_app.task(name="worker.tasks.supervision_task.dispatch_supervision_runs")
def dispatch_supervision_runs():
    return run_celery_async(_dispatch())


async def _dispatch():
    from infra.database.session import get_session
    from app.models.supervision import SupervisionRun

    async with get_session() as db:
        rows = list(
            await db.scalars(
                select(SupervisionRun)
                .where(
                    SupervisionRun.iteration < 2,
                    or_(
                        SupervisionRun.status == "queued",
                        (SupervisionRun.status == "running")
                        & (SupervisionRun.updated_at < datetime.utcnow() - timedelta(minutes=15)),
                    ),
                )
                .limit(100)
            )
        )
        for run in rows:
            execute_supervision_run.delay(run.id, run.org_id)
    publications = await _publish_candidates()
    return {"dispatched": len(rows), "candidate_publications": publications}


async def _publish_candidates():
    from infra.database.session import get_session
    from app.models.supervision import SupervisionRecord
    from app.models.memory import MemoryItem
    from app.models.organization import Organization
    from sqlalchemy import func
    from app.schemas.memory import (
        MemoryWriteRequest,
        MemorySource,
        MemoryScope,
        MemoryContent,
        MemoryType,
    )
    from app.services.memory_service import MemoryService
    from app.schemas.qdl import parse_qdl

    published = 0
    async with get_session() as db:
        rows = list(
            await db.scalars(
                select(SupervisionRecord)
                .join(Organization, Organization.id == SupervisionRecord.org_id)
                .where(
                    SupervisionRecord.kind == "inspection-sessions",
                    SupervisionRecord.status == "signed",
                    SupervisionRecord.data["memory_publication"]["status"]
                    .as_string()
                    .in_(["pending", "failed"]),
                    SupervisionRecord.data["memory_publication"]["attempts"].as_integer() < 2,
                    func.coalesce(SupervisionRecord.data["knowledge_status"].as_string(), "current")
                    != "needs_reassessment",
                    Organization.settings["quality_supervision_enabled"].as_boolean().is_(True),
                )
                .limit(100)
            )
        )
        for record in rows:
            publication = record.data.get("memory_publication") or {}
            if (
                publication.get("status") == "published"
                or publication.get("attempts", 0) >= 2
                or record.data.get("knowledge_status") == "needs_reassessment"
            ):
                continue
            qdl = record.data.get("qdl_candidate")
            if parse_qdl(qdl).validation_status != "valid":
                continue
            attempts = publication.get("attempts", 0) + 1
            try:
                async with db.begin_nested():
                    result = await MemoryService(db, record.org_id).write_candidate(
                        MemoryWriteRequest(
                            org_id=record.org_id,
                            user_id=record.created_by,
                            trace_id=f"supervision:{record.id}:{record.version}",
                            source=MemorySource(
                                kind="agent_message",
                                agent_id="laboratory_testing",
                                task_id=record.data["task_id"],
                            ),
                            memory_type=MemoryType.TASK_EPISODE,
                            scope=MemoryScope(task_id=record.data["task_id"]),
                            content=MemoryContent(
                                summary=qdl["claim"]["text"][:500],
                                facts=[f"检测会话:{record.id};签发版本:{record.version}"],
                                warnings=["仅作候选知识，需知识治理确认；兼容准入分不代表概率"],
                            ),
                            evidence_pointers={
                                "inspection_session_id": record.id,
                                "task_id": record.data["task_id"],
                            },
                            confidence=0.4,
                            created_by=record.created_by,
                        ),
                        allow_automatic_promotion=False,
                    )
                    memory = await db.scalar(
                        select(MemoryItem).where(
                            MemoryItem.memory_id == result.memory_id,
                            MemoryItem.org_id == record.org_id,
                        )
                    )
                    if memory:
                        memory.content_json = {
                            **(memory.content_json or {}),
                            "qdl": qdl,
                            "confidence_status": "not_calibrated",
                        }
                        record.data = {
                            **record.data,
                            "memory_publication": {
                                "status": "published",
                                "attempts": attempts,
                                "memory_id": result.memory_id,
                            },
                        }
                        published += 1
                    else:
                        record.data = {
                            **record.data,
                            "memory_publication": {"status": "rejected", "attempts": attempts},
                        }
            except Exception:
                record.data = {
                    **record.data,
                    "memory_publication": {
                        "status": "failed",
                        "attempts": attempts,
                        "error": "候选同步未完成，请检查知识存储服务后重试",
                    },
                }
            await db.commit()
    return published
