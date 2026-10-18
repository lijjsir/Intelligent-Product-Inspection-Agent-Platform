"""Large isolated datasets exercise pagination and live ACLs, not business truth."""
import copy
import json
from datetime import datetime, timedelta
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import event, insert, select

from test_quality_risk_v4 import domain  # noqa: F401
from test_risk_completion import completion  # noqa: F401
from test_risk_collaboration import collaboration  # noqa: F401
from test_demo_sampling import sampling  # noqa: F401
from test_risk_sampling_workflow import flow  # noqa: F401
from test_formal_risk_completion import formal  # noqa: F401
from test_risk_execution_return import returning  # noqa: F401
from app.core.exceptions import ValidationError, ForbiddenError
from app.models.meeting import MeetingRoomMember
from app.models.quality_risk import QualityAttachment, QualityRiskCase, QualitySourceRecord
from app.models.supervision import SupervisionRecord
from app.models.task import InspectionTask
from app.schemas.quality_risk import QualityEventCreate, RiskAnalyzeRequest, RiskReviewRequest
from app.schemas.risk_completion import RiskReportCreate
from app.services.quality_risk_service import stable_hash
from app.services.risk_report_service import RiskReportService


async def copies(db, report, org, actor, count, *, readers=None, year=2025):
    values, ids = [], []
    for index in range(count):
        snapshot = copy.deepcopy(report['snapshot'])
        snapshot['boundary'] += f'【隔离分页样本 {year}-{index:04}】'
        token, rid = stable_hash(snapshot), str(uuid4())
        ids.append(rid)
        values.append({'id':rid, 'org_id':org, 'kind':'risk-assessment-reports', 'code':token,
            'name':f'【演示分页样本】{index:04}', 'status':'demo_frozen', 'version':1, 'created_by':actor,
            'created_at':datetime(year, 1, 1), 'updated_at':datetime(year, 1, 1),
            'data':{'snapshot':snapshot, 'snapshot_hash':token, 'frozen_at':report['frozen_at'],
                'reader_ids':readers or [snapshot['review']['author_id'], snapshot['review']['reviewer_id']]}})
    await db.execute(insert(SupervisionRecord), values)
    return ids


@pytest.mark.asyncio
async def test_report_cursor_enumerates_beyond_200_without_full_detail_or_file_reads(completion, monkeypatch):
    db, risk, _, case, _, _, _, _, _, reports, _, payload = completion
    report = await reports().create(case['id'], payload)
    expected = {report['id'], *await copies(db, report, risk('expert').org_id, risk('expert').actor, 503)}
    query_count = 0
    def count(*args):
        nonlocal query_count
        query_count += 1
    event.listen(db.bind.sync_engine, 'before_cursor_execute', count)
    svc = reports()
    monkeypatch.setattr(svc, 'get', AsyncMock(side_effect=AssertionError('a list must not validate full report evidence')))
    seen, cursor = [], None
    first_queries = None
    try:
        for _ in range(60):
            before = query_count
            result = await svc.page(case['id'], size=17, cursor=cursor)
            first_queries = first_queries or query_count-before
            assert len(result['items']) <= 17
            assert all(r['effective_status'] == 'snapshot_unchecked' and r['validation_checked'] is False for r in result['items'])
            seen.extend(r['id'] for r in result['items'])
            cursor = result['next_cursor']
            if not cursor: break
        assert set(seen) == expected and len(seen) == len(expected)
        assert first_queries < 25
    finally: event.remove(db.bind.sync_engine, 'before_cursor_execute', count)


@pytest.mark.asyncio
async def test_report_insert_during_paging_does_not_duplicate_old_rows(completion):
    db, risk, _, case, _, _, _, _, _, reports, _, payload = completion
    report = await reports().create(case['id'], payload)
    original = {report['id'], *await copies(db, report, risk('expert').org_id, risk('expert').actor, 25)}
    first = await reports().page(case['id'], size=10)
    inserted = (await copies(db, report, risk('expert').org_id, risk('expert').actor, 1, year=2030))[0]
    ids, cursor = [r['id'] for r in first['items']], first['next_cursor']
    while cursor:
        page = await reports().page(case['id'], size=10, cursor=cursor)
        ids.extend(r['id'] for r in page['items']); cursor = page['next_cursor']
    assert set(ids) == original and len(ids) == len(original) and inserted not in ids
    assert (await reports().page(case['id'], size=10))['items'][0]['id'] == inserted


@pytest.mark.asyncio
async def test_cursor_is_filter_actor_and_size_bound_and_rejects_tampering(completion):
    db, risk, _, case, _, _, _, _, _, reports, _, payload = completion
    report = await reports().create(case['id'], payload)
    await copies(db, report, risk('expert').org_id, risk('expert').actor, 4)
    first = await reports().page(case['id'], size=1)
    token = first['next_cursor']
    for svc, case_id, size, keyword, cursor in [
        (reports(),str(uuid4()),1,'',token), (reports('expert2'),case['id'],1,'',token),
        (reports(),case['id'],2,'',token), (reports(),case['id'],1,'changed',token),
        (reports(),case['id'],1,'',token[:-4]+'ABCD')]:
        with pytest.raises(ValidationError): await svc.page(case_id, size=size, keyword=keyword, cursor=cursor)


@pytest.mark.asyncio
async def test_hidden_prefix_is_bounded_and_does_not_hide_later_authorized_report(completion):
    db, risk, _, case, _, _, _, _, _, reports, _, payload = completion
    report = await reports().create(case['id'], payload)
    (await db.get(SupervisionRecord, report['id'])).created_at = datetime(2024, 1, 1)
    ids = await copies(db, report, risk('expert').org_id, risk('expert').actor, 225)
    original = await db.get(QualitySourceRecord,report['snapshot']['records'][0]['id'])
    hidden_source = QualitySourceRecord(org_id=original.org_id, source_id=original.source_id,
        record_type='inspection_report', content={'text':'隔离私有来源'}, content_hash='fixture-private',
        attachment_ids=[], data_nature='synthetic', authorization_scope='private', created_by=risk('expert').actor)
    db.add(hidden_source); await db.flush()
    for row in await db.scalars(select(SupervisionRecord).where(SupervisionRecord.id.in_(ids))):
        data=copy.deepcopy(row.data)
        data['snapshot']['records'][0]['id']=hidden_source.id
        data['snapshot_hash']=stable_hash(data['snapshot'])
        row.data=data
    await db.flush()
    seen, cursor, pages = [], None, 0
    while True:
        result = await reports('expert2').page(case['id'], size=1, cursor=cursor)
        pages += 1; seen += result['items']; cursor = result['next_cursor']
        assert pages < 20
        if not cursor: break
    assert [r['id'] for r in seen] == [report['id']] and pages > 1


@pytest.mark.asyncio
async def test_revocation_and_removed_assessment_hide_report_summaries(completion):
    db, risk, _, case, source, assessment, _, _, _, reports, _, payload = completion
    report = await reports().create(case['id'], payload)
    raw = await db.get(QualitySourceRecord, source['id'])
    raw.authorization_scope = 'private'; await db.flush()
    assert not (await reports('expert2').page(case['id']))['items']
    assert (await reports().page(case['id']))['items'][0]['id'] == report['id']
    from app.models.quality_risk import QualityRiskAssessment
    (await db.get(QualityRiskAssessment, assessment['id'])).deleted_at = datetime.utcnow()
    await db.flush()
    assert not (await reports().page(case['id']))['items']


@pytest.mark.asyncio
async def test_attachment_shared_elsewhere_matches_detail_access_rule(completion):
    db, risk, _, case, source, _, _, _, _, reports, _, payload = completion
    report = await reports().create(case['id'], payload)
    attachment = QualityAttachment(org_id=risk('expert').org_id, uploaded_by=risk('expert2').actor, file_name='isolated.pdf',
        size_bytes=10, sha256='b'*64, mime_type='application/pdf', bucket='fixture', object_key='fixture')
    db.add(attachment); await db.flush()
    row = await db.get(SupervisionRecord, report['id'])
    data = copy.deepcopy(row.data)
    data['snapshot']['attachments'] = [{'id':attachment.id, 'name':attachment.file_name, 'sha256':attachment.sha256}]
    data['snapshot_hash'] = stable_hash(data['snapshot']); row.data = data
    original = await db.get(QualitySourceRecord, source['id'])
    shared = QualitySourceRecord(org_id=original.org_id, source_id=original.source_id, record_type='inspection_report',
        content={'text':'隔离附件授权测试'}, content_hash='fixture', attachment_ids=[attachment.id], data_nature='synthetic',
        authorization_scope='organization', created_by=risk('expert2').actor)
    db.add(shared); await db.flush()
    assert (await reports().page(case['id']))['items'][0]['id'] == report['id']
    shared.authorization_scope = 'private'; await db.flush()
    assert not (await reports().page(case['id']))['items']


@pytest.mark.asyncio
async def test_lab_option_pages_find_late_records_and_recheck_selected_acl(completion):
    db, risk, _, case, source, _, product, category, lab, _, _, _ = completion
    actor, org = risk('expert').actor, risk('expert').org_id
    tasks, records = [], []
    original = await db.get(QualitySourceRecord, source['id'])
    for i in range(243):
        tasks.append({'id':str(uuid4()), 'org_id':org, 'created_by':actor, 'product_id':product, 'quality_product_id':product,
            'spec_code':f'OPTION-{i:04}', 'image_urls':[], 'status':'pending', 'meta_data':{'execution_mode':'demo'},
            'created_at':datetime(2025,1,1)+timedelta(seconds=i), 'updated_at':datetime(2025,1,1)})
        records.append({'id':str(uuid4()), 'org_id':org, 'source_id':original.source_id, 'record_type':'inspection_report',
            'content':{'title':f'隔离资料-{i:04}'}, 'content_hash':f'fixture-{i}', 'attachment_ids':[], 'data_nature':'synthetic',
            'authorization_scope':'organization', 'created_by':actor, 'product_ref':{'product_id':product},
            'created_at':datetime(2025,1,1)+timedelta(seconds=i), 'updated_at':datetime(2025,1,1)})
    await db.execute(insert(InspectionTask), tasks); await db.execute(insert(QualitySourceRecord), records)
    for kind in ('tasks','records'):
        all_ids = []
        for page in range(1,14):
            result = await lab().option_page(case['id'],kind,page=page,size=20)
            assert len(result['items']) <= 20
            all_ids += [r['id'] for r in result['items']]
        assert len(set(all_ids)) == 243 and len(all_ids) == 243
    target = records[0]['id']
    result = await lab().option_page(case['id'],'records',keyword='0000',selected_ids=[target])
    assert [r['id'] for r in result['items']] == [target] and result['selected'][0]['id'] == target
    assert (await lab().option_page(case['id'],'tasks',keyword=tasks[0]['id']))['items'][0]['id'] == tasks[0]['id']
    private = await db.get(QualitySourceRecord,target)
    private.authorization_scope='private'; private.created_by=risk('expert2').actor
    await db.flush()
    result = await lab().option_page(case['id'],'records',selected_ids=[target])
    assert not result['selected'] and target in result['unavailable_selected_ids']
    legacy = await lab().options(case['id'])
    assert len(legacy['tasks']) == len(legacy['records']) == 100 and all(legacy['truncated'].values())


@pytest.mark.asyncio
async def test_case_picker_can_find_case_code_after_first_200(completion):
    db, risk, _, _, _, _, _, _, _, _, _, _ = completion
    actor, org = risk('expert').actor, risk('expert').org_id
    values = [{'id':str(uuid4()), 'org_id':org, 'code':f'CASE-PAGE-{i:04}', 'title':f'隔离事项{i:04}',
        'scope_type':'product','scope':{'execution_mode':'demo'},'status':'collecting','evidence_ids':[],
        'source_record_ids':[],'created_by':actor,'created_at':datetime(2025,1,1),'updated_at':datetime(2025,1,1)} for i in range(243)]
    await db.execute(insert(QualityRiskCase),values)
    page = await risk('expert').list_risk_cases(page=13,size=20,status=None,keyword='CASE-PAGE')
    assert page['total'] == 243 and len(page['items']) == 3
    result = await risk('expert').list_risk_cases(page=1,size=20,status=None,keyword=values[0]['code'])
    assert [r['id'] for r in result['items']] == [values[0]['id']]


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['membership','binding'])
async def test_report_page_checks_current_collaboration_access(sampling, change):
    db, risk, wf, case, _, _, link, _, suggestions, create = sampling
    await suggestions().create(case['id'],create)
    latest = await wf().risk.get_assessment(create.assessment_id)
    svc = RiskReportService(db,risk('expert').current)
    report = await svc.create(case['id'],RiskReportCreate(assessment_id=latest['id'],expected_basis_hash=latest['demo_validation']['basis_hash']))
    assert (await svc.page(case['id']))['items'][0]['id'] == report['id']
    if change == 'membership':
        member = await db.scalar(select(MeetingRoomMember).where(MeetingRoomMember.room_id == link['room_id'], MeetingRoomMember.user_id == risk('expert').actor))
        member.deleted_at = datetime.utcnow()
    else:
        from app.models.meeting import MeetingRoom
        room = await db.get(MeetingRoom,link['room_id']); room.memory_policy={}
    await db.flush()
    assert not (await svc.page(case['id']))['items']
    with pytest.raises(ForbiddenError): await svc.get(report['id'])


@pytest.mark.asyncio
async def test_native_result_sharing_is_rechecked_for_report_summary(returning):
    db, risk, _, case, _, _, source, _, lab, link, request, _ = returning
    await lab.return_execution(link['id'],request)
    draft = await risk('expert').analyze_risk(case['id'],RiskAnalyzeRequest())
    await risk('expert2').review_risk(case['id'],RiskReviewRequest(decision='accept',comment='隔离分页原件核验',risk_level='high'))
    workspace = await risk('expert').risk_workspace(case['id'])
    svc = RiskReportService(db,risk('expert').current)
    report = await svc.create(case['id'],RiskReportCreate(assessment_id=draft['id'],expected_basis_hash=workspace['workflow_context']['basis_hash']))
    assert (await svc.page(case['id']))['items'][0]['id'] == report['id']
    (await db.get(QualitySourceRecord,source['id'])).authorization_scope = 'private'
    await db.flush()
    assert not (await svc.page(case['id']))['items']


@pytest.mark.asyncio
async def test_new_page_api_contract_and_input_limits(completion):
    from fastapi import FastAPI
    from httpx import AsyncClient, ASGITransport
    from app.api.v1.quality_risk import router, risk_lab_service, risk_report_service
    _, _, _, case, source, _, _, _, lab, reports, _, payload = completion
    await reports().create(case['id'],payload)
    app=FastAPI(); app.include_router(router)
    app.dependency_overrides[risk_lab_service]=lambda:lab()
    app.dependency_overrides[risk_report_service]=lambda:reports()
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        response=await client.get('/risk-report-pages',params={'case_id':case['id']})
        assert response.status_code == 200 and 'snapshot' not in response.json()['data']['items'][0]
        assert (await client.get('/risk-report-pages?size=51')).status_code == 422
        prefix=f"/risk-cases/{case['id']}/laboratory-"
        assert (await client.get(prefix+'unknown-options')).status_code == 422
        assert (await client.get(prefix+'tasks-options?selected_ids=not-a-uuid')).status_code == 422
        response=await client.get(prefix+'records-options',params={'selected_ids':source['id']})
        assert response.status_code == 200 and response.json()['data']['unavailable_selected_ids'] == [source['id']]
