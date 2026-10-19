"""Isolated software fixtures only: no real sampling, equipment or standard claims."""
import csv
import io
from datetime import date, datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import DateTime, DefaultClause, MetaData, select, text

from test_risk_execution_return import returning, domain, flow, formal, collaboration  # noqa: F401
from test_lab_verification_paths import standard
from app.models import Base
from app.models.quality_risk import QualityProductionBatch, QualityRiskCase
from app.models.supervision import SupervisionRecord, SupervisionRevision
from app.models.task import InspectionTask
from app.core.exceptions import ConflictError, ForbiddenError, ValidationError, NotFoundError
from app.schemas.supervision import RecordCreate, RecordUpdate
from app.schemas.quality_risk import RiskAnalyzeRequest, RiskReviewRequest
from app.schemas.risk_completion import LabDecision, LabTaskCreate, LabExecutionReturn, RiskReportCreate
from app.services.risk_lab_task_service import RiskLabTaskService
from app.services.risk_lab_service import RiskLabService
from app.services.quality_risk_service import stable_hash
from app.services.supervision_service import SupervisionService
from app.services.inspection_execution_service import InspectionExecutionService
from app.services.inspection_execution_context_service import InspectionExecutionContextService
from app.services.risk_report_service import RiskReportService


@pytest_asyncio.fixture
async def preparing(returning):
    db, risk, _, case, _, _, _, original, _, _, _, _ = returning
    metadata=MetaData()
    for name in ('measurement_batches','supervision_events','business_number_sequences','business_identifiers'):
        table=Base.metadata.tables[name].to_metadata(metadata)
        for col in table.c:
            if col.server_default is not None:col.server_default=DefaultClause(text('CURRENT_TIMESTAMP')) if isinstance(col.type,DateTime) else None
    async with db.bind.begin() as conn:await conn.run_sync(metadata.create_all)
    product=case['scope']['product_id']
    batch=QualityProductionBatch(org_id=risk('expert').org_id,product_id=product,original_batch_no='ISOLATED-BATCH',production_date=date(2026,1,1),created_by=risk('expert').actor)
    db.add(batch);await db.flush()
    row=await db.get(QualityRiskCase,case['id'])
    row.scope={**row.scope,'quality_batch_id':batch.id,'production_batch_ref':batch.original_batch_no,'unit_serial_ref':'ISOLATED-UNIT'}
    assessment=await risk('expert').analyze_risk(case['id'],RiskAnalyzeRequest())
    lab=RiskLabService(db,risk('expert').current)
    basis,_=await lab.demo.capture(row)
    link=await lab.decide(case['id'],LabDecision(assessment_id=assessment['id'],expected_basis_hash=stable_hash(basis),
        mode='verify',verification_path='task',purpose='【隔离软件验收】不代表实物检测'))
    config=await standard(db,lab.org_id)
    context=await RiskLabTaskService(lab).context(link['id'])
    created=await RiskLabTaskService(lab).create(link['id'],LabTaskCreate(expected_revision=link['revision'],expected_basis_hash=context['basis_hash'],request_key=uuid4(),inspection_standard_id=config.id))
    task=await db.get(InspectionTask,created['task_id'])
    svc=SupervisionService(db,risk('expert').current)
    device=await SupervisionService(db,risk('admin').current).create('devices',RecordCreate(name='【隔离】设备档案',data={
        'device_type':'fixture','capabilities':['test_value'],'calibration_status':'valid','calibration_expires_at':'2030-01-01T00:00:00Z'}))
    # Historical fixture is explicit test data, never installed in a business DB.
    history=await db.scalar(select(SupervisionRevision).where(SupervisionRevision.record_id==device['id']))
    history.created_at=datetime(2026,1,1)
    await db.flush()
    sample_data={'task_id':task.id,'quality_product_id':product,'quality_batch_id':batch.id,
        'production_batch_ref':batch.original_batch_no,'unit_serial_ref':'ISOLATED-UNIT','sampled_at':'2026-01-02T00:00:00Z'}
    return db,risk,case,assessment,task,svc,device,sample_data,created['link'],original


async def collection(preparing):
    db,risk,case,assessment,task,svc,device,sample_data,link,original=preparing
    sample=await svc.create('samples',RecordCreate(code='ISOLATED-SAMPLE',name='【隔离】样品',data=sample_data))
    session=await svc.create('inspection-sessions',RecordCreate(name='【隔离】采集会话',data={
        'task_id':task.id,'sample_ids':[sample['id']],'device_ids':[device['id']],
        'test_items':[{'item':'test_value','unit':'unit','method':'fixture'}],'product_category':'隔离回流测试产品','production_date':'2026-01-01','adaptive_enabled':False}))
    output=io.StringIO();writer=csv.writer(output)
    writer.writerow(['event_id','sample_id','device_id','item','measured_at','value','unit','method','quality_flag','conditions','uncertainty'])
    writer.writerow(['isolated-trial',sample['id'],device['id'],'test_value','2026-01-03T00:00:00Z',11,'unit','fixture','valid','{}',''])
    return sample,session,output.getvalue().encode()


@pytest.mark.asyncio
async def test_created_task_sample_import_review_return_and_new_report(preparing):
    db,risk,case,assessment,task,svc,device,sample_data,link,original=preparing
    sample,session,raw=await collection(preparing)
    assert task.status=='pending' and task.product_sku_id is None
    preview=await svc.preview_file(session['id'],'isolated.csv',raw,{})
    assert preview['can_confirm'] and preview['valid_count']==1,preview
    imported=await svc.confirm_file(session['id'],preview['preview_id'],'isolated-source')
    assert imported['accepted']==1
    context=await InspectionExecutionContextService(db,risk('expert').current).context(task)
    assert not context['samples'][0]['issues']
    measurement=context['measurements'][0]
    native=InspectionExecutionService(db,risk('expert').current)
    body={'request_key':str(uuid4()),'task_id':task.id,'session_id':session['id'],'context_hash':context['context_hash'],
        'product_category':'隔离回流测试产品','production_date':'2026-01-01','sample_ids':[sample['id']],
        'requirements':[{'revision_id':r['revision_id'],'candidate_id':r['candidate_id']} for r in original.snapshot['source_refs']],
        'observations':[{'kind':'measurement_record','id':measurement['id'],'sample_id':sample['id'],'measurement_key':'test_value'}]}
    created=await native.create(body)
    assert not created['current_source_issues'],created
    run=await native.get(created['id'])
    lab=RiskLabService(db,risk('expert').current)
    assert not (await lab.execution_candidates(link['id']))['items']
    with pytest.raises(ValidationError,match='独立复核'):
        await lab.return_execution(link['id'],LabExecutionReturn(expected_revision=link['revision'],run_id=run.id,expected_run_hash='0'*64,note='【隔离】未复核不得回流'))
    review={'expected_version':run.row_version,'request_key':str(uuid4()),'decision':'accept','reason':'【隔离】逐项独立复核原始测量','evidence_refs':['isolated-trial']}
    with pytest.raises(ForbiddenError):await native.review(run.id,review)
    await InspectionExecutionService(db,risk('expert2').current).review(run.id,review)
    candidate=(await lab.execution_candidates(link['id']))['items'][0]
    assert candidate['eligible'],candidate
    payload=LabExecutionReturn(expected_revision=link['revision'],run_id=run.id,expected_run_hash=candidate['definition_hash'],note='【隔离】实测回流流程验收')
    returned=await lab.return_execution(link['id'],payload)
    assert (await lab.return_execution(link['id'],payload))['reused']
    new=await risk('expert').analyze_risk(case['id'],RiskAnalyzeRequest())
    assert new['version']==assessment['version']+1
    assert new['model_versions']['returned_execution_refs'][0]['run_id']==run.id
    await risk('expert2').review_risk(case['id'],RiskReviewRequest(decision='accept',comment='【隔离】风险复核仍独立进行',risk_level='high'))
    workspace=await risk('expert').risk_workspace(case['id'])
    report=await RiskReportService(db,risk('expert').current).create(case['id'],RiskReportCreate(assessment_id=new['id'],expected_basis_hash=workspace['workflow_context']['basis_hash']))
    assert report['snapshot']['execution_results'][0]['ref']['run_id']==run.id
    assert returned['status']=='returned' and task.status=='pending'
    sample_row=await db.get(SupervisionRecord,sample['id'])
    sample_row.data={**sample_row.data,'unit_serial_ref':'WRONG'};await db.flush()
    assert (await native.verification(run))['blockers']
    assert not (await lab.execution_candidates(link['id']))['items'][0]['eligible']


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value',[('quality_product_id',None),('quality_product_id','foreign'),('quality_batch_id',None),('production_batch_ref','WRONG'),('unit_serial_ref','WRONG'),('sampled_at','2099-01-01T00:00:00Z')])
async def test_sample_rejects_missing_or_inconsistent_object(preparing,field,value):
    db,risk,case,assessment,task,svc,device,data,link,original=preparing
    body={**data,field:(str(uuid4()) if value=='foreign' else value)}
    with pytest.raises(ValidationError):await svc.create('samples',RecordCreate(name='【隔离】拒绝错误对象',data=body))


@pytest.mark.asyncio
async def test_stale_preview_and_sample_changes_block_import_and_review(preparing):
    db,risk,case,assessment,task,svc,device,data,link,original=preparing
    sample,session,raw=await collection(preparing)
    preview=await svc.preview_file(session['id'],'isolated.csv',raw,{})
    row=await svc.get('samples',sample['id']);row.data={**row.data,'unit_serial_ref':'WRONG'};await db.flush()
    with pytest.raises(ValidationError,match='样品与任务'):await svc.confirm_file(session['id'],preview['preview_id'],'isolated-source')
    context=await InspectionExecutionContextService(db,risk('expert').current).context(task)
    assert context['samples'][0]['issues']
    row.data=sample['data'];await db.flush()
    session_row=await svc.get('inspection-sessions',session['id']);session_row.version+=1;await db.flush()
    with pytest.raises(ConflictError,match='重新预览'):await svc.confirm_file(session['id'],preview['preview_id'],'isolated-source')


@pytest.mark.asyncio
async def test_unknown_sample_time_preserved_and_unrelated_task_rejected(preparing):
    db,risk,case,assessment,task,svc,device,data,link,original=preparing
    sample=await svc.create('samples',RecordCreate(name='【隔离】待采样',data={**data,'sampled_at':None}))
    assert sample['data']['sampled_at'] is None
    context=await InspectionExecutionContextService(db,risk('expert').current).context(task)
    assert context['samples'][0]['issues']==['尚未记录采样时间']
    with pytest.raises((ForbiddenError,NotFoundError,ValidationError)):
        await svc.create('samples',RecordCreate(name='【隔离】无关任务',data={**data,'task_id':str(uuid4())}))


@pytest.mark.asyncio
@pytest.mark.parametrize('measured_at',['2026-01-01T00:00:00Z','2099-01-01T00:00:00Z'])
async def test_invalid_measurement_time_is_rejected_at_confirmation(preparing,measured_at):
    db,risk,case,assessment,task,svc,device,data,link,original=preparing
    sample,session,raw=await collection(preparing)
    raw=raw.replace(b'2026-01-03T00:00:00Z',measured_at.encode())
    preview=await svc.preview_file(session['id'],'isolated.csv',raw,{})
    with pytest.raises(ValidationError,match='实际采样、测量时间'):
        await svc.confirm_file(session['id'],preview['preview_id'],'isolated-time')


@pytest.mark.asyncio
async def test_archived_task_rejects_sample_change_and_measurement_import(preparing):
    db,risk,case,assessment,task,svc,device,data,link,original=preparing
    sample,session,raw=await collection(preparing)
    preview=await svc.preview_file(session['id'],'isolated.csv',raw,{})
    task.status='archived';await db.flush()
    with pytest.raises(ConflictError,match='已归档任务'):
        await svc.update('samples',sample['id'],RecordUpdate(version=1,data={'sampled_at':data['sampled_at']}))
    with pytest.raises(ConflictError,match='已归档任务'):
        await svc.confirm_file(session['id'],preview['preview_id'],'isolated-archived')
