from datetime import timedelta
from sqlalchemy import or_, select

from app.core.datetime import utcnow
from app.models.standard_admission import StandardDocumentRevision, StandardSyncOutbox
from app.models.inspection_standard_library import StandardDocument
from app.services.standard_admission_service import process_standard_outbox
from infra.database.session import get_session
from worker.asyncio_runner import run_celery_async
from worker.celery_app import celery_app


@celery_app.task(name="worker.tasks.standard_sync_outbox_task.dispatch_standard_sync_outbox")
def dispatch_standard_sync_outbox():
    return run_celery_async(_dispatch())


@celery_app.task(name="worker.tasks.standard_sync_outbox_task.process_standard_sync_outbox")
def process_standard_sync_outbox(outbox_id):
    return run_celery_async(_process(outbox_id))


async def _dispatch():
    async with get_session() as session:
        ids=(await session.execute(select(StandardSyncOutbox.id).where(
            StandardSyncOutbox.status.in_(["pending", "failed"]), StandardSyncOutbox.attempts<5,
            or_(StandardSyncOutbox.next_attempt_at.is_(None), StandardSyncOutbox.next_attempt_at<=utcnow())
        ).order_by(StandardSyncOutbox.created_at).limit(10))).scalars().all()
    for outbox_id in ids:
        process_standard_sync_outbox.delay(outbox_id)
    return {"queued":len(ids)}


async def _process(outbox_id):
    async with get_session() as session:
        row=(await session.execute(select(StandardSyncOutbox).where(StandardSyncOutbox.id==outbox_id).with_for_update(skip_locked=True))).scalar_one_or_none()
        if not row or row.status=="done" or row.attempts>=5 or (row.next_attempt_at and row.next_attempt_at>utcnow()):
            return {"skipped":True}
        row.attempts+=1
        try:
            async with session.begin_nested():
                await process_standard_outbox(session,row)
            row.status="done"
            row.error_message=None
            row.next_attempt_at=None
        except Exception as exc:
            row.status="failed"
            # No storage addresses, credentials or PDF contents in public job errors.
            row.error_message=f"{type(exc).__name__}：处理未完成，请核对文件或服务状态后重试"
            row.next_attempt_at=utcnow()+timedelta(seconds=min(60*2**row.attempts,1800))
            if row.action=="parse":
                rev=await session.get(StandardDocumentRevision,row.revision_id)
                rev.processing_status="failed"
                rev.row_version+=1
                doc=await session.get(StandardDocument,rev.document_id)
                if doc.current_revision_id==rev.id:
                    doc.processing_status="failed"
        await session.commit()
        return {"status":row.status,"attempts":row.attempts}
