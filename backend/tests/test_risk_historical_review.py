"""Purpose boundaries, independent review, and immutable historical reports in an isolated DB."""
from datetime import datetime
from hashlib import sha256
from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from pypdf import PdfWriter

from test_quality_risk_v4 import domain  # noqa: F401
from test_risk_sampling_workflow import flow  # noqa: F401
from test_formal_risk_completion import formal  # noqa: F401
from app.core.exceptions import ConflictError, ForbiddenError, ValidationError
from app.models.quality_risk import QualityAttachment, QualityRiskAssessment, QualitySourceRecord
from app.schemas.quality_risk import QualityEventCreate, RiskAnalyzeRequest, RiskCaseCreate, RiskReviewRequest
from app.schemas.risk_completion import LabDecision, RiskReportCreate
from app.services.risk_decision_context_service import RiskDecisionContextService
from app.services.risk_lab_service import RiskLabService
from app.services.risk_report_service import RiskReportService
from app.services.risk_workflow_context_service import RiskWorkflowContextService
from app.services.supervision_service import SupervisionService


async def historical_case(formal, monkeypatch, *, complete=True, unknown=False):
    db, risk = formal[:2]
    writer = PdfWriter(); writer.add_blank_page(width=400, height=600)
    content = BytesIO(); writer.write(content)
    class Storage:
        def get_bytes(self, **kwargs): return content.getvalue(), 'application/pdf'
    monkeypatch.setattr('app.services.quality_risk_service.build_object_storage', lambda: Storage())
    owner = risk('user')
    attachment = QualityAttachment(org_id=owner.org_id, uploaded_by=owner.actor, file_name='isolated-history.pdf',
        mime_type='application/pdf', size_bytes=len(content.getvalue()), sha256=sha256(content.getvalue()).hexdigest(), bucket='isolated', object_key='history')
    db.add(attachment); await db.flush()
    record = await owner.create_event(QualityEventCreate(record_type='inspection_report',
        attachment_ids=[attachment.id] if complete else [], occurred_at=datetime(2021,9,3), authorization_scope='organization',
        content={'text':'Isolated documentary finding', 'report_no':'ISOLATED-2021', 'issued_date':'2021-09-03',
            'documentary_verdict':'原报告所检项目不合格', 'transcribed_values':[{'value':30.8, 'unit':'km/h'}]},
        provenance={'source_url':'https://example.com/isolated-report.pdf'}))
    # This fixture explicitly shares the source, as the real intake owner must do.
    source = await db.get(QualitySourceRecord, record['id'])
    source.authorization_scope = 'organization'; await db.flush()
    case = await owner.create_risk_case(RiskCaseCreate(title='隔离历史复盘', assessment_purpose='historical_review',
        scope_type='category', scope={'name':'电动自行车', 'historical_period':'2021'}, source_record_ids=[record['id']]))
    monkeypatch.setattr(SupervisionService, 'model_call', AsyncMock(return_value=None))
    monkeypatch.setattr(SupervisionService, 'execute_agent_via_manager', AsyncMock(return_value={
        'risk_level':'unknown' if unknown else 'medium', 'summary':'Historical sample only',
        'model_versions':{'llm_called':True, 'model_success':True, 'attempted_calls':2, 'successful_calls':2},
        'missing_inputs':['No new device observations', 'Current sales status unknown'],
        'limitations':['One original sample'], 'conflicts':['Do not extrapolate to current sales']}))
    draft = await risk('expert').analyze_risk(case['id'], RiskAnalyzeRequest())
    return db, risk, case, record, draft


def accept(draft, **kwargs):
    return RiskReviewRequest(assessment_id=draft['id'], decision='accept', comment='隔离测试核对原件及历史范围',
        historical_scope_confirmed=True, conflict_resolution='仅采信历史样品，未知现售情况作为限制保留', **kwargs)


@pytest.mark.asyncio
async def test_historical_report_can_finish_without_new_instruments_but_requires_real_independent_review(formal, monkeypatch):
    db, risk, case, record, draft = await historical_case(formal, monkeypatch)
    assert draft['status'] == 'awaiting_review' and draft['missing_inputs'] == []
    assert 'No new device observations' in draft['purpose_review']['limitations']
    assert draft['conflicts'] and draft['reviewed_by'] is None
    workflow = RiskWorkflowContextService(db, risk('expert').current)
    workspace = await risk('expert').risk_workspace(case['id'])
    reports = RiskReportService(db, risk('expert').current)
    with pytest.raises(ValidationError):
        await reports.create(case['id'], RiskReportCreate(assessment_id=draft['id'], expected_basis_hash=workspace['workflow_context']['basis_hash']))
    with pytest.raises(ForbiddenError):
        await risk('expert').review_risk(case['id'], accept(draft))
    with pytest.raises(ValidationError):
        await risk('expert2').review_risk(case['id'], RiskReviewRequest(decision='accept', comment='未确认历史范围'))
    with pytest.raises(ValidationError):
        await risk('expert2').review_risk(case['id'], RiskReviewRequest(decision='accept', comment='忽略冲突', historical_scope_confirmed=True))
    reviewed = await risk('expert2').review_risk(case['id'], accept(draft))
    assert reviewed['status'] == 'accepted' and reviewed['source_validation']['uncertainties']
    current = risk('expert').current
    with pytest.raises(ValidationError, match='历史资料复盘'):
        await RiskDecisionContextService(db, current).accepted(case['id'])
    assert (await RiskDecisionContextService(db, current, workflow.risk.storage).accepted(case['id'], allow_historical=True))['version'] == 1
    context = (await risk('expert').risk_workspace(case['id']))['workflow_context']
    assert context['eligible'], context['blockers']
    with pytest.raises(ValidationError, match='历史资料复盘'):
        await RiskLabService(db, current).decide(case['id'], LabDecision(assessment_id=draft['id'], expected_basis_hash=context['basis_hash'],
            verification_path='task', mode='verify', purpose='不能在历史复盘中补造新检测'))
    report = await reports.create(case['id'], RiskReportCreate(assessment_id=draft['id'], expected_basis_hash=context['basis_hash']))
    assert '历史资料复盘报告' in report['title']
    assert report['snapshot']['report_type'] == 'historical_review'
    assert report['snapshot']['documentary_findings'][0]['original_verdict'] == '原报告所检项目不合格'
    assert report['snapshot']['review']['historical_scope_confirmed'] is True
    assert 'No new device observations' in report['snapshot']['conclusion']['limitations']
    from app.services.report_renderers.pdf_renderer import PdfRenderer
    from app.services.report_renderers.docx_renderer import DocxRenderer
    assert PdfRenderer().render({'risk_report':report}).startswith(b'%PDF')
    assert DocxRenderer().render({'risk_report':report}).startswith(b'PK')
    original = await db.get(QualitySourceRecord, record['id'])
    original.content = {**original.content, 'documentary_verdict':'改动原始结论'}; await db.flush()
    assert (await reports.get(report['id']))['effective_status'] == 'historical_snapshot'
    with pytest.raises((ConflictError, ValidationError)):
        await workflow.ensure_current(await workflow.risk.risk_case(case['id']), await db.get(QualityRiskAssessment, draft['id']))


@pytest.mark.asyncio
async def test_history_missing_original_cannot_be_overridden_by_expert_grade(formal, monkeypatch):
    _, risk, case, _, draft = await historical_case(formal, monkeypatch, complete=False)
    assert draft['status'] == 'awaiting_evidence' and '所引用检测报告的原件' in draft['missing_inputs']
    with pytest.raises(ValidationError):
        await risk('expert2').review_risk(case['id'], accept(draft, risk_level='low'))


@pytest.mark.asyncio
async def test_unknown_risk_needs_explicit_grade_even_for_history(formal, monkeypatch):
    _, risk, case, _, draft = await historical_case(formal, monkeypatch, unknown=True)
    assert draft['status'] == 'awaiting_evidence' and draft['risk_level'] == 'unknown'
    with pytest.raises(ValidationError, match='风险等级'):
        await risk('expert2').review_risk(case['id'], accept(draft))


@pytest.mark.asyncio
async def test_old_history_draft_requires_regeneration_not_silent_reclassification(formal, monkeypatch):
    db, risk, case, _, draft = await historical_case(formal, monkeypatch)
    row = await db.get(QualityRiskAssessment, draft['id'])
    row.model_versions = {k:v for k,v in row.model_versions.items() if k != 'purpose_review'}; await db.flush()
    with pytest.raises(ValidationError):
        await risk('expert2').review_risk(case['id'], accept(draft))


@pytest.mark.asyncio
async def test_refresh_reuses_only_unchanged_saved_analysis_without_new_calls_or_approval(formal, monkeypatch):
    db, risk, case, record, original = await historical_case(formal, monkeypatch)
    execute = AsyncMock()
    monkeypatch.setattr(SupervisionService, 'execute_agent_via_manager', execute)
    derived = await risk('expert').refresh_historical_requirements(case['id'], original['id'])
    execute.assert_not_awaited()
    assert derived['version'] == 2 and derived['status'] == 'awaiting_review'
    assert derived['analysis_summary'] == original['analysis_summary']
    assert derived['analysis_origin']['assessment_id'] == original['id']
    assert derived['model_versions']['llm_called'] is False and derived['model_versions']['attempted_calls'] == 0
    assert derived['reviewed_by'] is None and derived['trust_status'] == 'needs_review'
    assert (await risk('expert').refresh_historical_requirements(case['id'], original['id']))['id'] == derived['id']
    with pytest.raises(ValidationError):
        await risk('expert').refresh_historical_requirements(case['id'], derived['id'])
    raw = await db.get(QualitySourceRecord, record['id']); raw.content = {**raw.content, 'text':'Changed source'}; await db.flush()
    with pytest.raises(ValidationError):
        await risk('expert').refresh_historical_requirements(case['id'], original['id'])
