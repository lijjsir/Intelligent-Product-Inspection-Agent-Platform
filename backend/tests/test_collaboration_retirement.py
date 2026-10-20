"""Retired entry points, direct reviewed-assessment suggestions and legacy safety."""
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import func,select
from test_quality_risk_v4 import domain  # noqa: F401
from test_risk_sampling_workflow import flow  # noqa: F401
from test_formal_risk_completion import formal  # noqa: F401
from test_demo_sampling import collaboration,sampling  # noqa: F401
from app.core.exceptions import ConflictError,ForbiddenError,ValidationError
from app.models.collab import CollabThread
from app.models.quality_risk import QualityRiskAssessment,QualitySourceRecord
from app.models.supervision import SupervisionRecord
from app.schemas.demo_sampling import DemoSamplingCreate,DemoSamplingSave,DemoSamplingConfirm,DemoSamplingContent
from app.schemas.risk_completion import RiskReportCreate
from app.schemas.collab import CollabActionRequestCreateRequest,CollabMessageCreateRequest,CollabMessageActionRequest
from app.schemas.meeting import MeetingMemoryShareCreateRequest
from app.services.demo_sampling_service import DemoSamplingService,ASSESSMENT_SCHEMA
from app.services.risk_report_service import RiskReportService
from app.services.risk_collaboration_service import RiskCollaborationService
from app.services.meeting_service import MeetingService
from app.api.v1 import collab as collab_api


@pytest.mark.asyncio
async def test_reviewed_assessment_to_suggestion_and_report_without_any_collaboration(formal,monkeypatch):
    db,risk,_,source,case,assessment=formal
    blocked=AsyncMock(side_effect=AssertionError('new flow must not call collaboration'))
    monkeypatch.setattr(RiskCollaborationService,'get',blocked)
    monkeypatch.setattr(RiskCollaborationService,'guard',blocked)
    svc=DemoSamplingService(db,risk('expert').current)
    before=await db.scalar(select(func.count()).select_from(CollabThread))
    candidates=(await svc.candidates(case['id']))['items'];assert len(candidates)==1
    candidate=candidates[0];assert candidate['snapshot']['schema']==ASSESSMENT_SCHEMA and candidate['snapshot']['collaboration_id'] is None
    payload=DemoSamplingCreate(assessment_id=assessment['id'],expected_context_hash=candidate['context_hash'])
    created=await svc.create(case['id'],payload)
    assert (await svc.create(case['id'],payload))['id']==created['id']
    saved=await svc.mutate(created['id'],DemoSamplingSave(expected_revision=1,content=DemoSamplingContent(rationale='隔离测试依据',focus='原事项对象',limitations='实际执行仍需核实')))
    confirmed=await svc.mutate(created['id'],DemoSamplingConfirm(expected_revision=saved['revision']),confirm=True)
    assert confirmed['is_current'] and confirmed['status']=='confirmed'
    workspace=await risk('expert').risk_workspace(case['id'])
    report=await RiskReportService(db,risk('expert').current).create(case['id'],RiskReportCreate(assessment_id=assessment['id'],expected_basis_hash=workspace['workflow_context']['basis_hash']))
    assert report['snapshot']['sampling_protocol']=='assessment-v2'
    assert report['snapshot']['sampling'][0]['id']==created['id']
    assert not any(r['kind']=='collab-context' for r in report['snapshot']['source_refs'])
    assert (await RiskReportService(db,risk('expert').current).page(case['id']))['items'][0]['id']==report['id']
    assert await db.scalar(select(func.count()).select_from(CollabThread))==before
    assert not blocked.called
    peer=DemoSamplingService(db,risk('expert2').current)
    assert (await peer.get(created['id']))['id']==created['id']
    with pytest.raises(ForbiddenError):await peer.mutate(created['id'],DemoSamplingSave(expected_revision=3,content=DemoSamplingContent()))
    row=await db.get(QualitySourceRecord,source['id']);row.authorization_scope='private';row.created_by=risk('expert2').actor;await db.flush()
    with pytest.raises(ForbiddenError):await svc.get(created['id'])
    assert not (await RiskReportService(db,risk('expert').current).page(case['id']))['items']


@pytest.mark.asyncio
@pytest.mark.parametrize('problem',['unreviewed','self_review','changed_source'])
async def test_direct_flow_preserves_independent_review_and_current_evidence_gates(formal,problem):
    db,risk,_,source,case,assessment=formal
    svc=DemoSamplingService(db,risk('expert').current)
    if problem=='changed_source':
        row=await db.get(QualitySourceRecord,source['id']);row.content={**row.content,'changed':'new evidence'}
    else:
        row=await db.get(QualityRiskAssessment,assessment['id'])
        if problem=='unreviewed':row.status='awaiting_review';row.reviewed_by=None
        else:row.reviewed_by=row.submitted_by
    await db.flush()
    with pytest.raises((ConflictError,ValidationError)):await svc.context(case['id'])


@pytest.mark.asyncio
async def test_legacy_snapshot_keeps_old_opinions_and_current_access_rules(sampling):
    db,risk,_,case,_,_,link,public,services,payload=sampling
    svc=services();old=await svc.create(case['id'],payload);frozen=copy.deepcopy(old['snapshot'])
    assert old['snapshot']['collaboration_id']==link['id'] and any(o['id']==public.id for o in old['snapshot']['opinions'])
    assert (await svc.get(old['id']))['snapshot']==frozen
    direct=(await svc.candidates(case['id']))['items'][0]
    created=await svc.create(case['id'],DemoSamplingCreate(assessment_id=direct['snapshot']['assessment_id'],expected_context_hash=direct['context_hash']))
    assert created['snapshot']['collaboration_id'] is None and created['id']!=old['id']
    assert (await svc.get(old['id']))['snapshot']==frozen


@pytest.mark.asyncio
async def test_personal_share_is_rejected_before_confirming_or_mutating_source_memory():
    svc=object.__new__(MeetingService);svc._org_id=str(uuid4());svc._user_id=str(uuid4());svc._role='expert'
    svc._repo=SimpleNamespace(get_memory_transfer_log_by_idempotency_key=AsyncMock(return_value=None),get_memory_item=AsyncMock())
    payload=MeetingMemoryShareCreateRequest(target_scope_type='user',target_scope_id=str(uuid4()),idempotency_key=str(uuid4()))
    with pytest.raises(ValidationError,match='个人记忆分享已停用'):await svc.create_memory_share_request('fixture',payload)
    assert not svc._repo.get_memory_item.called


@pytest.mark.asyncio
async def test_retired_public_request_endpoints_reject_creation_and_updates(formal):
    db,risk,*_=formal;current=risk('expert').current
    create=CollabActionRequestCreateRequest(target_type='user',target_id=risk('expert2').actor,title='已停用请求',description='不应创建任何工作项')
    before=await db.scalar(select(func.count()).select_from(CollabThread))
    with pytest.raises(ValidationError,match='已停用'):await collab_api.create_action_request(create,current=current,db=db)
    with pytest.raises(ValidationError,match='不再推进'):await collab_api.update_message_action(str(uuid4()),CollabMessageActionRequest(action_status='done'),current=current,db=db)
    with pytest.raises(ValidationError,match='只读'):await collab_api.send_message(str(uuid4()),CollabMessageCreateRequest(content='旧评论',reply_to_message_id=str(uuid4())),current=current,db=db)
    assert await db.scalar(select(func.count()).select_from(CollabThread))==before
