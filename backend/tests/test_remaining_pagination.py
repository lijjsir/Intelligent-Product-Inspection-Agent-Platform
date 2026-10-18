"""Isolated large reference and collaboration datasets; no business data changes."""
import copy
from datetime import datetime,timedelta
from uuid import uuid4

import pytest
from sqlalchemy import DateTime,DefaultClause,MetaData,insert,select,text

from test_supervision import domain as supervision_domain  # noqa: F401
from test_quality_pagination import domain,collaboration,sampling,flow  # noqa: F401
from test_inspection_execution_service import data as native_data,current as native_current,measured_payload,review as native_review,EXPERT
from app.core.exceptions import ForbiddenError,NotFoundError,ValidationError
from app.models import Base
from app.models.collab import CollabMessage,CollabMessageReceipt
from app.models.meeting import MeetingRoomMember
from app.models.meeting import MemoryTransferLog
from app.models.supervision import SupervisionRecord
from app.models.task import InspectionTask
from app.models.user import User
from app.services.supervision_option_service import SupervisionOptionService
from app.services.collab_service import CollabService
from app.services.collab_work_item_page_service import CollabWorkItemPageService
from app.services.collab_reference_service import CollabReferenceService


@pytest.mark.asyncio
async def test_task_filter_runs_before_limit_and_options_recheck_selected(supervision_domain):
    db,service,ids=supervision_domain
    now=datetime(2025,1,1)
    values=[]
    for i in range(243):
        values.append({'id':str(uuid4()),'org_id':ids['org'],'kind':'inspection-sessions','code':f'BATCH-{i:04}','name':'隔离检测会话',
            'status':'collecting','version':1,'created_by':ids['actors']['expert'],'data':{'task_id':ids['task']},'created_at':now,'updated_at':now})
    values.append({**values[0],'id':str(uuid4()),'code':'OTHER-TASK','data':{'task_id':str(uuid4())}})
    await db.execute(insert(SupervisionRecord),values)
    all_ids=[]
    for page in range(1,14):
        result=await service('expert').list('inspection-sessions',page=page,size=20,task_id=ids['task'])
        assert result['total']==243
        all_ids += [r['id'] for r in result['items']]
    assert len(all_ids)==len(set(all_ids))==243 and values[-1]['id'] not in all_ids
    assert (await service('expert').list('inspection-sessions',keyword='BATCH-0000',task_id=ids['task']))['items'][0]['id']==values[0]['id']
    samples=[{**row,'kind':'samples','code':row['code'].replace('BATCH','SAMPLE')} for row in values]
    for row in samples:row['id']=str(uuid4())
    await db.execute(insert(SupervisionRecord),samples)
    svc=SupervisionOptionService(service('expert'))
    result=await svc.page('samples',page=13,task_id=ids['task'],selected_ids=[samples[0]['id']])
    assert result['total']==243 and len(result['items'])==3 and result['selected'][0]['value']==samples[0]['id']
    (await db.get(SupervisionRecord,samples[0]['id'])).status='archived';await db.flush()
    result=await svc.page('samples',task_id=ids['task'],selected_ids=[samples[0]['id'],samples[-1]['id']])
    assert not result['selected'] and len(result['unavailable_selected_ids'])==2
    with pytest.raises(ForbiddenError):await SupervisionOptionService(service('algorithm_engineer')).page('samples')


@pytest.mark.asyncio
async def test_generic_options_active_approved_org_and_user_task_scope(supervision_domain):
    db,service,ids=supervision_domain;now=datetime(2025,1,1)
    rows=[]
    for kind in ('devices','sampling-plans'):
        for org in (ids['org'],ids['other_org']):
            for status in ('active','approved','inactive','archived'):
                rows.append({'id':str(uuid4()),'org_id':org,'kind':kind,'code':str(uuid4()),'name':status,'status':status,'version':1,
                    'created_by':ids['actors']['expert'],'data':{},'created_at':now,'updated_at':now})
    await db.execute(insert(SupervisionRecord),rows)
    svc=SupervisionOptionService(service('expert'))
    result=await svc.page('plans',selected_ids=[r['id'] for r in rows[8:]])
    assert result['total']==1 and result['items'][0]['label'].endswith('approved')
    assert len(result['selected'])==1
    assert (await svc.page('devices'))['total']==2
    assert not (await svc.page('devices',keyword='%'))['items']
    task=await db.get(InspectionTask,ids['task']);task.created_by=ids['actors']['expert'];await db.flush()
    assert (await SupervisionOptionService(service('user')).page('tasks'))['total']==0
    with pytest.raises(NotFoundError):await SupervisionOptionService(service('user')).page('samples',task_id=task.id)


async def memory_tables(db):
    metadata=MetaData()
    for name in ('memory_transfer_logs','memory_items'):
        table=Base.metadata.tables[name].to_metadata(metadata)
        for column in table.c:
            if column.server_default is not None:
                column.server_default=DefaultClause(text('CURRENT_TIMESTAMP')) if isinstance(column.type,DateTime) else None
    async with db.bind.begin() as connection:await connection.run_sync(metadata.create_all)


@pytest.mark.asyncio
async def test_mixed_work_pages_find_late_request_and_reject_revoked_context(collaboration):
    db,risk,_,case,_,assessment,svc,payload=collaboration
    link=await svc().create(case['id'],payload);await memory_tables(db)
    original=await db.get(CollabMessage,link['message_id']);org=risk('expert').org_id;peer=risk('expert2').actor;actor=risk('expert').actor
    messages=[];receipts=[];now=datetime(2025,1,1)
    for i in range(243):
        mid=str(uuid4());meta=copy.deepcopy(original.metadata_json);meta['action_request']['title']=f'隔离请求-{i:04}'
        messages.append({'id':mid,'org_id':org,'thread_id':link['thread_id'],'sender_type':'user','sender_id':actor,'message_type':'action_request','content':'隔离分页资料',
            'metadata_json':meta,'created_at':now,'updated_at':now})
        receipts.append({'id':str(uuid4()),'org_id':org,'thread_id':link['thread_id'],'message_id':mid,'recipient_type':'user','recipient_id':peer,
            'action_status':'pending','created_at':now,'updated_at':now})
    await db.execute(insert(CollabMessage),messages);await db.execute(insert(CollabMessageReceipt),receipts)
    transfers=[{'id':str(uuid4()),'org_id':org,'memory_id':f'isolated-memory-{i}','from_scope_type':'user','from_scope_id':actor,
        'to_scope_type':'user','to_scope_id':peer,'status':'pending_approval','requested_by':actor,'created_at':now,'updated_at':now} for i in range(2)]
    await db.execute(insert(MemoryTransferLog),transfers)
    pager=CollabWorkItemPageService(CollabService(db,org,peer,role='expert'))
    ids=[];cursor=None
    for _ in range(40):
        page=await pager.page(view='pending',size=19,cursor=cursor)
        ids.extend(i.id for i in page['items']);cursor=page['next_cursor']
        if not cursor:break
    assert len(ids)==len(set(ids))==246
    assert all('memory_share:'+row['id'] in ids for row in transfers)
    target='action_request:'+messages[0]['id']
    assert (await pager.get(target)).title=='隔离请求-0000'
    assert (await pager.page(keyword='隔离请求-0000'))['items'][0].id==target
    token=(await pager.page(size=1))['next_cursor']
    with pytest.raises(ValidationError):await pager.page(size=2,cursor=token)
    with pytest.raises(ValidationError):await pager.page(size=1,cursor=token,keyword='changed')
    author_pager=CollabWorkItemPageService(CollabService(db,org,actor,role='expert'))
    with pytest.raises(ValidationError):await author_pager.page(size=1,cursor=token)
    membership=await db.scalar(select(MeetingRoomMember).where(MeetingRoomMember.room_id==link['room_id'],MeetingRoomMember.user_id==peer))
    membership.deleted_at=datetime.utcnow();await db.flush()
    assert not (await pager.page(keyword='隔离请求-0000'))['items']
    with pytest.raises(ForbiddenError):await pager.get(target)
    membership.deleted_at=None
    from app.models.meeting import MeetingRoom
    (await db.get(MeetingRoom,link['room_id'])).memory_policy={};await db.flush()
    assert not (await pager.page(keyword='隔离请求-0000'))['items']
    with pytest.raises(ForbiddenError):await pager.get(target)
    with pytest.raises(ForbiddenError):await svc().create(case['id'],payload)
    assert not await svc().list_for_case(case['id'])


@pytest.mark.asyncio
async def test_member_selector_beyond_200_and_inactive_selection(collaboration):
    db,risk,_,_,_,_,_,_=collaboration;org=risk('expert').org_id
    rows=[{'id':str(uuid4()),'org_id':org,'username':f'expert-{i:04}','email':f'{i}@fixture.invalid','role':'expert','is_active':True} for i in range(243)]
    await db.execute(insert(User),rows)
    svc=CollabReferenceService(db,risk('expert').current)
    result=await svc.page('user',page=13,selected_ids=[rows[0]['id']],expert_only=True)
    assert result['items'] and result['selected'][0]['value']==rows[0]['id']
    assert (await svc.page('user',keyword='expert-0000',expert_only=True))['items'][0]['value']==rows[0]['id']
    (await db.get(User,rows[0]['id'])).is_active=False;await db.flush()
    assert (await svc.page('user',selected_ids=[rows[0]['id']]))['unavailable_selected_ids']==[rows[0]['id']]


@pytest.mark.asyncio
async def test_sampling_scan_and_case_collaboration_pages(sampling):
    db,risk,_,case,_,_,link,_,suggestions,create=sampling
    original=await suggestions().create(case['id'],create)
    row=await db.get(SupervisionRecord,original['id']);rows=[]
    for i in range(205):
        rows.append({'id':str(uuid4()),'org_id':row.org_id,'kind':row.kind,'code':str(uuid4()),'name':f'隔离建议-{i:04}',
            'status':row.status,'version':1,'created_by':row.created_by,'data':copy.deepcopy(row.data),'created_at':datetime(2025,1,1),'updated_at':datetime(2025,1,1)})
    await db.execute(insert(SupervisionRecord),rows)
    svc=suggestions();cursor=None;seen=[]
    for _ in range(30):
        page=await svc.page(case['id'],size=20,cursor=cursor)
        seen.extend(r['id'] for r in page['items']);cursor=page['next_cursor']
        if not cursor:break
    assert len(seen)==len(set(seen))==206
    assert (await svc.page(case['id'],keyword='隔离建议-0000'))['items'][0]['id']==rows[0]['id']
    collab=svc.collab
    assert (await collab.page_for_case(case['id'],assessment_id=str(create.assessment_id)))['items'][0]['id']==link['id']
    assert not (await collab.page_for_case(case['id'],assessment_id=str(uuid4())))['items']
    membership=await db.scalar(select(MeetingRoomMember).where(MeetingRoomMember.room_id==link['room_id'],MeetingRoomMember.user_id==risk('expert').actor))
    membership.deleted_at=datetime.utcnow();await db.flush()
    assert not (await svc.page(case['id']))['items']


@pytest.mark.asyncio
async def test_native_context_pins_old_session_and_sample_through_create_and_review(native_data):
    from app.services.inspection_execution_context_service import InspectionExecutionContextService
    from app.services.inspection_execution_service import InspectionExecutionService
    from app.services.inspection_reference_service import InspectionReferenceService
    db,task=native_data[:2]
    body,session,sample,_,_,measurement=await measured_payload(native_data)
    session.created_at=sample.created_at=datetime(2020,1,1);await db.flush()
    rows=[]
    for kind,count in [('inspection-sessions',221),('samples',521)]:
        for i in range(count):
            rows.append({'id':str(uuid4()),'org_id':task.org_id,'kind':kind,'code':f'NATIVE-{kind}-{i:04}','name':'隔离后续资料',
                'status':'collecting' if kind=='inspection-sessions' else 'active','version':1,'created_by':task.created_by,
                'data':{'task_id':task.id,'sampled_at':'2025-01-01T00:00:00'},'created_at':datetime(2025,1,1),'updated_at':datetime(2025,1,1)})
    await db.execute(insert(SupervisionRecord),rows)
    svc=InspectionExecutionContextService(db,native_current(),native_data[5])
    initial=await svc.context(task)
    assert session.id not in {s['id'] for s in initial['sessions']} and sample.id not in {s['id'] for s in initial['samples']}
    context=await svc.context(task,session_id=session.id,sample_ids=[sample.id])
    assert session.id in {s['id'] for s in context['sessions']} and sample.id in {s['id'] for s in context['samples']}
    assert context['measurements'][0]['id']==measurement.id and context['truncated']['sessions'] and context['truncated']['samples']
    reference=await InspectionReferenceService(db,native_current()).page(task,'sessions',page=12,selected_ids=[session.id])
    assert reference['selected'][0]['value']==session.id and reference['items']
    body['context_hash']=context['context_hash']
    result=await InspectionExecutionService(db,native_current(),native_data[5]).create(body)
    assert result['snapshot']['task_context']['selected_samples'][0]['id']==sample.id
    assert 'context_hash' not in str(result['source_validation'].get('blockers',[]))
    from app.models.inspection_execution import InspectionExecutionRun
    run=await db.get(InspectionExecutionRun,result['id'])
    reviewed=await InspectionExecutionService(db,native_current(EXPERT,'expert'),native_data[5]).review(run.id,native_review(run))
    assert reviewed['status']=='accepted'
    copies=[{'id':str(uuid4()),'org_id':run.org_id,'task_id':run.task_id,'session_id':run.session_id,'request_key':str(uuid4()),'payload_hash':'isolated-page',
        'snapshot':copy.deepcopy(run.snapshot),'evaluation':copy.deepcopy(run.evaluation),'status':'draft','row_version':1,'created_by':run.created_by,
        'created_at':datetime(2010,1,1)+timedelta(seconds=i)} for i in range(231)]
    await db.execute(insert(InspectionExecutionRun),copies)
    execution=InspectionExecutionService(db,native_current(),native_data[5])
    page=await execution.page(task.id,page=12,size=20)
    assert page['total']==232 and len(page['items'])==12
    assert (await execution.page(task.id,keyword=copies[0]['id']))['items'][0]['id']==copies[0]['id']


@pytest.mark.asyncio
async def test_native_reference_http_contract_and_task_boundary(native_data):
    from fastapi import FastAPI
    from httpx import AsyncClient,ASGITransport
    from app.api.v1.deps import get_db,get_current_user
    from app.api.v1.inspection_execution import router
    db,task=native_data[:2]
    app=FastAPI();app.include_router(router)
    async def session():yield db
    app.dependency_overrides[get_db]=session;app.dependency_overrides[get_current_user]=lambda:native_current()
    prefix=f'/inspection-execution/tasks/{task.id}'
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        response=await client.get(prefix+'/reference-pages/samples')
        assert response.status_code==200 and 'selected' in response.json()['data']
        assert (await client.get(prefix+'/reference-pages/sessions?size=51')).status_code==422
        assert (await client.get(prefix+'/reference-pages/policies?selected_ids=bad')).status_code==422
        assert (await client.get('/inspection-execution/run-pages',params={'task_id':task.id})).json()['data']['total']==0
        assert (await client.get('/inspection-execution/run-pages',params={'task_id':task.id,'size':51})).status_code==422
        response=await client.post(prefix+'/context-selection',json={'session_id':str(uuid4()),'sample_ids':[],'policy_id':None})
        assert response.status_code==200 and not response.json()['data']['sessions']


@pytest.mark.asyncio
async def test_selected_policy_outside_first_200_uses_same_context_hash(native_data):
    from test_inspection_execution_context import publish_policy
    from app.models.inspection_execution import InspectionPolicyPublication
    from app.services.inspection_execution_context_service import InspectionExecutionContextService
    from app.services.inspection_execution_service import InspectionExecutionService
    db,task=native_data[:2]
    body,*_=await measured_payload(native_data)
    published,_,_=await publish_policy(native_data,required_image_count=0,required_views=[])
    original=await db.get(InspectionPolicyPublication,published['id']);original.created_at=datetime(2020,1,1);await db.flush()
    rows=[{'id':str(uuid4()),'org_id':original.org_id,'spec_id':original.spec_id,'request_key':str(uuid4()),'payload_hash':'fixture',
        'snapshot':copy.deepcopy(original.snapshot),'status':'published','published_by':original.published_by,'created_at':datetime(2025,1,1)} for _ in range(205)]
    await db.execute(insert(InspectionPolicyPublication),rows)
    svc=InspectionExecutionContextService(db,native_current(),native_data[5])
    assert original.id not in {p['id'] for p in (await svc.context(task))['policies']}
    context=await svc.context(task,session_id=body['session_id'],sample_ids=body['sample_ids'],policy_id=original.id)
    assert original.id in {p['id'] for p in context['policies']}
    body.update(policy_id=original.id,context_hash=context['context_hash'])
    result=await InspectionExecutionService(db,native_current(),native_data[5]).create(body)
    assert result['snapshot']['policy']['publication_id']==original.id
