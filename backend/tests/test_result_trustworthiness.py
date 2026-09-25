from types import SimpleNamespace

import pytest

from agent.subgraphs.quality_analysis.nodes import _evidence_citations
from app.services.evidence_arbitration_service import EvidenceArbitrationService
from app.services.inspection_standard_service import InspectionStandardService
from app.services.result_service import result_effective_verdict, result_score_status
from app.services.stability_service import StabilityService


def test_empty_rag_response_is_not_counted_as_evidence_source():
    result = EvidenceArbitrationService._build_result(
        query="晶体管检测标准",
        rag_hits=[{
            "hits": [], "hit_count": 0, "candidate_count": 0,
            "rag_space_ids": [], "rag_space_names": [], "top_k": 5,
        }],
        memory_hits=[],
        kg_hits=[],
        normalized=[],
        conflicts=[],
    )

    packet = result["evidence_packet"]
    assert packet["source_count"] == 0
    assert packet["sources"] == {}
    assert packet["rag_retrieval"]["attempted"] is True
    assert packet["rag_retrieval"]["hit_count"] == 0


def test_only_real_rag_chunks_become_citations():
    packet = {
        "sources": {
            "rag": {
                "items": [{
                    "hits": [
                        {
                            "chunk_id": "chunk-1",
                            "document_name": "晶体管检验规范",
                            "full_path": "标准库/晶体管检验规范.pdf",
                            "text": "引脚镀层不得出现氧化发黑。",
                            "score": 0.87,
                        }
                    ]
                }]
            }
        }
    }

    citations = _evidence_citations(packet)
    assert citations == [{
        "id": "chunk-1",
        "title": "晶体管检验规范",
        "source": "标准库/晶体管检验规范.pdf",
        "quote": "引脚镀层不得出现氧化发黑。",
        "score": 0.87,
        "kind": "rag",
        "rag_space_id": None,
    }]


def test_ai_gate_does_not_treat_no_detected_defects_as_document_evidence():
    gate = InspectionStandardService._build_ai_gate(
        spec=None,
        citations=[],
        reasoning_chain={"visual_inspection_result": {"summary": "未见缺陷"}},
        defects=[],
        overall_score=0.95,
    )

    assert gate["evidence_score"] == 0.0
    assert gate["traceability_score"] == 0.25
    assert "evidence_below_threshold" in gate["reasons"]
    assert "traceability_below_threshold" in gate["reasons"]


def test_quality_analysis_legacy_scores_are_marked_uncalibrated():
    result = SimpleNamespace(
        reasoning_chain={},
        prompt_version="quality_analysis_prompt_v1",
    )
    assert result_score_status(result) == "not_calibrated"


def test_automatic_pass_without_verified_rag_evidence_requires_review():
    result = SimpleNamespace(
        verdict="pass", reviewed_by=None, reasoning_chain={},
        prompt_version="quality_analysis_prompt_v1", citations={"items": []},
    )
    assert result_effective_verdict(result) == "manual_required"
    result.reviewed_by = "expert-1"
    assert result_effective_verdict(result) == "pass"


@pytest.mark.asyncio
async def test_legacy_stability_does_not_keep_fake_full_evidence_scores(monkeypatch):
    report = SimpleNamespace(
        id="stability-1", task_id="task-1", result_id="result-1", org_id="org-1",
        evidence_score=1.0, consistency_score=0.95, confidence_score=0.95,
        traceability_score=1.0, anomaly_score=0.0, risk_score=0.5, risk_level="medium",
        dimension_detail={}, sampling_results=None, root_cause=None, handled_by=None,
        handled_at=None, handle_action=None, handle_note=None, created_at=None,
    )
    result = SimpleNamespace(
        verdict="manual_required", prompt_version="quality_analysis_prompt_v1",
        citations={"items": [{"type": "standard", "title": "无法核验的旧来源"}]},
        reasoning_chain={"standard_evaluation": {"summary": "需要人工复核"}},
    )

    class StabilityRepo:
        async def get_by_task(self, *_args):
            return report

    class ResultRepo:
        def __init__(self, _session):
            pass

        async def get_by_task(self, *_args):
            return result

    monkeypatch.setattr("app.services.stability_service.ResultRepository", ResultRepo)
    service = StabilityService(object(), "org-1")
    service._repo = StabilityRepo()
    payload = await service.get_by_task("task-1")

    assert payload["evidence_score"] == 0.0
    assert payload["traceability_score"] == 0.25
    assert payload["dimension_detail"]["consistency"]["status"] == "not_measured"
    assert "知识库" in payload["root_cause"]
