"""Exercise real local MySQL row locking, then remove only this run's isolated rows."""
import asyncio,json
from uuid import uuid4
from sqlalchemy import select,delete,func
from app.core.config import settings
from app.models import Base,Organization
from app.models.risk_analysis_job import RiskAnalysisJob
from app.schemas.user import CurrentUser
from app.schemas.quality_risk import QualityEventCreate,RiskCaseCreate,RiskAnalysisJobCreate
from app.services.quality_risk_service import QualityRiskService
from app.services.risk_analysis_job_service import RiskAnalysisJobService
from infra.database.session import get_session,reset_async_engine_pool


async def main():
    if settings.app_env not in {'dev','local','development','test','testing'}:raise RuntimeError('Local checks only')
    org_id,actor_id=str(uuid4()),str(uuid4());slug='local-risk-lock-check-'+uuid4().hex
    current=CurrentUser(user_id=actor_id,org_id=org_id,role='expert')
    try:
        async with get_session() as db:
            db.add(Organization(id=org_id,name='Isolated local concurrency check',slug=slug,is_active=True,settings={}))
            await db.flush();svc=QualityRiskService(db,current)
            raw=await svc.create_event(QualityEventCreate(record_type='supervision_inspection',content={'text':'Isolated concurrency check; no model execution'}))
            case=await svc.create_risk_case(RiskCaseCreate(title='Isolated queue mutex',scope_type='category',scope={'name':'Isolated'},source_record_ids=[raw['id']]))
            await db.commit()
        async def queue():
            async with get_session() as db:
                job=await RiskAnalysisJobService(db,current).queue(case['id'],RiskAnalysisJobCreate(request_key=uuid4(),base_assessment_id=None))
                await db.commit();return job['id']
        ids=await asyncio.wait_for(asyncio.gather(queue(),queue(),queue()),20)
        async with get_session() as db:
            count=await db.scalar(select(func.count()).select_from(RiskAnalysisJob).where(RiskAnalysisJob.org_id==org_id))
            assert len(set(ids))==1 and count==1,{'unique_ids':len(set(ids)),'rows':count}
        print(json.dumps({'passed':True,'simultaneous_requests':3,'created_jobs':count,'model_calls':0}),flush=True)
    finally:
        async with get_session() as db:
            org=await db.get(Organization,org_id)
            if org:
                assert org.slug==slug and slug.startswith('local-risk-lock-check-')
                for name in ('risk_analysis_jobs','business_identifiers','business_number_sequences','quality_evidence_items',
                    'quality_source_records','quality_data_sources','quality_risk_cases'):
                    table=Base.metadata.tables[name]
                    await db.execute(delete(table).where(table.c.org_id==org_id))
                await db.execute(delete(Organization).where(Organization.id==org_id,Organization.slug==slug));await db.commit()
        await reset_async_engine_pool()


if __name__=='__main__':asyncio.run(main())
