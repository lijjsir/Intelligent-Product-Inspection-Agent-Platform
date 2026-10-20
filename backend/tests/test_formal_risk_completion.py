"""Formal downstream integration uses isolated test evidence, never demo bypasses."""
from datetime import datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import DateTime, DefaultClause, MetaData, select, text

from test_quality_risk_v4 import domain  # noqa: F401
from test_risk_sampling_workflow import flow  # noqa: F401
from app.core.exceptions import ConflictError, ForbiddenError, ValidationError, NotFoundError
from app.models.base import Base
from app.models.quality_risk import QualityRiskAssessment, QualitySourceRecord
from app.models.supervision import SupervisionRecord
from app.schemas.collab import CollabMessageActionRequest
from app.schemas.demo_sampling import DemoSamplingCreate, DemoSamplingSave, DemoSamplingConfirm, DemoSamplingContent
from app.schemas.risk_collaboration import RiskCollaborationCreate
from app.schemas.risk_completion import LabDecision, RiskReportCreate
from app.services.collab_service import CollabService
from app.services.demo_sampling_service import DemoSamplingService
from app.services.risk_collaboration_service import RiskCollaborationService
from app.services.risk_lab_service import RiskLabService
from app.services.risk_report_service import RiskReportService
from app.services.risk_workflow_context_service import RiskWorkflowContextService


@pytest_asyncio.fixture
async def formal(flow, monkeypatch):
    db, risk, _, record, case, assessment = flow
    metadata = MetaData()
    for name in ('meeting_rooms', 'meeting_room_members', 'meeting_messages', 'collab_threads',
                 'collab_thread_participants', 'collab_messages', 'collab_message_receipts', 'message_attachments', 'file_assets'):
        table = Base.metadata.tables[name].to_metadata(metadata)
        for column in table.c:
            column.server_default = DefaultClause(text('CURRENT_TIMESTAMP')) if isinstance(column.type, DateTime) and column.server_default is not None else None
    async with db.bind.begin() as conn:
        await conn.run_sync(metadata.create_all)
    async def noop(*args, **kwargs): pass
    from app.services import meeting_service, collab_service
    monkeypatch.setattr(meeting_service.meeting_stream_broker, 'publish', noop)
    monkeypatch.setattr(collab_service.collab_stream_broker, 'publish', noop)
    for method in ('_publish_work_item_event', '_publish_message_created', '_publish_receipt_updated'):
        monkeypatch.setattr(CollabService, method, noop)
    # Only explicitly shared evidence may enter collective downstream reports.
    source = await db.get(QualitySourceRecord, record['id'])
    source.authorization_scope = 'organization'
    await db.flush()
    from app.schemas.quality_risk import RiskAnalyzeRequest, RiskReviewRequest
    assessment = await risk('user').analyze_risk(case['id'], RiskAnalyzeRequest())
    await risk('expert').review_risk(case['id'], RiskReviewRequest(decision='accept', comment='隔离共享资料独立复核', risk_level='high'))
    await db.commit()
    return db, risk, flow[2], record, case, assessment


async def collaboration(formal):
    db, risk, _, _, case, assessment = formal
    current = risk('expert').current
    workspace = await risk('expert').risk_workspace(case['id'])
    context = workspace['workflow_context']
    assert context['execution_mode'] == 'business' and context['eligible'], context
    svc = RiskCollaborationService(db, current)
    payload = RiskCollaborationCreate(assessment_id=assessment['id'], expected_basis_hash=context['basis_hash'],
        request_key=uuid4(), coordinator_id=risk('expert2').actor, purpose='隔离正式流程核查证据缺口')
    link = await svc.create(case['id'], payload)
    assert (await svc.create(case['id'], payload))['id'] == link['id']
    peer = CollabService(db, current.org_id, risk('expert2').actor, role='expert')
    await peer.update_action(link['message_id'], CollabMessageActionRequest(action_status='accepted', decision_note='接收核查'))
    await peer.update_action(link['message_id'], CollabMessageActionRequest(action_status='done', decision_note='保留证据不足限制'))
    return context, link


@pytest.mark.asyncio
async def test_formal_review_collaboration_suggestion_skip_and_report(formal):
    db, risk, _, _, case, assessment = formal
    context, link = await collaboration(formal)
    svc = DemoSamplingService(db, risk('expert').current)
    candidate = (await svc.candidates(case['id']))['items'][0]
    suggestion = await svc.create(case['id'], DemoSamplingCreate(assessment_id=assessment['id'],
        expected_context_hash=candidate['context_hash']))
    saved = await svc.mutate(suggestion['id'], DemoSamplingSave(expected_revision=1,
        content=DemoSamplingContent(rationale='隔离证据复核', focus='代表性抽查', limitations='概率未校准')))
    confirmed = await svc.mutate(saved['id'], DemoSamplingConfirm(expected_revision=2), confirm=True)
    assert confirmed['status'] == 'confirmed' and confirmed['snapshot']['execution_mode'] == 'business'
    assert confirmed['snapshot']['source_ref']['assessment_id'] == assessment['id']
    from app.schemas.supervision import RecordCreate, RunRequest, ReviewRequest, ReviewDecision
    supervision = formal[2]()
    plan = await supervision.create('sampling-plans', RecordCreate(name='隔离建议来源方案', data={
        'source_suggestion_id':confirmed['id'], 'candidates':[{'case_id':case['id'], 'sample_count':1, 'unit_cost':0}],
        'budget':10, 'required_categories':['电动自行车']}))
    assert plan['data']['suggestion_ref']['id'] == confirmed['id']
    queued = await supervision.queue_run('sampling-plans', plan['id'], RunRequest(version=1,operation='sampling',request_key=str(uuid4())))
    result = await supervision.execute_run(queued['id'])
    assert result['status'] == 'completed', result
    plan = await supervision.get('sampling-plans', plan['id'])
    review = await supervision.submit_review('sampling-plans', plan.id, ReviewRequest(version=plan.version, operation='sampling.approve'))
    with pytest.raises(ForbiddenError):
        await supervision.review_decision(review['id'], ReviewDecision(decision='accept',comment='禁止本人审批'))
    await formal[2]('expert2').review_decision(review['id'], ReviewDecision(decision='accept',comment='独立批准方向性抽查'))
    assert plan.status == 'approved' and not plan.data['task_ids']
    lab = await RiskLabService(db, risk('expert').current).decide(case['id'], LabDecision(assessment_id=assessment['id'],
        expected_basis_hash=context['basis_hash'], mode='skip', purpose='当前仅形成方向性建议'))
    assert lab['status'] == 'skipped'
    report = await RiskReportService(db, risk('expert').current).create(case['id'], RiskReportCreate(
        assessment_id=assessment['id'], expected_basis_hash=context['basis_hash']))
    assert report['status'] == 'frozen' and report['snapshot']['execution_mode'] == 'business'
    assert report['snapshot']['llm_called'] is False
    rendered = str(report['sections'])
    assert '演示' not in rendered and '模拟' not in rendered
    from app.services.report_renderers.docx_renderer import DocxRenderer
    from app.services.report_renderers.pdf_renderer import PdfRenderer
    assert DocxRenderer().render({'risk_report':report}).startswith(b'PK')
    assert PdfRenderer().render({'risk_report':report}).startswith(b'%PDF')
    source = await db.get(QualitySourceRecord, formal[3]['id'])
    source.deleted_at = datetime.utcnow()
    await db.flush()
    with pytest.raises((ConflictError, ValidationError, NotFoundError)):
        await supervision.sampling_analysis_contexts(plan)


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['unreviewed', 'self_review', 'synthetic', 'withdrawn', 'private'])
async def test_formal_downstream_rejects_invalid_evidence_and_review(formal, change):
    db, risk, _, record, case, assessment = formal
    row = await db.get(QualityRiskAssessment, assessment['id'])
    source = await db.get(QualitySourceRecord, record['id'])
    if change == 'unreviewed': row.status = 'awaiting_review'
    elif change == 'self_review': row.reviewed_by = row.submitted_by
    elif change == 'synthetic': source.data_nature = 'synthetic'
    elif change == 'private': source.authorization_scope = 'private'
    else: source.deleted_at = datetime.utcnow()
    await db.flush()
    svc = RiskWorkflowContextService(db, risk('expert').current)
    with pytest.raises((ConflictError, ForbiddenError, ValidationError)):
        await svc.ensure_current(await svc.risk.risk_case(case['id']), row)


@pytest.mark.asyncio
async def test_formal_report_and_suggestion_become_historical_after_source_change(formal):
    db, risk, _, record, case, assessment = formal
    context, _ = await collaboration(formal)
    svc = RiskReportService(db, risk('expert').current)
    report = await svc.create(case['id'], RiskReportCreate(assessment_id=assessment['id'], expected_basis_hash=context['basis_hash']))
    source = await db.get(QualitySourceRecord, record['id'])
    source.content = {**source.content, 'text':'隔离来源已修订'}
    await db.flush()
    assert (await svc.get(report['id']))['effective_status'] == 'historical_snapshot'
    with pytest.raises((ConflictError, ValidationError)):
        await svc.create(case['id'], RiskReportCreate(assessment_id=assessment['id'], expected_basis_hash=context['basis_hash']))
