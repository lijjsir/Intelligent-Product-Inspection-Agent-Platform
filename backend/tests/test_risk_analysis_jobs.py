"""Isolated background analysis, input freshness, permission and recovery checks."""
import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import uuid4
from unittest.mock import AsyncMock
import pytest
import pytest_asyncio
from sqlalchemy import select,func
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_quality_risk_v4 import domain  # noqa: F401
from app.core.datetime import utcnow
from app.core.exceptions import ConflictError,NotFoundError
from app.models import Base,User
from app.models.risk_analysis_job import RiskAnalysisJob
from app.models.quality_risk import QualitySourceRecord,QualityRiskAssessment
from app.schemas.quality_risk import QualityEventCreate,RiskCaseCreate,RiskAnalysisJobCreate
from app.services.risk_analysis_job_service import RiskAnalysisJobService
from app.services.supervision_service import SupervisionService
from worker.tasks import risk_analysis_task as worker


@pytest_asyncio.fixture
async def jobs(domain,monkeypatch):
    db,risk=domain
    async with db.bind.begin() as connection:
        for name in ('risk_analysis_jobs','role_permissions','user_permissions'):
            await connection.run_sync(lambda conn, name=name:Base.metadata.tables[name].create(conn))
    factory=async_sessionmaker(db.bind,expire_on_commit=False)
    @asynccontextmanager
    async def sessions():
        async with factory() as session:yield session
    monkeypatch.setattr(worker,'get_session',sessions)
    monkeypatch.setattr(SupervisionService,'model_call',AsyncMock(return_value=None))
    execute=AsyncMock(return_value={'risk_level':'medium','summary':'Isolated observed source',
        'model_versions':{'model_success':True,'llm_called':True}})
    monkeypatch.setattr(SupervisionService,'execute_agent_via_manager',execute)
    record=await risk('user').create_event(QualityEventCreate(record_type='supervision_inspection',occurred_at=utcnow(),content={'text':'Isolated evidence'}))
    case=await risk('user').create_risk_case(RiskCaseCreate(title='Isolated durable request',scope_type='category',scope={'name':'电动自行车'},source_record_ids=[record['id']]))
    await db.commit()
    svc=RiskAnalysisJobService(db,risk('expert').current)
    return db,risk,svc,case,record,execute,factory


def request(**kwargs):return RiskAnalysisJobCreate(request_key=uuid4(),base_assessment_id=None,**kwargs)


@pytest.mark.asyncio
async def test_queue_is_durable_idempotent_and_prevents_active_or_stale_duplicate(jobs):
    db,_,svc,case,_,execute,_=jobs
    payload=request();job=await svc.queue(case['id'],payload);await db.commit()
    assert job['status']=='queued';execute.assert_not_awaited()
    assert (await svc.queue(case['id'],payload))['id']==job['id']
    assert (await svc.queue(case['id'],request()))['id']==job['id']
    with pytest.raises(ConflictError):await svc.queue(case['id'],request(policy_id=str(uuid4())))
    result=await worker._process(job['id'])
    assert result['status']=='succeeded'
    await db.rollback()  # refresh this reader's prior transaction
    assert (await svc.queue(case['id'],payload))['id']==job['id']
    with pytest.raises(ConflictError):await svc.queue(case['id'],request())
    assert (await worker._process(job['id']))['skipped']
    assert await db.scalar(select(func.count()).select_from(QualityRiskAssessment).where(QualityRiskAssessment.risk_case_id==case['id']))==1
    execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_source_changed_while_model_waits_never_saves_a_stale_draft(jobs,monkeypatch):
    db,risk,svc,case,record,_,factory=jobs
    entered=asyncio.Event();release=asyncio.Event()
    async def slow(*args,**kwargs):
        entered.set();await release.wait();return {'risk_level':'high'}
    monkeypatch.setattr(SupervisionService,'execute_agent_via_manager',slow)
    job=await svc.queue(case['id'],request());await db.commit()
    task=asyncio.create_task(worker._process(job['id']))
    await asyncio.wait_for(entered.wait(),5)
    async with factory() as reader:
        status=await RiskAnalysisJobService(reader,risk('expert').current).get(case['id'],job['id'])
        assert status['status']=='running'
        source=await reader.get(QualitySourceRecord,record['id']);source.content={'text':'New evidence'};await reader.commit()
    release.set();result=await task
    assert result['error_code']=='source_changed'
    await db.rollback()
    assert (await svc.get(case['id'],job['id']))['status']=='stale'
    assert await db.scalar(select(func.count()).select_from(QualityRiskAssessment))==0


@pytest.mark.asyncio
async def test_rate_limit_is_not_reported_as_successful_model_analysis(jobs,monkeypatch):
    db,_,svc,case,_,_,_=jobs
    monkeypatch.setattr(SupervisionService,'execute_agent_via_manager',AsyncMock(return_value={'risk_level':'unknown',
        'status':'manual_review_required','model_versions':{'llm_called':True,'model_success':False,'inference_error':'provider_rate_limited'}}))
    job=await svc.queue(case['id'],request());await db.commit()
    result=await worker._process(job['id']);assert result['status']=='completed_with_warnings'
    await db.rollback();status=await svc.get(case['id'],job['id'])
    assert status['error_code']=='provider_rate_limited'
    row=await db.get(QualityRiskAssessment,status['assessment_id'])
    assert row.reviewed_by is None and row.status!='accepted'


@pytest.mark.asyncio
async def test_timeout_and_worker_crash_require_explicit_retry(jobs,monkeypatch):
    db,_,svc,case,_,_,_=jobs
    monkeypatch.setattr(worker,'MAX_ANALYSIS_SECONDS',1)
    async def slow(*args,**kwargs):await asyncio.sleep(10)
    monkeypatch.setattr(SupervisionService,'execute_agent_via_manager',slow)
    job=await svc.queue(case['id'],request());await db.commit()
    assert (await worker._process(job['id']))['error_code']=='analysis_timeout'
    await db.rollback()
    second=await svc.queue(case['id'],request());await db.commit()
    row=await db.get(RiskAnalysisJob,second['id']);row.status='running';row.lease_until=utcnow()-timedelta(seconds=1);await db.commit()
    sent=[];monkeypatch.setattr(worker.process_risk_analysis,'delay',lambda job_id:sent.append(job_id))
    assert (await worker._dispatch())['interrupted']==1
    assert sent==[]
    await db.rollback();assert (await svc.get(case['id'],second['id']))['error_code']=='worker_interrupted'


@pytest.mark.asyncio
async def test_worker_rechecks_revoked_account_and_cross_org_access(jobs):
    db,risk,svc,case,_,execute,_=jobs
    job=await svc.queue(case['id'],request());await db.commit()
    user=await db.get(User,risk('expert').actor);user.is_active=False;await db.commit()
    assert (await worker._process(job['id']))['error_code']=='permission_changed'
    execute.assert_not_awaited()
    from app.schemas.user import CurrentUser
    other=RiskAnalysisJobService(db,CurrentUser(user_id=str(uuid4()),org_id=str(uuid4()),role='expert'))
    with pytest.raises(NotFoundError):await other.get(case['id'],job['id'])


@pytest.mark.asyncio
async def test_cancelled_queue_is_never_executed_and_cannot_be_cancelled_by_peer(jobs):
    db,risk,svc,case,_,execute,_=jobs
    from app.core.exceptions import ForbiddenError
    job=await svc.queue(case['id'],request());await db.commit()
    with pytest.raises(ForbiddenError):await RiskAnalysisJobService(db,risk('expert2').current).cancel(case['id'],job['id'])
    assert (await svc.cancel(case['id'],job['id']))['status']=='cancelled';await db.commit()
    assert (await worker._process(job['id']))['skipped'];execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_permission_revoked_during_inference_rolls_back_the_result(jobs,monkeypatch):
    db,risk,svc,case,_,_,factory=jobs
    entered=asyncio.Event();release=asyncio.Event()
    async def slow(*args,**kwargs):entered.set();await release.wait();return {'risk_level':'medium'}
    monkeypatch.setattr(SupervisionService,'execute_agent_via_manager',slow)
    job=await svc.queue(case['id'],request());await db.commit()
    task=asyncio.create_task(worker._process(job['id']));await asyncio.wait_for(entered.wait(),5)
    async with factory() as editor:
        user=await editor.get(User,risk('expert').actor);user.is_active=False;await editor.commit()
    release.set();assert (await task)['error_code']=='permission_changed'
    await db.rollback()
    assert await db.scalar(select(func.count()).select_from(QualityRiskAssessment))==0


def test_job_references_are_validated_before_database_binding():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):request(policy_id='not-a-uuid')


@pytest.mark.asyncio
async def test_http_acknowledges_a_saved_job_before_any_model_execution(jobs):
    db,risk,_,case,_,execute,_=jobs
    from fastapi import FastAPI
    from httpx import AsyncClient,ASGITransport
    from app.api.v1.quality_risk import router
    from app.api.v1.deps import get_current_user,get_db
    app=FastAPI();app.include_router(router)
    app.dependency_overrides[get_current_user]=lambda:risk('expert').current
    async def database():yield db
    app.dependency_overrides[get_db]=database
    async with AsyncClient(transport=ASGITransport(app),base_url='http://isolated') as client:
        created=await client.post(f"/risk-cases/{case['id']}/analysis-jobs",json=request().model_dump(mode='json'))
        assert created.status_code==202,created.text
        job=created.json()['data'];assert job['status']=='queued'
        latest=await client.get(f"/risk-cases/{case['id']}/analysis-jobs/latest")
        assert latest.json()['data']['id']==job['id'];execute.assert_not_awaited()
        cancelled=await client.post(f"/risk-cases/{case['id']}/analysis-jobs/{job['id']}/cancel")
        assert cancelled.json()['data']['status']=='cancelled'
