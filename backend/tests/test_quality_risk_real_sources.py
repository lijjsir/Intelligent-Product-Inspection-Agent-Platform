from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.schemas.quality_risk import QualityEventCreate, RiskAnalyzeRequest, RiskCaseCreate
from app.services.quality_risk_service import risk_analysis_text
from app.services.supervision_service import SupervisionService
from agent.subgraphs.supervision.agents import AGENTS, parse_model_json
from test_quality_risk_v4 import domain  # noqa: F401


def test_structured_public_report_keeps_report_identity_and_actual_values():
    text = risk_analysis_text({"title": "Historical report", "report_no": "JG2128520085", "transcribed_values": [{"value": 51.4, "unit": "kg"}], "limitations": ["No new physical inspection"]})
    assert "JG2128520085" in text and "51.4" in text
    assert "No new physical inspection" in text


@pytest.mark.parametrize('response', [
    {'ok': True, '__meta__': {'usage': {}}},
    {'choices': [{'message': {'content': '```json\n{"ok":true}\n```'}}]},
    {'text': '{"ok":true}', '__meta__': {}},
])
def test_transport_and_normalized_json_are_both_supported(response):
    assert parse_model_json(response) == {'ok': True}


@pytest.mark.parametrize('response', [{"__meta__": {}}, {"choices": []}, {"text": "not JSON", "__meta__": {}}])
def test_empty_and_non_json_completions_are_not_success(response):
    with pytest.raises((ValueError, TypeError)):
        parse_model_json(response)


@pytest.mark.asyncio
@pytest.mark.parametrize('source_type', ['supervision_inspection', 'inspection_report', 'enforcement_case'])
async def test_official_facts_do_not_require_a_fabricated_complaint(source_type):
    async def model(name, payload):
        return {'summary':'public documentary finding', 'risk_level':'medium', 'evidence_ids':['official'], 'missing_inputs':[], 'conflicts':[]} if name == 'risk_case.assess' else {'supported':True, 'issues':[]}
    result = await AGENTS['public_opinion_monitoring'].run({'data':{'evidence':[{'evidence_id':'official','source_id':'report','source_type':source_type,'nature':'observed','text':'Official documentary finding'}]}}, model)
    assert result['status'] == 'awaiting_review' and result['missing_inputs'] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("record_type", ["supervision_inspection", "inspection_report", "enforcement_case"])
async def test_official_inspection_and_enforcement_records_enter_analysis(domain, monkeypatch, record_type):
    _, service = domain
    monkeypatch.setattr(settings, "quality_demo_enabled", False)
    raw = await service("user").create_event(QualityEventCreate(record_type=record_type, occurred_at=datetime(2021, 9, 3), content={"title": "Public report", "report_no": "JG2128520085", "transcribed_values": [{"value": 73, "unit": "dB(A)"}]}))
    case = await service("user").create_risk_case(RiskCaseCreate(title="Historical source audit", scope_type="mixed", scope={"case_mode":"public_historical_review","historical_period":"2021"}, source_record_ids=[raw["id"]]))
    monkeypatch.setattr(SupervisionService, "model_call", AsyncMock(return_value=None))
    execute = AsyncMock(return_value={"risk_level": "unknown", "model_versions": {"llm_called": False}})
    monkeypatch.setattr(SupervisionService, "execute_agent_via_manager", execute)
    result = await service("user").analyze_risk(case["id"], RiskAnalyzeRequest())
    execute.assert_awaited_once()
    data = execute.call_args.args[0]["data"]
    assert "JG2128520085" in data["description"] and "73" in data["description"]
    assert data["occurred_at"] == "2021-09-03T00:00:00"
    assert data["assessment_context"]["scope"]["historical_period"] == "2021"
    assert result["status"] != "accepted" and result["reviewed_by"] is None


@pytest.mark.asyncio
async def test_policy_text_alone_does_not_become_a_product_risk_finding(domain, monkeypatch):
    _, service = domain
    monkeypatch.setattr(settings, "quality_demo_enabled", False)
    raw = await service("user").create_event(QualityEventCreate(record_type="policy_document", content={"text": "A requirement, not an observed product finding"}))
    case = await service("user").create_risk_case(RiskCaseCreate(title="Requirement-only case", scope_type="mixed", scope={}, source_record_ids=[raw["id"]]))
    execute = AsyncMock()
    monkeypatch.setattr(SupervisionService, "execute_agent_via_manager", execute)
    result = await service("user").analyze_risk(case["id"], RiskAnalyzeRequest())
    execute.assert_not_awaited()
    assert result["risk_level"] == "unknown"


@pytest.mark.asyncio
async def test_analysis_evidence_gaps_and_conflicts_are_visible_in_saved_draft(domain, monkeypatch):
    _, service = domain
    monkeypatch.setattr(settings, 'quality_demo_enabled', False)
    raw = await service('user').create_event(QualityEventCreate(record_type='inspection_report', occurred_at=datetime(2021,9,3), content={'text':'A bounded historical report'}))
    case = await service('user').create_risk_case(RiskCaseCreate(title='Public report with limitations', scope_type='mixed',scope={},source_record_ids=[raw['id']]))
    monkeypatch.setattr(SupervisionService, 'model_call', AsyncMock(return_value=None))
    monkeypatch.setattr(SupervisionService, 'execute_agent_via_manager', AsyncMock(return_value={'risk_level':'medium','status':'manual_review_required','missing_inputs':['Original repeated readings are not public'],'conflicts':['Only one historical sample']}))
    result = await service('user').analyze_risk(case['id'], RiskAnalyzeRequest())
    assert 'Original repeated readings are not public' in result['missing_inputs']
    assert any(item.get('conflict') == 'Only one historical sample' for item in result['conflicts'])
    assert result['status'] == 'awaiting_evidence' and result['reviewed_by'] is None


@pytest.mark.asyncio
async def test_full_fact_signal_is_preserved_outside_short_risk_classification(domain, monkeypatch):
    _, service = domain
    raw = await service('user').create_event(QualityEventCreate(record_type='enforcement_case', content={'text':'Documented source'}))
    case = await service('user').create_risk_case(RiskCaseCreate(title='Long factual explanation',scope_type='mixed',scope={},source_record_ids=[raw['id']]))
    long_fact = 'A factual narrative with citations. ' * 30
    monkeypatch.setattr(SupervisionService, 'model_call', AsyncMock(return_value=None))
    monkeypatch.setattr(SupervisionService, 'execute_agent_via_manager', AsyncMock(return_value={'risk_level':'medium','normalized_signals':[long_fact]}))
    result = await service('user').analyze_risk(case['id'], RiskAnalyzeRequest())
    assert result['risk_type'] is None
    assert result['analysis_summary']['signals'] == [long_fact.strip()]
