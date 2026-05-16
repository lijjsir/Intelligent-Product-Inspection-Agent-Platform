import pytest
from types import SimpleNamespace

from agent.contracts import NormalizedAttachment, NormalizedRequest
from agent.subgraphs.quality_judgement.graph import QualityJudgementSubgraph


@pytest.mark.asyncio
async def test_quality_judgement_accepts_structured_txt_without_images(monkeypatch):
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
        "agent.subgraphs.quality_judgement.graph.FileStorageService.file_bytes_from_url",
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
        "agent.subgraphs.quality_judgement.graph.InspectionStandardService.evaluate",
        fake_evaluate,
    )

    output = await QualityJudgementSubgraph().run(
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
async def test_quality_judgement_marks_fail_when_structured_defects_hit_rules(monkeypatch):
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
        "agent.subgraphs.quality_judgement.graph.FileStorageService.file_bytes_from_url",
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
        "agent.subgraphs.quality_judgement.graph.InspectionStandardService.evaluate",
        fake_evaluate,
    )

    output = await QualityJudgementSubgraph().run(
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
async def test_quality_judgement_applies_dspy_review_gate_and_prompt_version(monkeypatch):
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
        "agent.subgraphs.quality_judgement.graph.FileStorageService.file_bytes_from_url",
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
            if target_key == "quality_judgement.review_gate":
                return SimpleNamespace(
                    config_payload={"min_confidence": 0.95},
                )
            if target_key == "quality_judgement.planner":
                return SimpleNamespace(
                    config_payload={"default_priority": 7},
                )
            return None

        def as_metadata(self):
            return {
                "subgraph_key": "quality_judgement",
                "active_prompt_version": self.active_prompt_version,
                "targets": {"quality_judgement.review_gate": {"artifact_version": self.active_prompt_version}},
            }

    monkeypatch.setattr(
        "agent.subgraphs.quality_judgement.graph.InspectionStandardService.evaluate",
        fake_evaluate,
    )
    async def fake_runtime_profile(org_id: str, subgraph_key: str):
        return FakeProfile()

    monkeypatch.setattr(
        "agent.subgraphs.quality_judgement.graph.resolve_dspy_runtime_profile",
        fake_runtime_profile,
    )

    output = await QualityJudgementSubgraph().run(
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
async def test_quality_judgement_supports_food_records_and_real_rag_summary(monkeypatch):
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
        "agent.subgraphs.quality_judgement.graph.FileStorageService.file_bytes_from_url",
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

    async def fake_search(
        self,
        *,
        rag_space_id: str | None,
        query: str,
        top_k: int = 4,
        scope_node_ids: list[str] | None = None,
    ):
        assert rag_space_id == "rag-food"
        assert scope_node_ids == ["folder-food"]
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
        "agent.subgraphs.quality_judgement.graph.InspectionStandardService.evaluate",
        fake_evaluate,
    )
    monkeypatch.setattr(
        "agent.subgraphs.quality_judgement.graph.RagRetrievalService.search",
        fake_search,
    )

    output = await QualityJudgementSubgraph().run(
        NormalizedRequest(
            request_id="req-food-1",
            workflow_run_id="wf-food-1",
            org_id="org-1",
            user_id="user-1",
            query="Inspect this structured food sample.",
            ext={"selected_rag_space_id": "rag-food", "selected_rag_scope_node_ids": ["folder-food"]},
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


@pytest.mark.asyncio
async def test_quality_judgement_supports_electronics_records_with_default_spec(monkeypatch):
    file_text = """
{
  "product_id": "ELEC-001",
  "category": "electronics",
  "product_name": "65W USB-C Adapter",
  "model": "PD65-A1",
  "marking_info": {
    "model_marked": true,
    "rated_input_marked": true,
    "rated_output_marked": true,
    "manufacturer_name_marked": true,
    "manufacturer_address_marked": true,
    "warning_marked": true,
    "serial_number_marked": true
  },
  "structure_check": {
    "sharp_edge": false,
    "fire_enclosure_material_grade": "V-0"
  },
  "electrical_safety": {
    "electric_strength_kv": 3.0,
    "temperature_rise_max_c": 48,
    "creepage_distance_mm": 5.2,
    "clearance_mm": 4.8
  },
  "emc_test": {
    "conducted_emission": "pass",
    "radiated_emission": "pass",
    "esd_immunity": "pass",
    "surge_immunity": "pass",
    "eft_immunity": "pass"
  },
  "documents": {
    "inspection_report": true,
    "certificate_file": true,
    "traceability_code": true
  },
  "expected_result": {
    "is_qualified": true
  }
}
""".strip()

    monkeypatch.setattr(
        "agent.subgraphs.quality_judgement.graph.FileStorageService.file_bytes_from_url",
        lambda self, url: (file_text.encode("utf-8"), "text/plain"),
    )

    async def fake_evaluate(self, **kwargs):
        assert kwargs["spec_code"] == "ELEC-RAG-BASE-V1"
        assert kwargs["defects"] == []
        return {
            "verdict": "pass",
            "summary": "electronics baseline passed",
            "reasons": ["structured_record_verified"],
            "matched_rules": [],
            "unmatched_defects": [],
            "ai_gate": {
                "confidence_score": 0.96,
                "evidence_score": 1.0,
                "traceability_score": 1.0,
                "reasons": [],
            },
        }

    async def fake_search(
        self,
        *,
        rag_space_id: str | None,
        query: str,
        top_k: int = 4,
        scope_node_ids: list[str] | None = None,
    ):
        assert "ELEC-001" in query
        assert scope_node_ids == []
        return {
            "rag_space_id": None,
            "rag_space_name": None,
            "hit_count": 0,
            "latency_ms": 5.0,
            "hits": [],
        }

    monkeypatch.setattr(
        "agent.subgraphs.quality_judgement.graph.InspectionStandardService.evaluate",
        fake_evaluate,
    )
    monkeypatch.setattr(
        "agent.subgraphs.quality_judgement.graph.RagRetrievalService.search",
        fake_search,
    )

    output = await QualityJudgementSubgraph().run(
        NormalizedRequest(
            request_id="req-elec-1",
            workflow_run_id="wf-elec-1",
            org_id="org-1",
            user_id="user-1",
            query="Inspect this electronics record.",
            attachments=[
                NormalizedAttachment(
                    id="file-elec-1",
                    name="adapter.txt",
                    url="/uploads/native/adapter.txt",
                    kind="file",
                )
            ],
        )
    )

    assert output.persistable_output.task is not None
    assert output.persistable_output.task.product_id == "ELEC-001"
    assert output.persistable_output.task.spec_code == "ELEC-RAG-BASE-V1"
    assert output.persistable_output.result is not None
    assert output.persistable_output.result.verdict == "pass"
    assert output.result_card is not None
    assert output.result_card["product_family"] == "electronics"
    assert "电子产品质检已完成" in output.answer
    assert output.expectation_check is not None
    assert output.expectation_check["matched"] is True


@pytest.mark.asyncio
async def test_quality_judgement_maps_electronics_failures_to_electronics_rules(monkeypatch):
    file_text = """
{
  "product_id": "ELEC-003",
  "category": "electronics",
  "product_name": "Smart Power Strip",
  "marking_info": {
    "rated_output_marked": false,
    "manufacturer_address_marked": false,
    "warning_marked": false
  },
  "structure_check": {
    "socket_shutter_present": false,
    "sharp_edge": true,
    "fire_enclosure_material_grade": "unknown"
  },
  "electrical_safety": {
    "ground_continuity_ohm": 0.65,
    "electric_strength_kv": 1.2,
    "temperature_rise_max_c": 76,
    "creepage_distance_mm": 2.1,
    "clearance_mm": 1.8
  },
  "emc_test": {
    "conducted_emission": "fail",
    "radiated_emission": "fail",
    "esd_immunity": "function_loss_manual_restart_needed",
    "surge_immunity": "fail",
    "eft_immunity": "fail"
  },
  "documents": {
    "inspection_report": false,
    "certificate_file": false,
    "traceability_code": false,
    "ccc_file": false
  },
  "functional_test": {
    "usb_output_voltage_v": 5.7
  },
  "expected_result": {
    "is_qualified": false
  }
}
""".strip()

    monkeypatch.setattr(
        "agent.subgraphs.quality_judgement.graph.FileStorageService.file_bytes_from_url",
        lambda self, url: (file_text.encode("utf-8"), "text/plain"),
    )

    async def fake_evaluate(self, **kwargs):
        defect_types = {item["type"] for item in kwargs["defects"]}
        assert kwargs["spec_code"] == "ELEC-RAG-BASE-V1"
        assert "electronics.marking.rated_output_marked" in defect_types
        assert "electronics.structure.socket_shutter_present" in defect_types
        assert "electronics.safety.ground_continuity_ohm" in defect_types
        assert "electronics.emc.conducted_emission" in defect_types
        assert "electronics.documents.ccc_file" in defect_types
        assert "electronics.functional.usb_output_voltage_v" in defect_types
        return {
            "verdict": "fail",
            "summary": "electronics reject rules matched",
            "reasons": ["matched_reject_rule"],
            "matched_rules": [
                {"defect_type": "electronics.marking.rated_output_marked", "disposition": "fail"},
                {"defect_type": "electronics.safety.ground_continuity_ohm", "disposition": "fail"},
            ],
            "unmatched_defects": [],
            "ai_gate": {
                "confidence_score": 0.38,
                "evidence_score": 1.0,
                "traceability_score": 1.0,
                "reasons": [],
            },
        }

    monkeypatch.setattr(
        "agent.subgraphs.quality_judgement.graph.InspectionStandardService.evaluate",
        fake_evaluate,
    )

    output = await QualityJudgementSubgraph().run(
        NormalizedRequest(
            request_id="req-elec-2",
            workflow_run_id="wf-elec-2",
            org_id="org-1",
            user_id="user-1",
            query="Inspect this failed electronics sample.",
            attachments=[
                NormalizedAttachment(
                    id="file-elec-2",
                    name="power_strip.txt",
                    url="/uploads/native/power_strip.txt",
                    kind="file",
                )
            ],
        )
    )

    assert output.persistable_output.result is not None
    assert output.persistable_output.result.verdict == "fail"
    assert output.persistable_output.task is not None
    assert output.persistable_output.task.spec_code == "ELEC-RAG-BASE-V1"
    assert output.result_card is not None
    assert "electronics.marking.rated_output_marked" in output.result_card["failed_rules"]
    assert output.persistable_output.stability is not None
    assert output.persistable_output.stability.risk_level == "critical"


@pytest.mark.asyncio
async def test_quality_judgement_returns_task_action_for_unknown_product_family(monkeypatch):
    file_text = """
{
  "product_id": "CHEM-001",
  "category": "chemical",
  "product_name": "Industrial Solvent",
  "expected_result": {
    "is_qualified": false
  }
}
""".strip()

    monkeypatch.setattr(
        "agent.subgraphs.quality_judgement.graph.FileStorageService.file_bytes_from_url",
        lambda self, url: (file_text.encode("utf-8"), "text/plain"),
    )

    output = await QualityJudgementSubgraph().run(
        NormalizedRequest(
            request_id="req-unknown-1",
            workflow_run_id="wf-unknown-1",
            org_id="org-1",
            user_id="user-1",
            query="Inspect this unknown product family sample.",
            attachments=[
                NormalizedAttachment(
                    id="file-unknown-1",
                    name="chemical.txt",
                    url="/uploads/native/chemical.txt",
                    kind="file",
                )
            ],
        )
    )

    assert output.message_type == "task_action"
    assert output.action_state == "awaiting_clarification"
    assert output.clarification is not None
    assert "spec_code" in output.clarification.missing_fields
    assert "识别到的产品类别：`chemical`" in output.answer
