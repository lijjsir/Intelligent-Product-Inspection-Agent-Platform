"""Inspect R2 task readiness without linking, publishing, signing or exposing bodies."""
import argparse,asyncio,json
from collections import Counter
from pathlib import Path
from sqlalchemy import select,text
from app.models.task import InspectionTask
from app.models.user import User
from app.models.standard_admission import StandardDocumentRevision
from app.models.inspection_standard_library import StandardDocument
from app.schemas.user import CurrentUser
from app.services.inspection_execution_context_service import InspectionExecutionContextService
from infra.database.session import get_session,reset_async_engine_pool


async def main(output):
    result={'read_only':True,'tasks':[],'non_business_creator_count':0}
    try:
        async with get_session() as db:
            result['database_revisions']=list(await db.scalars(text('SELECT version_num FROM alembic_version')))
            rows=(await db.scalars(select(InspectionTask).where(InspectionTask.deleted_at.is_(None)))).all()
            for task in rows:
                user=await db.get(User,task.created_by)
                if not user or user.role not in {'user','expert'}:
                    result['non_business_creator_count']+=1
                    user=await db.scalar(select(User).where(User.org_id==task.org_id,User.role=='expert',User.is_active.is_(True)).limit(1))
                if not user:continue
                context=await InspectionExecutionContextService(db,CurrentUser(user_id=user.id,org_id=user.org_id,role=user.role)).context(task)
                result['tasks'].append({'status':task.status,'input_mode':context['task_scope']['input_mode'],
                    'product_bound':bool(task.quality_product_id or task.product_sku_id),'batch_bound':bool(context['task_scope']['quality_batch_id'] or task.batch_id),
                    'production_date_available':bool(context['task_scope']['production_date']),'scope_issues':context['task_scope']['issues'],
                    'sessions':len(context['sessions']),'samples':dict(Counter(s['kind'] for s in context['samples'])),
                    'measurements':len(context['measurements']),'reports_linked':len(context['reports']),
                    'applicable_policies':sum(not p['issues'] for p in context['policies'])})
            revisions=(await db.scalars(select(StandardDocumentRevision).join(StandardDocument,StandardDocument.published_revision_id==StandardDocumentRevision.id)
                .where(StandardDocument.deleted_at.is_(None),StandardDocumentRevision.publication_status=='published'))).all()
            result['published_confirmed_types']=dict(Counter(c.get('candidate_type') or 'unclassified' for r in revisions for c in r.candidates_json or [] if c.get('status')=='confirmed'))
    finally:await reset_async_engine_pool()
    path=Path(output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    asyncio.run(main(parser.parse_args().output))
