"""Synthetic identities and storage; no professional actions in the live database."""
import copy, hashlib, json, os, uuid
from pathlib import Path
from contextlib import asynccontextmanager
import pytest, pytest_asyncio
from sqlalchemy import MetaData, DateTime, DefaultClause, text, select
from sqlalchemy.ext.asyncio import async_sessionmaker
import test_task_result_bundle as bundle_fixture
import test_inspection_execution_service as base
from app.models.base import Base
from app.models.knowledge_admission import KnowledgeAdmission, KnowledgeAdmissionAction
from app.models.memory import MemoryItem,MemoryOrigin,MemoryEvidence,MemoryEvent,MemoryDependencyEdge,MemorySyncOutbox
from app.models.meeting import MemoryScopeBinding
from app.models.standard_admission import StandardAdmissionReview,StandardSyncOutbox
from app.models.business_number import BusinessNumberSequence,BusinessIdentifier
from app.models.quality_risk import QualityEvidenceItem,QualitySourceRecord,QualityRiskCase
from app.models.user import User
from app.models.inspection_execution import InspectionExecutionRun
from app.core.exceptions import ValidationError, NotFoundError
from app.services.inspection_case_workflow_service import InspectionCaseWorkflowService
from app.services.inspection_execution_service import InspectionExecutionService
from app.services.knowledge_admission_service import KnowledgeAdmissionService,finish_knowledge_projection
from app.services.standard_admission_service import StandardAdmissionService,process_standard_outbox
from app.services.quality_risk_service import QualityRiskService
from app.schemas.quality_risk import RiskCaseCreate,RiskAnalyzeRequest,RiskReviewRequest
from app.services.export_job_service import ExportJobService
from app.services import report_generation_service as generation


@pytest_asyncio.fixture
async def data(monkeypatch):
    generator=bundle_fixture.data.__wrapped__(monkeypatch);data=await anext(generator);db,task,rev,rule,report=data[:5]
    await db.commit();meta=MetaData()
    names={model.__tablename__ for model in [KnowledgeAdmission,KnowledgeAdmissionAction,MemoryItem,MemoryOrigin,
        MemoryEvidence,MemoryEvent,MemoryDependencyEdge,MemorySyncOutbox,MemoryScopeBinding,StandardAdmissionReview,
        StandardSyncOutbox,BusinessNumberSequence,BusinessIdentifier]}
    # Include FK targets in the metadata while leaving their existing tables intact.
    names.update(['standard_document_revisions','standard_documents','inspection_standard_libraries'])
    for name in names:
        table=Base.metadata.tables[name].to_metadata(meta)
        for column in table.c:
            if isinstance(column.type,DateTime) and column.server_default is not None:
                column.server_default=DefaultClause(text('CURRENT_TIMESTAMP'))
    async with db.bind.begin() as conn:await conn.run_sync(meta.create_all)
    doc=await StandardAdmissionService(db,base.ORG).document(rev.document_id)
    task.inspection_standard_id=doc.library_id
    task.meta_data={**task.meta_data,'production_date':'2021-09-03','case_preparation':{
        'case_id':'isolated-r4','title':'R4隔离流程验证','standard_document_id':doc.id,'standard_revision_id':rev.id,
        'report_attachment_id':report.id,'standard_refs':[{'revision_id':rev.id,'candidate_id':rule['id'],'measurement_key':'maximum_speed'}],
        'initial_execution_keys':['maximum_speed'],'planned_items':[],'limitations':['合成账号工程验证，不属于真实专业签认']}}
    await db.commit()
    try:yield data
    finally:await generator.aclose()


@pytest.mark.asyncio
async def test_preparation_flags_cannot_mark_workflow_complete(data):
    task=data[1];task.meta_data={**task.meta_data,'case_preparation':{**task.meta_data['case_preparation'],
        'professional_work_complete':True,'retrieval_reuse_verified':True}}
    await data[0].commit()
    result=await InspectionCaseWorkflowService(data[0],base.current()).read(task.id)
    assert result['can_prepare_execution'] and not result['professional_work_complete']
    assert not result['retrieval_reuse_verified'] and result['product_verdict']=='not_assessed'
    data[2].publication_status='withdrawn';await data[0].commit()
    result=await InspectionCaseWorkflowService(data[0],base.current()).read(task.id)
    assert not result['can_prepare_execution']


@pytest.mark.asyncio
async def test_old_draft_report_does_not_complete_reviewed_version_export_step(data):
    await bundle_fixture.run(data)
    run=await data[0].scalar(select(InspectionExecutionRun))
    job=await bundle_fixture.job(data,execution_run_id=run.id)
    job.status='success';job.file_url='/api/v1/files/isolated-report/fixture.pdf';await data[0].commit()
    service=InspectionCaseWorkflowService(data[0],base.current())
    assert next(s for s in (await service.read(data[1].id))['steps'] if s['key']=='export')['status']=='complete'
    await InspectionExecutionService(data[0],base.current(base.EXPERT,'expert')).review(run.id,base.review(run))
    await data[0].commit()
    assert next(s for s in (await service.read(data[1].id))['steps'] if s['key']=='export')['status']=='pending'


@pytest.mark.asyncio
async def test_workflow_obeys_task_scope_and_rejects_invalid_references(data):
    with pytest.raises(NotFoundError):await InspectionCaseWorkflowService(data[0],base.current(org=base.OTHER)).read(data[1].id)
    data[1].meta_data={**data[1].meta_data,'case_preparation':{'case_id':'incomplete'}}
    await data[0].commit()
    with pytest.raises(ValidationError):await InspectionCaseWorkflowService(data[0],base.current()).read(data[1].id)


@pytest.mark.asyncio
async def test_real_report_selected_item_replay_to_report_and_knowledge(data,monkeypatch,tmp_path):
    package=os.getenv('PIAP_R4_CASE_PACKAGE')
    if not package:pytest.skip('Set PIAP_R4_CASE_PACKAGE for genuine asset replay')
    manifest,assets=__import__('scripts.prepare_industrial_case',fromlist=['load_package']).load_package(package)
    db,task,rev,old_rule,report,storage=data
    from app.models.inspection_execution import InspectionExecutionRun
    from app.schemas.standard_admission import CandidateEdit
    admin=str(uuid.uuid4());peer=str(uuid.uuid4())
    for actor,role in [(admin,'admin'),(peer,'expert')]:
        db.add(User(id=actor,org_id=base.ORG,username=actor,email=actor+'@example.invalid',role=role,is_active=True))
    doc=await StandardAdmissionService(db,base.ORG).document(rev.document_id)
    raw=assets['standard'][1];report_raw=assets['report'][1]
    storage.content=report_raw;report.sha256=hashlib.sha256(report_raw).hexdigest();report.size_bytes=len(report_raw)
    doc.file_hash=hashlib.sha256(raw).hexdigest();rev.file_hash=doc.file_hash
    rev.snapshot={**manifest['standard_metadata'],'file_name':'GB-17761-2018.pdf','file_path':'std-real.pdf','file_hash':doc.file_hash,'file_size':len(raw)}
    # Source pages are a review transcript of the actual PDF, not invented measurements.
    rev.pages_json=[{'page_number':1,'text':'GB 17761-2018 电动自行车安全技术规范 2019-04-15 实施'},
        *[{'page_number':p['standard_page'],'text':p['clause_no']+' '+p['indicator']+'\n'+p['requirement']} for p in manifest['planned_items']]]
    rev.candidates_json=[{'id':str(uuid.uuid4()),'clause_no':p['clause_no'],'page_number':p['standard_page'],
        'source_text':p['requirement'],'status':'pending'} for p in manifest['planned_items']]
    rev.created_by=admin;rev.review_status='pending';rev.publication_status='unpublished';doc.published_revision_id=None;doc.current_revision_id=rev.id
    class Original:
        def get_bytes(self,**kwargs):return raw,'application/pdf'
    monkeypatch.setattr('app.services.standard_admission_service.build_object_storage',lambda:Original())
    author=StandardAdmissionService(db,base.ORG,admin);expert=StandardAdmissionService(db,base.ORG,base.EXPERT)
    def action(**fields):return {'expected_version':rev.row_version,'request_key':str(uuid.uuid4()),
        'reason':'隔离账号对真实原件做流程重放，非正式人工审核','evidence_refs':['original PDF page locator'],**fields}
    refs=[]
    for rule,p in zip(copy.deepcopy(rev.candidates_json),manifest['planned_items']):
        edit=CandidateEdit.model_validate({**action(candidate_id=rule['id']),**{k:p[k] for k in
            ['candidate_type','indicator','measurement_key','unit','method','conditions','requirement','operator','numeric_upper','numeric_lower','numeric_aggregation','minimum_observations']},
            'applicability':manifest['standard_metadata']['scope_notes'],'execution_mode':'numeric'}).model_dump()
        await author.candidate(doc.id,rev.id,edit,actor_role='admin')
        await expert.candidate_review(doc.id,rev.id,action(candidate_id=rule['id'],decision='confirm'),can_confirm=True)
        refs.append({'revision_id':rev.id,'candidate_id':rule['id'],'measurement_key':p['measurement_key']})
    await expert.review(doc.id,rev.id,action(decision='approve'),actor_role='expert')
    await author.publish(doc.id,rev.id,action())
    class Index:
        async def index(self,docs):return {'accepted':len(docs),'failed_embeddings':0}
    publication=await db.scalar(select(StandardSyncOutbox).where(StandardSyncOutbox.revision_id==rev.id,StandardSyncOutbox.action=='publish'))
    await process_standard_outbox(db,publication,indexer=Index())
    source_id=task.meta_data['execution_inputs']['report_links'][0]['source_record_id']
    source=await db.get(QualitySourceRecord,source_id);source.content={'description':'历史报告核对，鸣号汇总值73dB(A)，原始三次读数未公开。'}
    source.authorization_scope='organization'
    task.meta_data={**task.meta_data,'production_date':'2019-08-01','case_preparation':{**task.meta_data['case_preparation'],
        'standard_refs':refs,'initial_execution_keys':['whole_mass'],'planned_items':manifest['planned_items']}}
    await db.commit()
    def request(key):
        p=next(p for p in manifest['planned_items'] if p['measurement_key']==key)
        return {**base.payload(data),'request_key':str(uuid.uuid4()),'production_date':'2019-08-01',
            'requirements':[{k:v for k,v in r.items() if k!='measurement_key'} for r in refs if r['measurement_key']==key],
            'observations':[{**base.payload(data)['observations'][0],'measurement_key':key,'value':p['value'],'unit':p['unit'],
                'method':p['method'],'conditions':{},'report_page':p['report_page'],'report_item':p['report_item']}]}
    executions=InspectionExecutionService(db,base.current())
    incomplete=await executions.create(request('horn_sound'))
    assert incomplete['evaluation']['item_verdict'] in {'uncertain','incomplete'}
    assert incomplete['evaluation']['checks'][0]['status']=='uncertain'
    assert len(incomplete['snapshot']['observations'])==1
    result=await executions.create(request('whole_mass'));row=await db.get(InspectionExecutionRun,result['id'])
    assert result['evaluation']['item_verdict']=='pass'
    await InspectionExecutionService(db,base.current(base.EXPERT,'expert')).review(row.id,base.review(row,evidence_refs=['JG2128520085 uploaded PDF p2, mass51.4kg']))
    risk=QualityRiskService(db,base.current(base.EXPERT,'expert'));risk.storage=storage;await risk.materialize_evidence(source)
    case=await risk.create_risk_case(RiskCaseCreate(title='隔离历史线索',scope_type='category',scope={'name':'电动自行车'},source_record_ids=[source.id]))
    assessment=await risk.analyze_risk(case['id'],RiskAnalyzeRequest(inspection_execution_run_id=row.id))
    try:
        reviewer=QualityRiskService(db,base.current(peer,'expert'));reviewer.storage=storage
        await reviewer.review_risk(case['id'],RiskReviewRequest(decision='accept',
            comment='隔离流程确认受限历史线索，未知现况与发生概率；需要原始记录复核',risk_level='medium',recommendations=['补齐三次鸣号原始记录']))
    except ValidationError as exc:
        raise AssertionError(exc.detail) from exc
    jobs=ExportJobService(db,base.ORG,actor_user_id=base.EXPERT,actor_role='expert')
    job=await jobs.create_job(base.EXPERT,{'report_name':'R4真实材料隔离重放','report_type':'single_task','format':'pdf',
        'config_json':{'task_id':task.id,'execution_run_id':row.id}})
    factory=async_sessionmaker(db.bind,expire_on_commit=False)
    @asynccontextmanager
    async def sessions():
        async with factory() as session:yield session
    monkeypatch.setattr(generation,'get_session',sessions);saved=[]
    class ExportStorage:
        def ensure_bucket(self,bucket):pass
        def put_bytes(self,**fields):saved.append(fields)
    monkeypatch.setattr(generation,'build_object_storage',lambda:ExportStorage())
    await generation.generate_report(job_id=job.id,org_id=base.ORG)
    assert saved; (tmp_path/'R4真实材料隔离重放.pdf').write_bytes(saved[0]['data'])
    knowledge=KnowledgeAdmissionService(db,base.current(base.EXPERT,'expert'))
    candidate=await knowledge.submit({'request_key':str(uuid.uuid4()),'claim':'该历史报告所列整车质量51.4kg，核对所选条款限值55kg；产品整体未评定。',
        'product_category':'电动自行车','applicability':'仅该历史报告和选定样品项目，不扩展到当前同型号新样品',
        'limitations':'鸣号缺三次原始读数，历史报告不能证明当前状态或产品整体结论。',
        'sources':[{'kind':'inspection_execution','id':row.id,'quote':''}],
        'requested_scope':'organization','consent_to_review':True,'consent_to_share':True})
    item=await db.get(KnowledgeAdmission,candidate['id'])
    def ka():return {'expected_version':item.row_version,'request_key':str(uuid.uuid4()),'reason':'隔离账号重放准入，非正式专业签认','evidence_refs':['bounded execution original report p2']}
    await KnowledgeAdmissionService(db,base.current(peer,'expert')).review(item.id,{**ka(),'decision':'approve'})
    governance=KnowledgeAdmissionService(db,base.current(admin,'admin'))
    await governance.sharing(item.id,{**ka(),'decision':'approve'})
    await governance.publish(item.id,ka());await finish_knowledge_projection(db,base.ORG,item.id);await db.commit()
    assert item.publication_status=='published' and not await knowledge.source_issues(item)
    from app.services.knowledge_admission_service import guard_managed_memory
    memory=await knowledge.memory(item)
    assert await guard_managed_memory(db,base.ORG,[memory])==[memory]
    # Source qualification is rechecked before downstream reuse; withdrawal removes eligibility.
    rev.publication_status='withdrawn';await db.commit()
    assert await knowledge.source_issues(item)
    assert await guard_managed_memory(db,base.ORG,[memory])==[]
