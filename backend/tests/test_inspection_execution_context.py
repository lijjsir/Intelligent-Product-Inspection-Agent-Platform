"""Task-scoped selection, explicit report linking and published policy consumption."""
import copy,uuid
from datetime import date
import pytest
from sqlalchemy import select
from test_inspection_execution_service import data,current,payload,review,measured_payload,ORG,OTHER,AUTHOR,EXPERT
from app.core.exceptions import NotFoundError,ValidationError,ConflictError,ForbiddenError
from app.models.quality_risk import ProductCategory,QualityProduct,QualityProductionBatch,QualitySourceRecord
from app.models.supervision import SupervisionRecord
from app.models.product import ProductLine,ProductSku,ProductBatch
from app.models.inspection_spec import InspectionSpec
from app.models.inspection_execution import InspectionExecutionRun,InspectionPolicyPublication
from app.services.inspection_execution_service import InspectionExecutionService
from app.services.inspection_execution_context_service import InspectionExecutionContextService


def uid():return str(uuid.uuid4())


async def product_scope(data):
    db,task=data[:2]
    category=ProductCategory(org_id=ORG,code='EBIKE',name='电动自行车',is_active=True)
    db.add(category);await db.flush()
    product=QualityProduct(org_id=ORG,category_id=category.id,name='工业产品',brand='fixture',attributes={},is_active=True)
    db.add(product);await db.flush()
    batch=QualityProductionBatch(org_id=ORG,product_id=product.id,original_batch_no='BATCH-A',production_date=date(2021,9,3),created_by=AUTHOR)
    db.add(batch);await db.flush()
    task.quality_product_id=product.id;task.product_category_id=category.id;task.product_id=product.id
    task.meta_data={**task.meta_data,'quality_batch_id':batch.id};await db.flush()
    return category,product,batch


async def publish_policy(data,**fields):
    spec=InspectionSpec(id=uid(),org_id=ORG,spec_code=data[1].spec_code,name='隔离执行策略',version='v1',product_family='电动自行车',
        required_image_count=2,required_views=['正面','背面'],is_active=True)
    data[0].add(spec);await data[0].flush()
    body={'request_key':uid(),'expected_updated_at':str(spec.updated_at),'required_fields':['product_category','production_date','sample_ids'],
        'input_modes':['image','measurement','mixed','report'],'required_image_count':2,'required_views':['正面','背面'],
        'review_on_fail':True,'reason':'隔离策略输入及来源核对',**fields}
    published=await InspectionExecutionService(data[0],current(EXPERT,'admin')).publish_policy(spec.id,body)
    return published,spec,body


@pytest.mark.asyncio
async def test_context_returns_task_bound_values_and_hides_unrelated_entities(data):
    body,session,sample,device,_,measurement=await measured_payload(data)
    unrelated=SupervisionRecord(id=uid(),org_id=ORG,kind='samples',code='elsewhere',name='不属于本任务',created_by=AUTHOR,data={'task_id':uid()})
    foreign=SupervisionRecord(id=uid(),org_id=OTHER,kind='inspection-sessions',code='foreign',name='另一租户',created_by=AUTHOR,data={'task_id':data[1].id})
    data[0].add_all([unrelated,foreign]);await data[0].flush()
    context=await InspectionExecutionContextService(data[0],current()).context(data[1])
    assert [s['id'] for s in context['sessions']]==[session.id]
    assert sample.id in {s['id'] for s in context['samples']} and unrelated.id not in {s['id'] for s in context['samples']}
    assert context['measurements'][0]['data']['value']==24.0 and context['measurements'][0]['id']==measurement.id
    with pytest.raises(NotFoundError):await InspectionExecutionService(data[0],current(org=OTHER)).task(data[1].id)


@pytest.mark.asyncio
async def test_explicit_report_link_is_scoped_idempotent_and_preserves_original_sample_code(data):
    db,task=data[:2];source_id=task.meta_data['execution_inputs']['report_links'][0]['source_record_id']
    task.meta_data={'input_mode':'report','product_category_name':'电动自行车'};await db.flush()
    service=InspectionExecutionContextService(db,current());context=await service.context(task)
    body={'request_key':uid(),'expected_context_hash':context['context_hash'],'source_record_id':source_id,'attachment_id':data[4].id,
        'sample_codes':['原样品-A'],'reason':'核对报告与当前任务工业产品的对应关系'}
    linked=await service.link_report(task,body)
    original=linked['reports'][0]['samples'][0]
    assert original['label']=='原样品-A' and original['id'].startswith('report-sample:')
    assert linked['reports'][0]['page_count']==4 and linked['context_hash']!=context['context_hash']
    assert (await service.link_report(task,body))['context_hash']==linked['context_hash']
    assert len(task.meta_data['execution_inputs']['events'])==1
    source=await db.get(QualitySourceRecord,source_id);assert source.authorization_scope=='private'
    with pytest.raises(ConflictError):await service.link_report(task,{**body,'sample_codes':['另一个样品']})
    request=payload(data);request['sample_ids']=[original['id']];request['observations'][0]['sample_id']=original['id'];request['context_hash']=linked['context_hash']
    result=await InspectionExecutionService(db,current()).create(request)
    assert result['snapshot']['observations'][0]['sample_label']=='原样品-A'
    assert result['snapshot']['task_context']['scope']['task_id']==task.id


@pytest.mark.asyncio
async def test_unlinked_report_and_forged_samples_are_rejected(data):
    data[1].meta_data={'input_mode':'report'};await data[0].flush()
    with pytest.raises(ValidationError):await InspectionExecutionService(data[0],current()).create(payload(data))


@pytest.mark.asyncio
@pytest.mark.parametrize('problem',['standard','inferred','wrong_product','private_other','missing_file'])
async def test_report_link_checks_source_kind_scope_access_and_original(data,problem):
    _,product,_=await product_scope(data);db,task=data[:2]
    source_id=task.meta_data['execution_inputs']['report_links'][0]['source_record_id'];source=await db.get(QualitySourceRecord,source_id)
    task.meta_data={**task.meta_data,'execution_inputs':{}};await db.flush()
    if problem=='standard':source.record_type='standard_document'
    elif problem=='inferred':source.data_nature='inferred'
    elif problem=='wrong_product':source.product_ref={'product_id':uid()}
    elif problem=='private_other':source.created_by=uid()
    else:data[5].content=None
    await db.flush();service=InspectionExecutionContextService(db,current());context=await service.context(task)
    body={'request_key':uid(),'expected_context_hash':context['context_hash'],'source_record_id':source_id,'attachment_id':data[4].id,'sample_codes':['A'],'reason':'必须核对实际原件和对象'}
    with pytest.raises((ValidationError,NotFoundError)):await service.link_report(task,body)


@pytest.mark.asyncio
async def test_scope_comes_from_product_and_batch_and_date_cannot_be_overridden(data):
    _,product,batch=await product_scope(data)
    context=await InspectionExecutionContextService(data[0],current()).context(data[1])
    assert context['task_scope']['production_date']=='2021-09-03' and context['task_scope']['quality_product_id']==product.id
    body=payload(data);body['production_date']='2022-01-01'
    result=await InspectionExecutionService(data[0],current()).create(body)
    assert result['evaluation']['item_verdict']=='incomplete'
    assert '执行生产日期与已登记批次日期不一致' in result['evaluation']['missing_inputs']


@pytest.mark.asyncio
async def test_stale_selection_token_does_not_create_a_run(data):
    body,*_=await measured_payload(data)
    context=await InspectionExecutionContextService(data[0],current()).context(data[1]);body['context_hash']=context['context_hash']
    data[1].meta_data={**data[1].meta_data,'input_mode':'mixed'};await data[0].flush()
    with pytest.raises(ConflictError):await InspectionExecutionService(data[0],current()).create(body)
    assert not (await data[0].scalars(select(InspectionExecutionRun))).all()


@pytest.mark.asyncio
async def test_published_report_policy_is_consumed_without_image_gate_or_product_limits(data):
    published,_,_=await publish_policy(data)
    body=payload(data)
    with pytest.raises(ValidationError,match='明确选择'):await InspectionExecutionService(data[0],current()).create(body)
    body['policy_id']=published['id'];result=await InspectionExecutionService(data[0],current()).create(body)
    assert result['evaluation']['item_verdict']=='fail' and not result['evaluation']['missing_inputs']
    assert result['snapshot']['policy']['publication_id']==published['id']
    assert result['snapshot']['policy']['product_limits']=='from_confirmed_standard_requirements'
    assert result['snapshot']['policy_inputs']['input_mode']=='report'


@pytest.mark.asyncio
async def test_published_policy_required_fields_and_views_are_enforced(data):
    published,_,_=await publish_policy(data,required_fields=['quality_product_id'])
    body=payload(data);body['policy_id']=published['id']
    result=await InspectionExecutionService(data[0],current()).create(body)
    assert '任务缺少策略要求字段：具体产品' in result['evaluation']['missing_inputs']
    data[1].meta_data={**data[1].meta_data,'input_mode':'image'}
    data[1].image_items=[{'url':'fixture://image-a','hash':'image-a'},{'url':'fixture://copy','hash':'image-a'}];await data[0].flush()
    body['request_key']=uid();body['image_view_assignments']=[{'image_hash':'image-a','view':'正面'},{'image_hash':'image-a','view':'背面'}]
    result=await InspectionExecutionService(data[0],current()).create(body)
    assert any('至少2张独立图片' in m for m in result['evaluation']['missing_inputs'])
    assert '同一图片不能充当多个独立视角' in result['evaluation']['missing_inputs']


@pytest.mark.asyncio
async def test_policy_wrong_mode_is_rejected_and_withdrawal_invalidates_frozen_run(data):
    published,_,_=await publish_policy(data,input_modes=['measurement'])
    body=payload(data);body['policy_id']=published['id']
    with pytest.raises(ValidationError,match='不适用'):await InspectionExecutionService(data[0],current()).create(body)
    row=await data[0].get(InspectionPolicyPublication,published['id']);row.status='withdrawn';await data[0].flush()
    published,_,_=await publish_policy(data)
    body['policy_id']=published['id'];result=await InspectionExecutionService(data[0],current()).create(body)
    run=await data[0].get(InspectionExecutionRun,result['id']);before=copy.deepcopy(run.snapshot)
    (await data[0].get(InspectionPolicyPublication,published['id'])).status='withdrawn';await data[0].flush()
    with pytest.raises(ValidationError):await InspectionExecutionService(data[0],current(EXPERT,'expert')).review(run.id,review(run))
    assert run.snapshot==before


@pytest.mark.asyncio
async def test_trial_conditions_are_labeled_separately_from_product_requirements(data):
    data[2].candidates_json=[{**data[3],'candidate_type':'method_condition'}]
    result=await InspectionExecutionService(data[0],current()).create(payload(data))
    assert result['evaluation']['requirement_groups']['method_condition']['count']==1
    assert result['evaluation']['requirement_groups']['inspection_requirement']['verdict']=='not_assessed'
    assert result['evaluation']['product_verdict']=='not_assessed'
    data[2].candidates_json=[{**data[3],'candidate_type':None}];await data[0].flush()
    result=await InspectionExecutionService(data[0],current()).create(payload(data))
    assert result['evaluation']['item_verdict']=='incomplete'


@pytest.mark.asyncio
async def test_batch_or_report_source_change_invalidates_frozen_review_basis(data):
    _,_,batch=await product_scope(data)
    service=InspectionExecutionService(data[0],current());result=await service.create(payload(data));run=await data[0].get(InspectionExecutionRun,result['id'])
    before=copy.deepcopy(run.snapshot);batch.production_date=date(2022,1,1);await data[0].flush()
    assert any('冻结对象' in m for m in await service.validity(run))
    with pytest.raises(ValidationError):await InspectionExecutionService(data[0],current(EXPERT,'expert')).review(run.id,review(run))
    assert run.snapshot==before


@pytest.mark.asyncio
async def test_private_expert_report_cannot_grant_access_by_attaching_to_another_users_task(data):
    db,task=data[:2];source_id=task.meta_data['execution_inputs']['report_links'][0]['source_record_id']
    source=await db.get(QualitySourceRecord,source_id);source.created_by=EXPERT;data[4].uploaded_by=EXPERT
    task.meta_data={**task.meta_data,'execution_inputs':{}};await db.flush()
    service=InspectionExecutionContextService(db,current(EXPERT,'expert'));context=await service.context(task)
    with pytest.raises(ValidationError,match='私有报告'):
        await service.link_report(task,{'request_key':uid(),'expected_context_hash':context['context_hash'],'source_record_id':source_id,
            'attachment_id':data[4].id,'sample_codes':['A'],'reason':'不能以任务关联绕过私有资料授权'})


@pytest.mark.asyncio
async def test_native_measurement_value_cannot_be_overridden_by_execution_request(data):
    body,*_=await measured_payload(data)
    body['observations'][0].update(value=0.0,unit='fake',method='fake',conditions={})
    result=await InspectionExecutionService(data[0],current()).create(body)
    obs=result['snapshot']['observations'][0]
    assert obs['value']==24.0 and obs['unit']=='km/h' and obs['method']=='7.1' and obs['conditions']=={'mode':'maximum'}


@pytest.mark.asyncio
async def test_empty_r2_defaults_preserve_legacy_idempotency(data):
    body=payload(data);service=InspectionExecutionService(data[0],current());result=await service.create(body)
    repeated=await service.create({**body,'context_hash':None,'image_view_assignments':[]})
    assert repeated['id']==result['id']


@pytest.mark.asyncio
async def test_policy_publication_and_withdrawal_require_governance_permission(data):
    published,spec,body=await publish_policy(data)
    for actor in [current(),current(EXPERT,'expert')]:
        with pytest.raises(ForbiddenError):await InspectionExecutionService(data[0],actor).publish_policy(spec.id,{**body,'request_key':uid()})
        with pytest.raises(ForbiddenError):await InspectionExecutionService(data[0],actor).withdraw_policy(published['id'],{'reason':'不应允许专业角色直接治理策略'})
    admin=InspectionExecutionService(data[0],current(EXPERT,'admin'))
    await admin.withdraw_policy(published['id'],{'reason':'撤回隔离验证版本'})
    assert (await admin.withdraw_policy(published['id'],{'reason':'相同版本重复撤回'}))['status']=='withdrawn'


@pytest.mark.asyncio
async def test_native_sample_batch_must_match_task_and_is_rechecked_after_creation(data):
    body,_,sample,_,_,_=await measured_payload(data);db,task=data[:2]
    line=ProductLine(org_id=ORG,code='LINE-FIXTURE',name='隔离产品线',is_active=True);db.add(line);await db.flush()
    sku=ProductSku(org_id=ORG,product_line_id=line.id,code='SKU-FIXTURE',name='隔离型号',is_active=True);db.add(sku);await db.flush()
    batch=ProductBatch(org_id=ORG,product_sku_id=sku.id,batch_no='NATIVE-BATCH',name='隔离批次',production_date=date(2021,9,3),is_active=True)
    db.add(batch);await db.flush();task.product_sku_id=sku.id;task.batch_id=batch.id
    sample.data={**sample.data,'product_sku_id':sku.id,'batch_id':batch.id};await db.flush()
    service=InspectionExecutionService(db,current());result=await service.create(body);run=await db.get(InspectionExecutionRun,result['id'])
    assert result['evaluation']['item_verdict']=='pass'
    sample.data={**sample.data,'batch_id':uid()};await db.flush()
    assert any('样品关联' in issue for issue in await service.validity(run))
    with pytest.raises(ValidationError):await InspectionExecutionService(db,current(EXPERT,'expert')).review(run.id,review(run))
