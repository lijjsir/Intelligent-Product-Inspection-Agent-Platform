import pytest
from types import SimpleNamespace

from agent.contracts import NormalizedAttachment, NormalizedRequest
from agent.subgraphs.llm_native_quality.graph import LLMNativeQualitySubgraph


@pytest.mark.asyncio
async def test_llm_native_quality_accepts_structured_txt_without_images(monkeypatch):
    file_text = """
record_id=SCREW-PASS-01
product_id=screw
spec_code=SCREW-A-2026-V1
inspection_type=appearance
surface_condition=clean
crack_count=0
surface_scratch_count=0
coating_defect_count=0
thread_damage_count=0
oil_stain_count=0
expected_decision=PASS
""".strip()

    monkeypatch.setattr(
        "agent.subgraphs.llm_native_quality.graph.FileStorageService.file_bytes_from_url",
        lambda self, url: (file_text.encode("utf-8"), "text/plain"),
    )

    async def fake_evaluate(self, **kwargs):
        assert kwargs["spec_code"] == "SCREW-A-2026-V1"
        assert kwargs["defects"] == []
        return {
            "verdict": "manual_required",
            "summary": "ai gate blocked auto pass",
            "reasons": ["ai_gate_blocked_auto_pass"],
            "matched_rules": [],
            "unmatched_defects": [],
            "ai_gate": {
                "confidence_score": 0.96,
                "evidence_score": 1.0,
                "traceability_score": 1.0,
                "reasons": [],
            },
        }

    monkeypatch.setattr(
        "agent.subgraphs.llm_native_quality.graph.InspectionStandardService.evaluate",
        fake_evaluate,
    )

    output = await LLMNativeQualitySubgraph().run(
        NormalizedRequest(
            request_id="req-1",
            workflow_run_id="wf-1",
            org_id="org-1",
            user_id="user-1",
            query="Please inspect this screw record.",
            attachments=[
                NormalizedAttachment(
                    id="file-1",
                    name="screw_pass_01.txt",
                    url="/uploads/native/screw_pass_01.txt",
                    kind="file",
                )
            ],
        )
    )

    assert output.action_state == "done"
    assert output.persistable_output.task is not None
    assert output.persistable_output.task.product_id == "screw"
    assert output.persistable_output.result is not None
    assert output.persistable_output.result.verdict == "pass"
    assert output.persistable_output.stability is not None
    assert output.persistable_output.stability.risk_level == "low"
    assert output.clarification is None


@pytest.mark.asyncio
async def test_llm_native_quality_marks_fail_when_structured_defects_hit_rules(monkeypatch):
    file_text = """
record_id=SCREW-FAIL-01
product_id=screw
spec_code=SCREW-A-2026-V1
inspection_type=appearance
surface_condition=scratch
crack_count=0
surface_scratch_count=2
coating_defect_count=0
thread_damage_count=0
oil_stain_count=0
expected_decision=FAIL
""".strip()

    monkeypatch.setattr(
        "agent.subgraphs.llm_native_quality.graph.FileStorageService.file_bytes_from_url",
        lambda self, url: (file_text.encode("utf-8"), "text/plain"),
    )

    async def fake_evaluate(self, **kwargs):
        assert len(kwargs["defects"]) == 2
        return {
            "verdict": "fail",
            "summary": "matched reject rule",
            "reasons": ["matched_reject_rule"],
            "matched_rules": [{"defect_type": "surface_scratch", "disposition": "fail"}],
            "unmatched_defects": [],
            "ai_gate": {
                "confidence_score": 0.42,
                "evidence_score": 1.0,
                "traceability_score": 1.0,
                "reasons": [],
            },
        }

    monkeypatch.setattr(
        "agent.subgraphs.llm_native_quality.graph.InspectionStandardService.evaluate",
        fake_evaluate,
    )

    output = await LLMNativeQualitySubgraph().run(
        NormalizedRequest(
            request_id="req-2",
            workflow_run_id="wf-2",
            org_id="org-1",
            user_id="user-1",
            query="Evaluate this screw record.",
            attachments=[
                NormalizedAttachment(
                    id="file-2",
                    name="screw_fail_02.txt",
                    url="/uploads/native/screw_fail_02.txt",
                    kind="file",
                )
            ],
        )
    )

    assert output.persistable_output.result is not None
    assert output.persistable_output.result.verdict == "fail"
    assert output.persistable_output.stability is not None
    assert output.persistable_output.stability.risk_level == "critical"
    assert output.persistable_output.alerts


@pytest.mark.asyncio
async def test_llm_native_quality_applies_dspy_review_gate_and_prompt_version(monkeypatch):
    file_text = """
record_id=SCREW-PASS-02
product_id=screw
spec_code=SCREW-A-2026-V1
inspection_type=appearance
surface_condition=clean
crack_count=0
surface_scratch_count=0
coating_defect_count=0
thread_damage_count=0
oil_stain_count=0
expected_decision=PASS
""".strip()

    monkeypatch.setattr(
        "agent.subgraphs.llm_native_quality.graph.FileStorageService.file_bytes_from_url",
        lambda self, url: (file_text.encode("utf-8"), "text/plain"),
    )

    async def fake_evaluate(self, **kwargs):
        return {
            "verdict": "pass",
            "summary": "baseline pass",
            "reasons": ["structured_record_verified"],
            "matched_rules": [],
            "unmatched_defects": [],
            "ai_gate": {
                "confidence_score": 0.91,
                "evidence_score": 1.0,
                "traceability_score": 1.0,
                "reasons": [],
            },
        }

    class FakeProfile:
        active_prompt_version = "llm-native-review-gate-v4"

        def get(self, target_key: str):
            if target_key == "llm_native_quality.review_gate":
                return SimpleNamespace(
                    config_payload={"min_confidence": 0.95},
                )
            if target_key == "llm_native_quality.planner":
                return SimpleNamespace(
                    config_payload={"default_priority": 7},
                )
            return None

        def as_metadata(self):
            return {
                "subgraph_key": "llm_native_quality",
                "active_prompt_version": self.active_prompt_version,
                "targets": {"llm_native_quality.review_gate": {"artifact_version": self.active_prompt_version}},
            }

    monkeypatch.setattr(
        "agent.subgraphs.llm_native_quality.graph.InspectionStandardService.evaluate",
        fake_evaluate,
    )
    async def fake_runtime_profile(org_id: str, subgraph_key: str):
        return FakeProfile()

    monkeypatch.setattr(
        "agent.subgraphs.llm_native_quality.graph.resolve_dspy_runtime_profile",
        fake_runtime_profile,
    )

    output = await LLMNativeQualitySubgraph().run(
        NormalizedRequest(
            request_id="req-3",
            workflow_run_id="wf-3",
            org_id="org-1",
            user_id="user-1",
            query="Evaluate this structured screw record.",
            attachments=[
                NormalizedAttachment(
                    id="file-3",
                    name="screw_pass_02.txt",
                    url="/uploads/native/screw_pass_02.txt",
                    kind="file",
                )
            ],
        )
    )

    assert output.persistable_output.result is not None
    assert output.persistable_output.result.verdict == "manual_required"
    assert output.persistable_output.task is not None
    assert output.persistable_output.task.priority == 7
    assert output.persistable_output.stability is not None
    assert output.persistable_output.stability.risk_level == "medium"
    assert output.persistable_output.quality_trace is not None
    assert output.persistable_output.quality_trace.prompt_version == "llm-native-review-gate-v4"


@pytest.mark.asyncio
async def test_llm_native_quality_supports_food_records_and_real_rag_summary(monkeypatch):
    file_text = """
{
  "product_id": "FOOD-001",
  "category": "food",
  "product_name": "Pure Milk",
  "label_info": {
    "product_name_present": true,
    "ingredient_list_present": true,
    "net_content_present": true,
    "manufacturer_present": true,
    "production_date_present": true,
    "shelf_life_present": true,
    "storage_condition_present": true,
    "nutrition_table_present": true,
    "allergen_warning_present": true,
    "barcode_present": true,
    "font_clear": true
  },
  "packaging": {
    "seal_integrity": "good",
    "leakage": false,
    "deformation": false,
    "surface_contamination": false
  },
  "process_records": {
    "traceability_record": true
  },
  "traceability": {
    "qr_code": "https://trace.example.com/FOOD-001",
    "supplier_batch_linked": true
  },
  "expected_result": {
    "is_qualified": true
  }
}
""".strip()

    monkeypatch.setattr(
        "agent.subgraphs.llm_native_quality.graph.FileStorageService.file_bytes_from_url",
        lambda self, url: (file_text.encode("utf-8"), "text/plain"),
    )

    async def fake_evaluate(self, **kwargs):
        assert kwargs["spec_code"] == "FOOD-RAG-BASE-V1"
        assert kwargs["defects"] == []
        assert len(kwargs["citations"]) >= 2
        return {
            "verdict": "pass",
            "summary": "food baseline passed",
            "reasons": ["structured_food_record_verified"],
            "matched_rules": [],
            "unmatched_defects": [],
            "ai_gate": {
                "confidence_score": 0.97,
                "evidence_score": 1.0,
                "traceability_score": 1.0,
                "reasons": [],
            },
        }

    async def fake_search(self, *, rag_space_id: str | None, query: str, top_k: int = 4):
        assert rag_space_id == "rag-food"
        assert "FOOD-001" in query
        return {
            "rag_space_id": "rag-food",
            "rag_space_name": "food",
            "hit_count": 1,
            "latency_ms": 12.5,
            "hits": [
                {
                    "title": "food-standard.txt",
                    "source": "food-standard.txt",
                    "quote": "Traceability QR code and label completeness are required.",
                    "score": 0.88,
                }
            ],
        }

    monkeypatch.setattr(
        "agent.subgraphs.llm_native_quality.graph.InspectionStandardService.evaluate",
        fake_evaluate,
    )
    monkeypatch.setattr(
        "agent.subgraphs.llm_native_quality.graph.RagRetrievalService.search",
        fake_search,
    )

    output = await LLMNativeQualitySubgraph().run(
        NormalizedRequest(
            request_id="req-food-1",
            workflow_run_id="wf-food-1",
            org_id="org-1",
            user_id="user-1",
            query="Inspect this structured food sample.",
            ext={"selected_rag_space_id": "rag-food"},
            attachments=[
                NormalizedAttachment(
                    id="file-food-1",
                    name="1.txt",
                    url="/uploads/native/1.txt",
                    kind="file",
                )
            ],
        )
    )

    assert output.persistable_output.task is not None
    assert output.persistable_output.task.product_id == "FOOD-001"
    assert output.persistable_output.task.spec_code == "FOOD-RAG-BASE-V1"
    assert output.persistable_output.result is not None
    assert output.persistable_output.result.verdict == "pass"
    assert output.result_card is not None
    assert output.result_card["product_family"] == "food"
    assert output.rag_summary is not None
    assert output.rag_summary["rag_space_name"] == "food"
    assert output.rag_summary["hit_count"] == 1
    assert output.expectation_check is not None
    assert output.expectation_check["matched"] is True
