"""Complete source page positions on unreviewed legacy parsing results."""
import asyncio
from io import BytesIO
import json
from pathlib import Path
from pypdf import PdfReader
from sqlalchemy import select
from app.models.standard_admission import StandardDocumentRevision
from app.models.inspection_standard_library import StandardDocument
from app.services.standard_admission_service import StandardAdmissionService
from infra.database.session import get_session,reset_async_engine_pool


async def main():
    corrected=[]
    async with get_session() as session:
        rows=(await session.execute(select(StandardDocumentRevision).where(StandardDocumentRevision.processing_status=="parsed",
            StandardDocumentRevision.review_status=="pending",StandardDocumentRevision.publication_status=="unpublished").with_for_update())).scalars().all()
        for rev in rows:
            if not rev.snapshot.get("legacy"):continue
            content=await asyncio.to_thread(StandardAdmissionService(session,rev.org_id).read_original,rev)
            count=len(PdfReader(BytesIO(content)).pages)
            pages=list(rev.pages_json or [])
            missing=sorted(set(range(1,count+1))-{p["page_number"] for p in pages})
            if not missing:continue
            rev.pages_json=sorted([*pages,*[{"page_number":p,"text":"","extraction_status":"no_text_detected"} for p in missing]],key=lambda p:p["page_number"])
            rev.issues_json=[*rev.issues_json,"未提取到文字的PDF页："+"、".join(map(str,missing))+"；请对照原文核对是否为空白、图示或表格页。"]
            rev.row_version+=1
            doc=await session.get(StandardDocument,rev.document_id)
            if doc.current_revision_id==rev.id:doc.page_count=count
            corrected.append({"revision_id":rev.id,"source_pages":count,"no_text_pages":missing})
        await session.commit()
    Path("runtime/standard_admission_20261005/source_page_positions.json").write_text(json.dumps({"corrected":corrected},ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"corrected_documents":len(corrected),"publication_changes":0}))
    await reset_async_engine_pool()


if __name__=="__main__":asyncio.run(main())
