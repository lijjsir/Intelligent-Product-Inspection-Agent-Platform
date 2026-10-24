"""Back up untouched legacy drafts and create new reading-text revisions only.

Never replace a published revision, manual preparation or a professional review.
"""
import argparse
import asyncio
import copy
import hashlib
import json
import tempfile
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, func
from app.core.config import settings
from app.models.organization import Organization
from app.models.user import User
from app.models.inspection_standard_library import StandardDocument
from app.models.standard_admission import StandardDocumentRevision, StandardAdmissionReview
from app.services.standard_admission_service import StandardAdmissionService, digest
from app.services.standard_candidate_extractor import extract_candidates
from app.services.standard_pdf_importer import extract_pdf_pages
from app.services.standard_pdf_reading_text import reading_page
from infra.database.session import get_session, reset_async_engine_pool

ROOT = Path('runtime/standard_text_repair_20261023')
RULES = 'pdf-reading-layout-v2'


async def refine_pending_reading_drafts():
    """Finish this repair's own drafts only, provided nobody has edited/reviewed them."""
    if settings.app_env not in {'local','dev','development','test','testing'} or settings.quality_demo_enabled:
        raise RuntimeError('Only the local business stack is supported')
    targets=json.loads((ROOT/'repair-result.json').read_text(encoding='utf-8'))
    backup=ROOT/'before-reading-refinement.json'
    if backup.exists():raise RuntimeError('Refinement backup already exists; inspect the completed run')
    try:
        async with get_session() as db:
            org=await db.scalar(select(Organization).where(Organization.slug=='cqupt'))
            svc=StandardAdmissionService(db,org.id)
            revisions=[]
            for item in targets:
                doc,rev=await svc.revision(item['document_id'],item['new_revision_id'],lock=True)
                repair=rev.snapshot.get('reading_text_repair') or {}
                if (doc.current_revision_id!=rev.id or rev.row_version!=1 or rev.review_status!='pending' or
                    rev.publication_status!='unpublished' or repair.get('source_revision_id')!=item['previous_revision_id'] or
                    any(c.get('status')!='pending' or c.get('prepared_by') or c.get('requirement') for c in rev.candidates_json)):
                    raise RuntimeError('A draft has been used or edited; do not replace its extraction')
                revisions.append((doc,rev))
            backup.write_text(json.dumps([{'id':rev.id,'snapshot':rev.snapshot,'row_version':rev.row_version,
                'pages':rev.pages_json,'candidates':rev.candidates_json} for _,rev in revisions],ensure_ascii=False,indent=2),encoding='utf-8')
            for doc,rev in revisions:
                content=svc.read_original(rev)
                with tempfile.TemporaryDirectory(prefix='standard-reading-') as folder:
                    source=Path(folder)/'source.pdf';source.write_bytes(content)
                    pages,_=await asyncio.to_thread(extract_pdf_pages,source)
                rev.pages_json=pages;rev.candidates_json=extract_candidates(pages);rev.row_version+=1
                rev.snapshot={**rev.snapshot,'reading_text_repair':{**rev.snapshot['reading_text_repair'],'rules_version':RULES}}
                db.add(StandardAdmissionReview(org_id=org.id,revision_id=rev.id,action='reparse_text',actor_id=rev.created_by,
                    request_key=str(uuid4()),payload_hash=digest(rev.snapshot['reading_text_repair']),
                    reason='完成同次解析修复：合并损坏公式片段，原件以逐页图像对照；未更改专业要求或确认状态。',
                    evidence_refs=[f'original_sha256:{rev.file_hash}'],detail_json=rev.snapshot['reading_text_repair']))
            await db.commit()
            print(json.dumps({'refined_untouched_drafts':len(revisions),'new_reviews':0,'new_publications':0}),flush=True)
    finally:await reset_async_engine_pool()


def untouched_legacy(doc, rev):
    return (rev.snapshot.get('legacy') and not rev.snapshot.get('reading_text_repair') and
        doc.current_revision_id == rev.id and not doc.published_revision_id and
        rev.publication_status == 'unpublished' and rev.review_status == 'pending' and
        not rev.reviewed_by and not any(c.get('status') != 'pending' or c.get('prepared_by') or
            c.get('reviewed_by') or c.get('review_reason') or c.get('requirement') for c in rev.candidates_json or []))


async def main(apply):
    if settings.app_env not in {'local','dev','development','test','testing'} or settings.quality_demo_enabled:
        raise RuntimeError('This maintenance is restricted to the real local development stack')
    ROOT.mkdir(exist_ok=True, parents=True)
    try:
        async with get_session() as db:
            org = await db.scalar(select(Organization).where(Organization.slug == 'cqupt'))
            if not org:raise RuntimeError('Expected cqupt organization not found')
            actor = await db.scalar(select(User).where(User.org_id == org.id,User.role == 'admin',User.is_active.is_(True)))
            if not actor:raise RuntimeError('An active organization maintenance actor is required')
            svc = StandardAdmissionService(db, org.id, actor.id)
            docs = list(await db.scalars(select(StandardDocument).where(StandardDocument.org_id == org.id,
                StandardDocument.deleted_at.is_(None))))
            targets, protected = [], []
            import pymupdf
            for doc in docs:
                rev = await db.get(StandardDocumentRevision, doc.current_revision_id)
                if not rev or not untouched_legacy(doc,rev):
                    protected.append(doc.standard_no); continue
                content = svc.read_original(rev)
                with pymupdf.open(stream=content,filetype='pdf') as pdf:
                    warning_pages = [index+1 for index,page in enumerate(pdf) if reading_page(page)[1]]
                if not warning_pages:continue
                targets.append({'document_id':doc.id,'revision_id':rev.id,'standard_no':doc.standard_no,
                    'row_version':rev.row_version,'file_hash':rev.file_hash,'warning_pages':warning_pages,
                    'before':{'snapshot':rev.snapshot,'pages':rev.pages_json,'candidates':rev.candidates_json,
                        'review_assignment':rev.review_assignment,'created_by':rev.created_by,'revision_no':rev.revision_no}})
            summary = {'apply':apply,'organization':org.slug,'affected':[{
                k:t[k] for k in ('document_id','revision_id','standard_no','warning_pages')} for t in targets],
                'protected_documents':protected,'new_professional_reviews':0,'new_publications':0}
            print(json.dumps(summary,ensure_ascii=True),flush=True)
            if not apply:return
            backup = ROOT / 'before-reading-repair.json'
            if backup.exists():raise RuntimeError('A backup already exists; inspect the previous maintenance result before applying again')
            backup.write_text(json.dumps({'organization':org.id,'targets':targets},ensure_ascii=False,indent=2,default=str),encoding='utf-8')
            results=[]
            for target in targets:
                doc, old = await svc.revision(target['document_id'],target['revision_id'],lock=True)
                if not untouched_legacy(doc,old) or old.row_version != target['row_version']:
                    raise RuntimeError('Draft changed during repair; retry after inspecting the backed-up state')
                content = svc.read_original(old)
                with tempfile.TemporaryDirectory(prefix='standard-reading-') as folder:
                    source = Path(folder)/'source.pdf';source.write_bytes(content)
                    pages, count = await asyncio.to_thread(extract_pdf_pages, source)
                candidates = extract_candidates(pages)
                if not pages or not candidates:raise RuntimeError('Re-extraction did not produce reviewable content')
                number = await db.scalar(select(func.max(StandardDocumentRevision.revision_no)).where(StandardDocumentRevision.document_id == doc.id))
                snapshot = copy.deepcopy(old.snapshot)
                snapshot['reading_text_repair']={'rules_version':RULES,'source_revision_id':old.id,
                    'file_hash':hashlib.sha256(content).hexdigest(),'mode':'automatic_text_layout_no_professional_review'}
                fresh = StandardDocumentRevision(org_id=org.id,document_id=doc.id,revision_no=number+1,
                    snapshot=snapshot,file_hash=old.file_hash,processing_status='parsed',review_status='pending',
                    publication_status='unpublished',extraction_status='needs_review',pages_json=pages,candidates_json=candidates,
                    review_assignment=copy.deepcopy(old.review_assignment),created_by=actor.id,
                    issues_json=['从原PDF重新整理阅读排版；旧修订保留。公式及特殊字形请查看原页；未完成专业核验或发布。'])
                db.add(fresh);await db.flush()
                doc.current_revision_id=fresh.id;doc.review_status='pending';doc.processing_status='parsed';doc.page_count=count
                db.add(StandardAdmissionReview(org_id=org.id,revision_id=fresh.id,action='reparse_text',actor_id=actor.id,
                    request_key=str(uuid4()),payload_hash=digest(snapshot['reading_text_repair']),
                    reason='用户反馈解析乱码；按原PDF重新分行并标记不可可靠还原的符号，未核验或发布标准。',
                    evidence_refs=[f'original_sha256:{fresh.file_hash}',f'previous_revision:{old.id}'],
                    detail_json=snapshot['reading_text_repair']))
                results.append({'standard_no':doc.standard_no,'document_id':doc.id,'previous_revision_id':old.id,
                    'new_revision_id':fresh.id,'revision_no':fresh.revision_no,'candidates':len(candidates),'file_hash_unchanged':fresh.file_hash == old.file_hash})
            await db.commit()
            (ROOT/'repair-result.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'updated':results,'backup_sha256':hashlib.sha256(backup.read_bytes()).hexdigest()},ensure_ascii=True),flush=True)
    finally:await reset_async_engine_pool()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');parser.add_argument('--refine',action='store_true')
    args=parser.parse_args()
    asyncio.run(refine_pending_reading_drafts() if args.refine else main(args.apply))
