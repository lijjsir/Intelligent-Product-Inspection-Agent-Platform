"""Queue readable legacy standards for local parsing, without approving them."""
import asyncio
import json
from pathlib import Path
from sqlalchemy import select
from app.models.inspection_standard_library import StandardDocument
from app.models.standard_admission import StandardDocumentRevision
from app.services.standard_admission_service import StandardAdmissionService
from infra.database.session import get_session, reset_async_engine_pool


async def main():
    queued=[];unavailable=[]
    async with get_session() as session:
        rows=(await session.execute(select(StandardDocumentRevision,StandardDocument).join(StandardDocument,
            StandardDocument.current_revision_id==StandardDocumentRevision.id).where(StandardDocument.deleted_at.is_(None),
            StandardDocumentRevision.processing_status=="pending",StandardDocumentRevision.publication_status=="unpublished"))).all()
        for rev,doc in rows:
            if not rev.snapshot.get("legacy"):continue
            service=StandardAdmissionService(session,rev.org_id)
            try: await asyncio.to_thread(service.read_original,rev)
            except Exception as exc:
                unavailable.append({"document_id":doc.id,"standard_no":doc.standard_no,"error_type":type(exc).__name__})
                continue
            await service.enqueue(rev,"parse")
            queued.append({"document_id":doc.id,"revision_id":rev.id,"standard_no":doc.standard_no})
        await session.commit()
    report={"queued":queued,"unavailable":unavailable,"approvals":0,"publications":0}
    Path("runtime/standard_admission_20261005/legacy_candidate_preparation.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"queued":len(queued),"unavailable":len(unavailable),"approvals":0,"publications":0}))
    await reset_async_engine_pool()


if __name__=="__main__":asyncio.run(main())
