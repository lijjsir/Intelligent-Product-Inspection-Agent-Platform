from datetime import date, datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.config import settings
from app.core.exceptions import ForbiddenError
from app.models.organization import Organization
from app.models.quality_risk import QualitySourceRecord
from app.models.export_job import ExportJob
from app.schemas.quality_risk import QualityEventCreate, RiskCaseCreate, RiskAnalyzeRequest
from app.schemas.market_monitoring import MarketScan
from app.services.market_monitoring_service import MarketMonitoringService
from app.services.supervision_service import SupervisionService
from app.services.export_job_service import ExportJobService
from test_quality_risk_v4 import domain  # noqa: F401
from test_risk_completion import completion  # noqa: F401


@pytest.mark.asyncio
async def test_report_rechecks_raw_record_authorization_for_each_reader(completion):
    db, service, _, case, source, _, _, _, _, reports, _, payload = completion
    report = await reports().create(case['id'], payload)
    assert (await reports('expert2').get(report['id']))['snapshot'] == report['snapshot']
    import json
    job = ExportJob(id=str(uuid4()), org_id=service('expert2').org_id, actor_id=service('expert2').actor,
        report_name=report['title'], report_type='risk_assessment', format='pdf', status='success',
        config_json=json.dumps({'risk_report_id':report['id'],'snapshot_hash':report['snapshot_hash']}),
        created_at=datetime.utcnow(), updated_at=datetime.utcnow())
    db.add(job); await db.flush()
    peer_exports = ExportJobService(db,service('expert2').org_id,actor_user_id=service('expert2').actor,actor_role='expert')
    assert (await peer_exports.get_detail(job.id)).id == job.id
    raw = await db.get(QualitySourceRecord, source['id'])
    raw.authorization_scope = 'private'
    await db.flush()
    with pytest.raises(ForbiddenError):
        await reports('expert2').get(report['id'])
    with pytest.raises(ForbiddenError):
        await peer_exports.get_detail(job.id)
    assert await reports('expert2').list(case['id']) == []
    assert (await reports().get(report['id']))['snapshot'] == report['snapshot']


@pytest.mark.asyncio
async def test_demo_default_monitoring_uses_declared_anchor_not_wall_clock(domain, monkeypatch):
    db, service = domain
    monkeypatch.setattr(settings, 'quality_demo_enabled', True)
    org = await db.get(Organization, service('expert').org_id)
    org.settings = {'quality_supervision_enabled': True, 'execution_mode': 'demo', 'anchor_at': '2026-10-16T01:00:00'}
    await db.flush()
    report = await MarketMonitoringService(db, service('expert').current).report(MarketScan())
    assert report['as_of'] == '2026-10-16'
    assert report['date_basis'] == 'demo_anchor'
    explicit = await MarketMonitoringService(db, service('expert').current).report(MarketScan(as_of=date(2026, 10, 17)))
    assert explicit['as_of'] == '2026-10-17' and explicit['date_basis'] == 'explicit'
    monkeypatch.setattr(settings, 'quality_demo_enabled', False)
    org.settings = {**org.settings, 'execution_mode':'business'}
    await db.flush()
    business = await MarketMonitoringService(db, service('expert').current).report(MarketScan())
    from zoneinfo import ZoneInfo
    assert business['as_of'] == datetime.now(timezone.utc).astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()
    assert business['date_basis'] == 'current_day' and business['demo_anchor_as_of'] is None


@pytest.mark.asyncio
@pytest.mark.parametrize('has_known_time', [False, True])
async def test_formal_analysis_passes_unknown_event_times_without_fabrication(domain, monkeypatch, has_known_time):
    _, service = domain
    monkeypatch.setattr(settings, 'quality_demo_enabled', False)
    raw = await service('user').create_event(QualityEventCreate(record_type='public_opinion', content={'text': '事件时间未知的来源'}))
    ids = [raw['id']]
    if has_known_time:
        known = await service('user').create_event(QualityEventCreate(record_type='public_opinion', occurred_at=datetime(2026, 10, 15), content={'text': '明确时间来源'}))
        ids.append(known['id'])
    case = await service('user').create_risk_case(RiskCaseCreate(title='时间完整性检查', scope_type='mixed', scope={}, source_record_ids=ids))
    monkeypatch.setattr(SupervisionService, 'model_call', AsyncMock(return_value=None))
    execute = AsyncMock(return_value={'risk_level': 'unknown', 'model_versions': {'llm_called': False}})
    monkeypatch.setattr(SupervisionService, 'execute_agent_via_manager', execute)
    result = await service('user').analyze_risk(case['id'], RiskAnalyzeRequest())
    execute.assert_awaited_once()
    data = execute.call_args.args[0]['data']
    assert data['occurred_at'] == ('2026-10-15T00:00:00' if has_known_time else None)
    assert all(e['occurred_at'] is None for e in data['evidence'] if e['source_id'] == raw['id'])
    assert any('发生时间' in item for item in result['missing_inputs'])


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['pending', 'running'])
async def test_repeat_export_reuses_inflight_job_instead_of_spawning_duplicate(completion, monkeypatch, status):
    db, service, _, case, _, _, _, _, _, reports, _, payload = completion
    report = await reports().create(case['id'], payload)
    import json
    job = ExportJob(id=str(uuid4()), org_id=service('expert').org_id, actor_id=service('expert').actor,
        report_name=report['title'], report_type='risk_assessment', format='pdf', status=status,
        config_json=json.dumps({'risk_report_id':report['id'], 'snapshot_hash':report['snapshot_hash'], 'renderer_version':'risk-report-v1'}),
        created_at=datetime.utcnow(), updated_at=datetime.utcnow())
    db.add(job); await db.flush()
    expected_id = job.id
    generate = AsyncMock()
    monkeypatch.setattr('app.services.report_generation_service.generate_report', generate)
    exports = ExportJobService(db, service('expert').org_id, actor_user_id=service('expert').actor, actor_role='expert')
    result = await exports.create_job(service('expert').actor, {'report_type':'risk_assessment','format':'pdf','config_json':{'risk_report_id':report['id']}})
    assert result.id == expected_id and result.status == status
    generate.assert_not_awaited()
