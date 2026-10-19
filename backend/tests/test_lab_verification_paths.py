"""Validation planning is separate from accepted conclusions and real execution."""
from datetime import datetime
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError as SchemaError
from sqlalchemy import DateTime,DefaultClause,MetaData,func,select,text

from test_quality_pagination import domain,flow,formal,collaboration,sampling,completion  # noqa: F401
from app.models import Base
from app.models.quality_risk import QualityRiskAssessment,QualityRiskCase,ProductCategory,QualityProduct,QualitySourceRecord
from app.models.supervision import SupervisionRecord
from app.models.task import InspectionTask
from app.models.inspection_spec import InspectionSpec
from app.models.inspection_standard_library import InspectionStandardLibrary
from app.core.exceptions import ConflictError,ForbiddenError,NotFoundError,ValidationError
from app.schemas.risk_completion import LabDecision,LabTaskCreate,LabReturn,RiskReportCreate
from app.schemas.quality_risk import QualityEventCreate
from app.services.risk_lab_service import RiskLabService
from app.services.risk_lab_task_service import RiskLabTaskService
from app.services.risk_report_service import RiskReportService
from app.services.task_service import TaskService
from app.services.quality_risk_service import stable_hash


async def request(formal,path='task',*,preliminary=True):
    db,risk,_,_,case,assessment=formal
    if preliminary:
        row=await db.get(QualityRiskAssessment,assessment['id']);row.status='awaiting_review';row.reviewed_by=None;row.reviewed_at=None;row.trust_status='unverified';await db.flush()
    lab=RiskLabService(db,risk('expert').current)
    target=await lab.demo.risk.risk_case(case['id']);basis,_=await lab.demo.capture(target)
    decision=LabDecision(assessment_id=assessment['id'],expected_basis_hash=stable_hash(basis),verification_path=path,
        mode='skip' if path=='skip' else 'verify',purpose='【隔离】补充原始温升依据，不作最终风险结论')
    link=await lab.decide(case['id'],decision)
    return lab,link,decision


async def standard(db,org):
    metadata=MetaData()
    for name in ('inspection_specs','inspection_tasks','inspection_results','stability_reports'):
        table=Base.metadata.tables[name].to_metadata(metadata)
        for col in table.c:
            if col.server_default is not None:col.server_default=DefaultClause(text('CURRENT_TIMESTAMP')) if isinstance(col.type,DateTime) else None
    async with db.bind.begin() as conn:await conn.run_sync(metadata.create_all)
    spec=InspectionSpec(id=str(uuid4()),org_id=org,spec_code='ISOLATED-VALIDATION',name='【隔离配置】非正式标准',version='fixture',is_active=True,required_image_count=1,required_views=[])
    db.add(spec);await db.flush()
    item=InspectionStandardLibrary(id=str(uuid4()),org_id=org,name='【隔离配置】仅用于创建流程测试',product_family='隔离测试',spec_code=spec.spec_code,
        inspection_spec_id=spec.id,rag_space_ids=[],is_active=True)
    db.add(item);await db.flush();return item


async def attach_product(formal):
    db,risk,_,_,case,_=formal
    category=ProductCategory(org_id=risk('expert').org_id,code='ISOLATED-'+uuid4().hex[:8],name='隔离产品类别',is_active=True)
    db.add(category);await db.flush()
    product=QualityProduct(org_id=category.org_id,category_id=category.id,name='【隔离】验证对象',is_active=True,attributes={})
    db.add(product);await db.flush()
    row=await db.get(QualityRiskCase,case['id']);row.scope={**row.scope,'product_id':product.id,'category_id':category.id};case['scope']=row.scope
    await db.flush()


@pytest.mark.asyncio
@pytest.mark.parametrize('path',['skip','report','task'])
async def test_can_plan_before_review_but_cannot_generate_formal_report(formal,path):
    db,_,_,_,case,assessment=formal
    before=await db.scalar(select(func.count()).select_from(InspectionTask))
    lab,link,decision=await request(formal,path)
    assert link['request_stage']=='preliminary' and link['status']=='validation_planned' and link['verification_path']==path
    assert link['task_id'] is None and (await db.get(QualityRiskAssessment,assessment['id'])).status=='awaiting_review'
    assert (await lab.decide(case['id'],decision))['reused']
    assert await db.scalar(select(func.count()).select_from(InspectionTask))==before
    if path=='task':
        context=await RiskLabTaskService(lab).context(link['id'])
        assert not context['can_create'] and any('具体产品' in message for message in context['blockers'])
    from app.services.risk_decision_context_service import RiskDecisionContextService
    with pytest.raises(ValidationError):await RiskDecisionContextService(db,lab.current).accepted(case['id'])
    with pytest.raises((ConflictError,ValidationError,ForbiddenError)):
        await RiskReportService(db,lab.current).create(case['id'],RiskReportCreate(assessment_id=assessment['id'],expected_basis_hash=decision.expected_basis_hash))
    with pytest.raises((ConflictError,ValidationError,ForbiddenError)):
        await lab.decide(case['id'],decision.model_copy(update={'verification_path':None}))


def test_path_schema_rejects_task_in_report_or_skipped_request():
    for path,mode in [('report','verify'),('skip','skip')]:
        with pytest.raises(SchemaError):LabDecision(assessment_id=uuid4(),expected_basis_hash='a'*64,mode=mode,purpose='合法长度',verification_path=path,task_id=uuid4())


@pytest.mark.asyncio
async def test_create_preparation_task_once_and_restore_origin(formal,monkeypatch):
    db,risk,_,_,case,_=formal
    await attach_product(formal)
    lab,link,_=await request(formal)
    config=await standard(db,lab.org_id);svc=RiskLabTaskService(lab)
    context=await svc.context(link['id']);assert context['can_create'] and context['product_id']==case['scope']['product_id']
    runner=AsyncMock(side_effect=AssertionError('preparation must not launch execution'))
    monkeypatch.setattr('app.services.task_execution_service.launch_task_execution',runner)
    payload=LabTaskCreate(expected_revision=link['revision'],expected_basis_hash=context['basis_hash'],request_key=uuid4(),inspection_standard_id=config.id)
    before=await db.scalar(select(func.count()).select_from(InspectionTask))
    first=await svc.create(link['id'],payload);again=await svc.create(link['id'],payload)
    assert first['task_id']==again['task_id'] and again['reused']
    assert await db.scalar(select(func.count()).select_from(InspectionTask))==before+1
    task=await db.get(InspectionTask,first['task_id'])
    assert task.status=='pending' and task.meta_data['risk_verification_id']==link['id'] and task.meta_data['input_mode']=='measurement'
    assert not runner.called and not task.image_urls
    fetched=await TaskService(db,lab.org_id,actor_user_id=lab.actor,actor_role=lab.current.role).get_task(task.id)
    assert fetched.risk_verification_id==link['id']
    origin=await svc.origin(link['id'],task.id)
    assert origin['case_id']==case['id'] and origin['purpose']==link['purpose']
    with pytest.raises(ConflictError):await svc.create(link['id'],payload.model_copy(update={'request_key':uuid4()}))
    with pytest.raises(ConflictError):await svc.create(link['id'],payload.model_copy(update={'priority':9}))
    with pytest.raises(NotFoundError):await svc.origin(link['id'],str(uuid4()))
    peer=RiskLabTaskService(RiskLabService(db,risk('expert2').current))
    with pytest.raises(ForbiddenError):await peer.create(link['id'],payload)
    (await db.get(QualityRiskAssessment,link['assessment_id'])).deleted_at=datetime.utcnow();await db.flush()
    with pytest.raises(NotFoundError):await svc.origin(link['id'],task.id)


@pytest.mark.asyncio
async def test_source_drift_and_history_require_a_fresh_request(formal):
    db,_,_,_,case,assessment=formal
    await attach_product(formal)
    lab,link,_=await request(formal);config=await standard(db,lab.org_id);svc=RiskLabTaskService(lab)
    context=await svc.context(link['id'])
    payload=LabTaskCreate(expected_revision=link['revision'],expected_basis_hash=context['basis_hash'],request_key=uuid4(),inspection_standard_id=config.id)
    row=await db.get(QualityRiskCase,case['id']);row.scope={**row.scope,'unit_serial_ref':'明确追加的隔离单件'};await db.flush()
    with pytest.raises(ConflictError):await svc.create(link['id'],payload)
    fresh=await svc.context(link['id']);assert not fresh['can_create']
    updated=await lab.decide(case['id'],LabDecision(assessment_id=assessment['id'],expected_basis_hash=fresh['basis_hash'],expected_revision=link['revision'],
        mode='verify',verification_path='task',purpose=link['purpose']))
    assert updated['revision']==link['revision']+1
    assert (await svc.context(link['id']))['can_create']
    old=await db.get(QualityRiskAssessment,assessment['id'])
    db.add(QualityRiskAssessment(org_id=lab.org_id,risk_case_id=case['id'],version=old.version+1,scope=old.scope,status='draft',risk_level='unknown',trust_status='unverified'))
    await db.flush()
    assert not (await svc.context(link['id']))['can_create']


@pytest.mark.asyncio
async def test_task_creation_rolls_back_with_binding_failure(formal,monkeypatch):
    db,_,_,_,_,_=formal
    await attach_product(formal)
    lab,link,_=await request(formal);config=await standard(db,lab.org_id);svc=RiskLabTaskService(lab);ctx=await svc.context(link['id'])
    payload=LabTaskCreate(expected_revision=link['revision'],expected_basis_hash=ctx['basis_hash'],request_key=uuid4(),inspection_standard_id=config.id)
    before=await db.scalar(select(func.count()).select_from(InspectionTask))
    async def fail(*args):raise ValidationError('模拟关联序列化失败')
    monkeypatch.setattr(lab,'serialize',fail)
    with pytest.raises(ValidationError):
        async with db.begin_nested():await svc.create(link['id'],payload)
    assert await db.scalar(select(func.count()).select_from(InspectionTask))==before
    restored=await db.get(SupervisionRecord,link['id'],populate_existing=True)
    assert not restored.data.get('task_id') and not restored.data.get('task_creation')


@pytest.mark.asyncio
async def test_report_path_has_no_task_and_returns_intake_context(formal):
    db,_,_,_,case,_=formal
    lab,link,_=await request(formal,'report')
    ctx=await lab.intake_context(link['id'])
    assert ctx['case_id']==case['id'] and ctx['product_id'] is None
    assert not (await RiskLabTaskService(lab).context(link['id']))['can_create']
    with pytest.raises(ConflictError):
        await RiskLabTaskService(lab).create(link['id'],LabTaskCreate(expected_revision=1,expected_basis_hash='a'*64,request_key=uuid4(),inspection_standard_id=uuid4()))


@pytest.mark.asyncio
async def test_demo_cannot_create_real_tasks(completion):
    _,_,_,case,_,assessment,_,_,lab,_,_,_=completion
    service=lab();basis,_=await service.demo.capture(await service.demo.risk.risk_case(case['id']))
    link=await service.decide(case['id'],LabDecision(assessment_id=assessment['id'],expected_basis_hash=stable_hash(basis),mode='verify',verification_path='task',purpose='【演示】只能申请'))
    ctx=await RiskLabTaskService(service).context(link['id']);assert not ctx['can_create']
    with pytest.raises(ConflictError):await RiskLabTaskService(service).create(link['id'],LabTaskCreate(expected_revision=link['revision'],expected_basis_hash=ctx['basis_hash'],request_key=uuid4(),inspection_standard_id=uuid4()))


@pytest.mark.asyncio
async def test_existing_report_returns_without_task_and_checks_batch(formal):
    db,risk,_,_,case,assessment=formal
    await attach_product(formal)
    row=await db.get(QualityRiskCase,case['id']);row.scope={**row.scope,'production_batch_ref':'ISOLATED-BATCH-A'};case['scope']=row.scope;await db.flush()
    lab,link,_=await request(formal,'report')
    async def material(batch):
        return await risk('expert').create_event(QualityEventCreate(record_type='inspection_report',data_nature='observed',
            content={'text':'【隔离测试原文】仅验证接入与回流，不是真实检测报告'},origin_label='隔离服务测试，非真实业务',
            product_ref={'product_id':case['scope']['product_id'],'production_batch_ref':batch}))
    wrong=await material('ISOLATED-BATCH-B');good=await material('ISOLATED-BATCH-A')
    assert wrong['id'] not in {r['id'] for r in (await lab.option_page(case['id'],'records'))['items']}
    with pytest.raises(ValidationError):await lab.return_records(link['id'],LabReturn(expected_revision=link['revision'],record_ids=[wrong['id']],note='不得混用批次'))
    returned=await lab.return_records(link['id'],LabReturn(expected_revision=link['revision'],record_ids=[good['id']],note='【隔离】补证进入原事项'))
    assert returned['task_id'] is None and returned['added_new_evidence']
    assert good['id'] in (await db.get(QualityRiskCase,case['id'])).source_record_ids
    assert (await db.get(QualityRiskAssessment,assessment['id'])).status=='awaiting_review'


@pytest.mark.asyncio
async def test_task_path_cannot_substitute_unreviewed_material_and_http_limits(formal):
    from fastapi import FastAPI
    from httpx import AsyncClient,ASGITransport
    from app.api.v1.quality_risk import router,risk_lab_service
    await attach_product(formal)
    db,_,_,_,case,_=formal;lab,link,_=await request(formal)
    with pytest.raises(ValidationError):await lab.return_records(link['id'],LabReturn(expected_revision=link['revision'],record_ids=[str(uuid4())],note='不得代替检测复核'))
    app=FastAPI();app.include_router(router);app.dependency_overrides[risk_lab_service]=lambda:lab
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        prefix='/risk-laboratory-verifications/'+link['id']
        response=await client.get(prefix+'/task-preparation');assert response.status_code==200 and response.json()['data']['can_create']
        assert (await client.post(prefix+'/tasks',json={'expected_revision':0})).status_code==422
        assert (await client.post(prefix+'/tasks',json={'expected_revision':1,'expected_basis_hash':'a'*64,'request_key':str(uuid4()),'inspection_standard_id':str(uuid4()),'status':'done'})).status_code==422


@pytest.mark.asyncio
async def test_other_organization_cannot_read_or_create_for_request(formal):
    from app.models import Organization,User
    from app.schemas.user import CurrentUser
    db,_,_,_,_,_=formal;lab,link,_=await request(formal,'report')
    oid,uid=str(uuid4()),str(uuid4())
    db.add(Organization(id=oid,slug='isolated-'+uuid4().hex[:8],name='隔离的另一组织',settings={'quality_supervision_enabled':True},is_active=True))
    db.add(User(id=uid,org_id=oid,username='isolated-other',email='isolated-other@example.invalid',role='expert',is_active=True))
    await db.flush()
    foreign=RiskLabService(db,CurrentUser(user_id=uid,org_id=oid,role='expert'))
    with pytest.raises(NotFoundError):await foreign.intake_context(link['id'])
    with pytest.raises(NotFoundError):await RiskLabTaskService(foreign).context(link['id'])
    with pytest.raises(NotFoundError):await RiskLabTaskService(foreign).create(link['id'],LabTaskCreate(expected_revision=1,expected_basis_hash='a'*64,request_key=uuid4(),inspection_standard_id=uuid4()))
