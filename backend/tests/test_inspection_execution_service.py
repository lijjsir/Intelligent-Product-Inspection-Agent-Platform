import uuid
import copy
import hashlib
from io import BytesIO
from datetime import datetime
from pypdf import PdfWriter
import pytest
import pytest_asyncio
from sqlalchemy import MetaData,DefaultClause,select,text
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from app.models.task import InspectionTask
from app.models.inspection_standard_library import InspectionStandardLibrary,StandardDocument
from app.models.standard_admission import StandardDocumentRevision
from app.models.inspection_execution import InspectionExecutionRun,InspectionExecutionAction,InspectionPolicyPublication
from app.models.inspection_spec import InspectionSpec,SpecChangeLog
from app.models.quality_risk import QualityAttachment,QualitySourceRecord,PhysicalSample,ProductCategory,QualityProduct,QualityProductionBatch
from app.models.product import ProductSku,ProductBatch,ProductLine
from app.models.supervision import MeasurementRecord,SupervisionRecord,SupervisionRevision
from app.schemas.user import CurrentUser
from app.services.inspection_execution_service import InspectionExecutionService
from app.core.exceptions import ConflictError,ForbiddenError,NotFoundError,ValidationError
from app.services.knowledge_source_service import fingerprint

ORG,OTHER,AUTHOR,EXPERT=[str(uuid.uuid4()) for _ in range(4)]


@pytest_asyncio.fixture
async def data(monkeypatch):
    writer=PdfWriter()
    for _ in range(4):writer.add_blank_page(width=500,height=700)
    output=BytesIO();writer.write(output);pdf=output.getvalue()
    class Storage:
        content=pdf
        def get_bytes(self,**kw):return (self.content,'application/pdf') if self.content else None
    storage=Storage()
    monkeypatch.setattr('app.services.execution_evidence_service.build_object_storage',lambda:storage)
    engine=create_async_engine('sqlite+aiosqlite:///:memory:');meta=MetaData()
    models=[InspectionTask,InspectionStandardLibrary,StandardDocument,StandardDocumentRevision,InspectionExecutionRun,InspectionExecutionAction,
        InspectionPolicyPublication,InspectionSpec,SpecChangeLog,QualityAttachment,QualitySourceRecord,MeasurementRecord,SupervisionRecord,SupervisionRevision,
        PhysicalSample,ProductCategory,QualityProduct,QualityProductionBatch,ProductSku,ProductBatch,ProductLine]
    for model in models:
        table=model.__table__.to_metadata(meta)
        for col in table.c:
            if col.name in {'created_at','updated_at'}:col.server_default=DefaultClause(text('CURRENT_TIMESTAMP'))
    async with engine.begin() as conn:await conn.run_sync(meta.create_all)
    async with async_sessionmaker(engine,expire_on_commit=False)() as session:
        task=InspectionTask(org_id=ORG,created_by=AUTHOR,product_id='fixture-ebike',spec_code='fixture',image_urls=[],status='pending')
        library=InspectionStandardLibrary(id=str(uuid.uuid4()),org_id=ORG,name='isolated standard fixture',product_family='电动自行车',rag_space_ids=[])
        session.add_all([task,library]);await session.flush()
        doc=StandardDocument(org_id=ORG,library_id=library.id,standard_no='GB 17761-2018',standard_name='isolated fixture',standard_level='GB',
            domain='电动自行车',product_category='电动自行车',file_name='fixture.pdf',file_path='fixture.pdf')
        session.add(doc);await session.flush()
        rid=str(uuid.uuid4());candidate={'id':str(uuid.uuid4()),'candidate_type':'inspection_requirement','status':'confirmed','reviewed_by':EXPERT,'indicator':'最高车速','measurement_key':'maximum_speed',
            'unit':'km/h','method':'7.1','operator':'le','numeric_upper':25.0,'execution_mode':'numeric','expected_conditions':{'mode':'maximum'},'clause_no':'6.1.1','page_number':4}
        revision=StandardDocumentRevision(id=rid,document_id=doc.id,org_id=ORG,revision_no=1,processing_status='parsed',review_status='approved',publication_status='published',
            snapshot={'standard_no':'GB 17761-2018','product_category':'电动自行车','standard_status':'被代替','production_from':'2019-04-15','production_to':'2025-08-31','scope_notes':'历史产品测试范围'},
            file_hash='fixture-hash',candidates_json=[candidate],pages_json=[])
        doc.current_revision_id=rid;doc.published_revision_id=rid;session.add(revision)
        report=QualityAttachment(org_id=ORG,file_name='fixture-report.pdf',mime_type='application/pdf',size_bytes=len(pdf),sha256=hashlib.sha256(pdf).hexdigest(),
            bucket='fixture',object_key='report',uploaded_by=AUTHOR)
        session.add(report);await session.flush()
        source=QualitySourceRecord(org_id=ORG,source_id=str(uuid.uuid4()),record_type='inspection_report',content={'text':'isolated report'},content_hash='isolated',
            attachment_ids=[report.id],authorization_scope='private',data_nature='observed',created_by=AUTHOR)
        session.add(source);await session.flush()
        task.meta_data={'input_mode':'report','product_category_name':'电动自行车','execution_inputs':{'report_links':[{'source_record_id':source.id,'attachment_id':report.id,
            'samples':[{'id':'report-sample','label':'report-sample'}]}]}}
        await session.flush()
        yield session,task,revision,candidate,report,storage
    await engine.dispose()


def current(user=AUTHOR,role='user',org=ORG):return CurrentUser(user_id=user,org_id=org,role=role)
def payload(data):return {'request_key':str(uuid.uuid4()),'task_id':data[1].id,'session_id':None,'product_category':'电动自行车','production_date':'2021-09-03',
    'policy_id':None,'requirements':[{'revision_id':data[2].id,'candidate_id':data[3]['id']}],'sample_ids':['report-sample'],
    'observations':[{'kind':'report_attachment','id':data[4].id,'measurement_key':'maximum_speed','sample_id':'report-sample','value':30.8,'unit':'km/h',
        'method':'7.1','conditions':{'mode':'maximum'},'report_page':3,'report_item':'最高车速'}]}
def review(run,**kw):return {'expected_version':run.row_version,'request_key':str(uuid.uuid4()),'decision':'accept','reason':'isolated reviewer verification',
    'report_values_verified':True,'evidence_refs':['fixture-report page3'],
    'verified_evidence_ids':list({o['evidence_id'] for o in run.snapshot['observations'] if o['kind']=='report_attachment'}),**kw}


@pytest.mark.asyncio
async def test_execution_freezes_bases_and_report_values_requiring_independent_review(data):
    result=await InspectionExecutionService(data[0],current()).create(payload(data))
    assert result['evaluation']['item_verdict']=='fail' and result['evaluation']['product_verdict']=='not_assessed'
    assert result['snapshot']['source_refs'][0]['revision_id']==data[2].id and result['status']=='draft'
    assert result['snapshot']['observations'][0]['validation_status']=='reported'


@pytest.mark.asyncio
async def test_unpublished_or_unconfirmed_requirement_never_yields_conformity(data):
    data[2].publication_status='unpublished';await data[0].flush()
    result=await InspectionExecutionService(data[0],current()).create(payload(data))
    assert result['evaluation']['item_verdict']=='incomplete' and result['current_source_issues']


@pytest.mark.asyncio
async def test_historical_version_not_applied_to_new_production(data):
    body=payload(data);body['production_date']='2026-10-05'
    result=await InspectionExecutionService(data[0],current()).create(body)
    assert result['evaluation']['item_verdict']=='incomplete'


@pytest.mark.asyncio
async def test_cross_tenant_and_other_user_task_access_is_denied(data):
    with pytest.raises(NotFoundError):await InspectionExecutionService(data[0],current(org=OTHER)).create(payload(data))
    with pytest.raises(NotFoundError):await InspectionExecutionService(data[0],current(user=EXPERT)).create(payload(data))


@pytest.mark.asyncio
async def test_report_transcription_needs_explicit_original_verification(data):
    service=InspectionExecutionService(data[0],current());result=await service.create(payload(data));run=await data[0].get(InspectionExecutionRun,result['id'])
    expert=InspectionExecutionService(data[0],current(EXPERT,'expert'))
    with pytest.raises(ValidationError):await expert.review(run.id,review(run,report_values_verified=False))
    result=await expert.review(run.id,review(run))
    assert result['status']=='accepted' and result['evaluation']['item_verdict']=='fail'


@pytest.mark.asyncio
async def test_source_withdrawn_after_execution_blocks_review_and_preserves_snapshot(data):
    result=await InspectionExecutionService(data[0],current()).create(payload(data));run=await data[0].get(InspectionExecutionRun,result['id']);before=copy.deepcopy(run.snapshot)
    data[2].publication_status='withdrawn';await data[0].flush()
    with pytest.raises(ValidationError):await InspectionExecutionService(data[0],current(EXPERT,'expert')).review(run.id,review(run))
    assert run.snapshot==before


@pytest.mark.asyncio
async def test_execution_retry_idempotent_without_changing_data(data):
    body=payload(data);service=InspectionExecutionService(data[0],current());first=await service.create(body);second=await service.create(body)
    assert first['id']==second['id']
    with pytest.raises(ConflictError):await service.create({**body,'production_date':'2022-01-01'})


@pytest.mark.asyncio
@pytest.mark.parametrize('problem',['missing','hash','page','malformed'])
async def test_report_actual_source_and_page_are_required(data,problem):
    body=payload(data)
    if problem=='missing':data[5].content=None
    elif problem=='hash':data[5].content+=b'changed'
    elif problem=='page':body['observations'][0]['report_page']=9999
    else:
        content=b'%PDF-invalid body';data[5].content=content;data[4].sha256=hashlib.sha256(content).hexdigest();data[4].size_bytes=len(content)
    with pytest.raises(ValidationError):await InspectionExecutionService(data[0],current()).create(body)


@pytest.mark.asyncio
async def test_report_recheck_and_structured_review_history(data):
    service=InspectionExecutionService(data[0],current());result=await service.create(payload(data));run=await data[0].get(InspectionExecutionRun,result['id'])
    expert=InspectionExecutionService(data[0],current(EXPERT,'expert'))
    with pytest.raises(ValidationError):await expert.review(run.id,review(run,verified_evidence_ids=[]))
    with pytest.raises(ValidationError):await expert.review(run.id,review(run,evidence_refs=['   ']))
    original=data[5].content;data[5].content=b'corrupted'
    with pytest.raises(ValidationError):await expert.review(run.id,review(run))
    data[5].content=original;before=copy.deepcopy(run.snapshot);body=review(run)
    accepted=await expert.review(run.id,body)
    assert accepted['effective_status']=='accepted' and run.snapshot==before
    action=accepted['review_history'][0]
    assert action['evidence_refs']==body['evidence_refs']
    assert action['verification_snapshot']['verified_evidence_ids']==body['verified_evidence_ids']
    assert action['verification_snapshot']['sources'][0]['page_count']==4
    assert action['verification_snapshot']['sources'][0]['transcription_verified'] is True
    assert accepted['source_validation']['sources'][0]['transcription_verified'] is True
    assert (await expert.review(run.id,body))['row_version']==accepted['row_version']
    data[5].content=None
    assert (await expert.serialize(run))['effective_status']=='needs_reassessment'
    assert run.status=='accepted' and run.snapshot==before


@pytest.mark.asyncio
async def test_same_pdf_copies_do_not_satisfy_independent_observations(data):
    data[2].candidates_json=[{**data[3],'minimum_observations':2}]
    report=QualityAttachment(org_id=ORG,file_name='copy.pdf',mime_type='application/pdf',size_bytes=data[4].size_bytes,
        sha256=data[4].sha256,bucket='fixture',object_key='copy',uploaded_by=AUTHOR)
    data[0].add(report);await data[0].flush()
    inputs=copy.deepcopy(data[1].meta_data['execution_inputs']);original=inputs['report_links'][0]
    source=await data[0].get(QualitySourceRecord,original['source_record_id']);source.attachment_ids=[*source.attachment_ids,report.id]
    inputs['report_links'].append({**original,'attachment_id':report.id});data[1].meta_data={**data[1].meta_data,'execution_inputs':inputs};await data[0].flush()
    body=payload(data);body['observations'].append({**body['observations'][0],'id':report.id,'report_page':4,'report_item':'项目别名'})
    result=await InspectionExecutionService(data[0],current()).create(body)
    assert result['evaluation']['item_verdict']=='incomplete'
    assert result['evaluation']['checks'][0]['independent_observation_count']==1


async def measured_payload(data):
    db,task=data[:2];sid,sample_id,device_id=[str(uuid.uuid4()) for _ in range(3)]
    session=SupervisionRecord(id=sid,org_id=ORG,kind='inspection-sessions',code='session',name='fixture',status='collecting',created_by=AUTHOR,
        data={'task_id':task.id,'sample_ids':[sample_id],'device_ids':[device_id]})
    sample=SupervisionRecord(id=sample_id,org_id=ORG,kind='samples',code='sample',name='fixture',status='active',created_by=AUTHOR,
        data={'task_id':task.id,'sampled_at':'2021-09-01T00:00:00Z'})
    device=SupervisionRecord(id=device_id,org_id=ORG,kind='devices',code='device',name='fixture',status='active',created_by=AUTHOR,
        data={'calibration_status':'expired','calibration_expires_at':'2022-01-01','capabilities':['maximum_speed']})
    history=SupervisionRevision(org_id=ORG,record_id=device_id,version=1,actor_id=AUTHOR,action='activate',created_at=datetime(2021,1,1),
        snapshot={'version':1,'status':'active','data':{'calibration_status':'valid','calibration_expires_at':'2022-01-01T00:00:00Z','capabilities':['maximum_speed']}})
    m={'item':'maximum_speed','value':24.0,'unit':'km/h','method':'7.1','conditions':{'mode':'maximum'},'quality_flag':'valid','measured_at':'2021-09-03T08:00:00+08:00'}
    record=MeasurementRecord(org_id=ORG,session_id=sid,sample_id=sample_id,device_id=device_id,event_id='trial-1',content_hash=fingerprint(m),
        validation_status='accepted',calibration_version='1',data=m)
    db.add_all([session,sample,device,history,record]);await db.flush()
    body=payload(data);body.update(session_id=sid,sample_ids=[sample_id],observations=[{'kind':'measurement_record','id':record.id,'measurement_key':'maximum_speed','sample_id':sample_id}])
    return body,session,sample,device,history,record


@pytest.mark.asyncio
async def test_measurement_event_alias_does_not_create_an_independent_trial(data):
    body,_,_,_,_,record=await measured_payload(data)
    data[2].candidates_json=[{**data[3],'minimum_observations':2}]
    alias=MeasurementRecord(org_id=ORG,session_id=record.session_id,sample_id=record.sample_id,device_id=record.device_id,
        event_id='new-event-same-acquisition',content_hash=record.content_hash,validation_status='accepted',calibration_version='1',data=record.data)
    data[0].add(alias);await data[0].flush()
    body['observations'].append({**body['observations'][0],'id':alias.id})
    result=await InspectionExecutionService(data[0],current()).create(body)
    assert result['evaluation']['checks'][0]['independent_observation_count']==1
    assert result['evaluation']['item_verdict']=='incomplete'


@pytest.mark.asyncio
async def test_measurement_calibration_is_checked_at_measurement_time(data):
    body,*_=await measured_payload(data)
    result=await InspectionExecutionService(data[0],current()).create(body)
    assert result['evaluation']['item_verdict']=='pass' and not result['current_source_issues']
    run=await data[0].get(InspectionExecutionRun,result['id'])
    accepted=await InspectionExecutionService(data[0],current(EXPERT,'expert')).review(run.id,review(run))
    assert accepted['effective_status']=='accepted'


@pytest.mark.asyncio
@pytest.mark.parametrize('problem',['device','sample','calibration','time','version','session'])
async def test_measurement_missing_entities_or_calibration_block_confirmation(data,problem):
    body,session,sample,device,history,record=await measured_payload(data)
    if problem=='device':await data[0].delete(device)
    elif problem=='sample':await data[0].delete(sample)
    elif problem=='calibration':history.snapshot={**history.snapshot,'data':{**history.snapshot['data'],'calibration_expires_at':'2020-01-01'}}
    elif problem=='time':record.data={**record.data,'measured_at':None}
    elif problem=='version':record.calibration_version='made-up'
    else:session.data={**session.data,'device_ids':[]}
    await data[0].flush()
    if problem=='sample':
        with pytest.raises(ValidationError):await InspectionExecutionService(data[0],current()).create(body)
        return
    result=await InspectionExecutionService(data[0],current()).create(body)
    assert result['current_source_issues'] and result['evaluation']['item_verdict']=='incomplete'
    run=await data[0].get(InspectionExecutionRun,result['id'])
    with pytest.raises(ValidationError):await InspectionExecutionService(data[0],current(EXPERT,'expert')).review(run.id,review(run))


@pytest.mark.asyncio
async def test_private_report_is_only_readable_within_submitted_run(data):
    result=await InspectionExecutionService(data[0],current()).create(payload(data))
    expert=InspectionExecutionService(data[0],current(EXPERT,'expert'))
    row,content,_=await expert.report_file(result['id'],data[4].id)
    assert row.id==data[4].id and content.startswith(b'%PDF-')
    with pytest.raises(NotFoundError):await expert.report_file(result['id'],str(uuid.uuid4()))
    from app.services.execution_evidence_service import ExecutionEvidenceService
    with pytest.raises(NotFoundError):await ExecutionEvidenceService(data[0],current(EXPERT,'expert')).file(data[4].id)
