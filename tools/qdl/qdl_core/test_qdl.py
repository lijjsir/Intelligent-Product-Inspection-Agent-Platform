import json
import ast
import unittest
from pathlib import Path
from typing import Optional

try:
    from .knowledge_mapping import transform_retrieved_doc
    from .defect_ontology import infer_semantic_profile, semantic_profile_score
    from .qdl_module import QDLMatcher, QDLConfig, calibrate_qdl_weights
except ImportError:
    from knowledge_mapping import transform_retrieved_doc
    from defect_ontology import infer_semantic_profile, semantic_profile_score
    from qdl_module import QDLMatcher, QDLConfig, calibrate_qdl_weights


class TestKnowledgeMapping(unittest.TestCase):
    def test_dataset_mapping_keeps_source_label(self):
        result = transform_retrieved_doc({
            "category": "bottle", "defect_type": "broken_large",
            "defect_desc": "瓶身出现较大破损", "criteria": "可见断裂边缘",
        })
        self.assertEqual(result["source_defect_type"], "broken_large")
        self.assertEqual(result["defect_category"], "broken")
        self.assertEqual(result["risk_type"], "structural_damage")

    def test_fine_grained_mapping_preserves_thread_side(self):
        result = transform_retrieved_doc({
            "category": "screw", "defect_type": "thread_side",
            "defect_desc": "侧面螺纹发生形变",
        })
        self.assertEqual(result["defect_category"], "surface_damage")
        self.assertEqual(result["defect_subtype"], "thread_side")
        self.assertEqual(result["component"], "side_thread")
        self.assertEqual(result["morphology"], "thread_deformation")
        self.assertEqual(result["risk_type"], "structural_damage")

    def test_hierarchical_scoring_levels(self):
        left = infer_semantic_profile("scratch_neck")
        exact = infer_semantic_profile("scratch_neck")
        same_category_component = dict(exact, defect_subtype="another_neck_scratch")
        category_only = infer_semantic_profile("scratch")
        family_only = infer_semantic_profile("crack")
        conflict = infer_semantic_profile("broken")
        self.assertEqual(semantic_profile_score(left, exact), (1.0, "subtype_and_component"))
        self.assertEqual(semantic_profile_score(left, same_category_component), (0.9, "category_and_component"))
        self.assertEqual(semantic_profile_score(left, category_only), (0.75, "category"))
        self.assertEqual(semantic_profile_score(left, family_only), (0.55, "family"))
        self.assertEqual(semantic_profile_score(left, conflict), (0.1, "semantic_conflict"))


class TestQDL(unittest.TestCase):
    def setUp(self):
        self.text = {
            "has_defect": "Yes", "risk_type": "surface_defect", "severity": "medium",
            "defect_category": "crack", "location_hint": "瓶口区域",
            "evidence_summary": "瓶口区域有连续裂纹", "emotion_label": "neutral",
            "emotion_intensity": 0.0,
        }
        self.image = {
            "has_defect": "Yes", "risk_type": "surface_defect", "severity": "medium",
            "defect_category": "crack", "location_hint": "瓶口附近",
            "evidence_summary": "可见连续裂纹", "bbox": [100, 100, 400, 400],
        }

    def test_many_to_many_edges_exist(self):
        result = QDLMatcher(config=QDLConfig(llm_review=False)).match(self.text, self.image, category="bottle")
        self.assertGreaterEqual(len(result["accepted_edges"]), 3)
        self.assertIn("evidence_summary", result["relation_matrix"])
        self.assertIn("defect_category", result["relation_matrix"]["evidence_summary"])
        self.assertGreater(result["alignment_score"], 0.4)
        self.assertIn("semantic_profiles", result)
        self.assertTrue(any(node["source"] == "derived_semantic_profile" for node in result["nodes"]))
        self.assertEqual(result["probability_calibration"]["reason"], "temperature_not_fitted")

    def test_candidate_limit_defaults_to_128(self):
        self.assertEqual(QDLConfig().max_candidates, 128)

    def test_semantic_profile_repairs_missing_risk_for_matching_only(self):
        image = dict(self.image, risk_type="none", defect_category="scratch_neck", location_hint="颈部")
        result = QDLMatcher(config=QDLConfig(llm_review=False)).match(
            self.text, image, category="screw"
        )
        self.assertEqual(result["semantic_profiles"]["image"]["defect_subtype"], "scratch_neck")
        self.assertEqual(result["audit"]["semantic_repairs"]["image"]["risk_type"]["to"], "surface_defect")
        self.assertEqual(image["risk_type"], "none")

    def test_temperature_interface_applies_only_with_logits(self):
        image = dict(self.image, yes_logit=2.0, no_logit=0.0)
        result = QDLMatcher(config=QDLConfig(
            llm_review=False, probability_temperature=2.0,
        )).match(self.text, image)
        calibration = result["probability_calibration"]
        self.assertTrue(calibration["applied"])
        self.assertAlmostEqual(calibration["calibrated_yes_probability"], 0.7310585, places=5)

    def test_testcode_risk_inference_no_longer_returns_none_early(self):
        # Load only the dependency-free function body; importing the complete
        # Kaggle generation module locally would require torch/transformers.
        source_path = Path(__file__).resolve().parent / "structured_generation_module.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        function = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_infer_image_risk_type"
        )
        namespace = {
            "Optional": Optional,
            "normalize_risk_type": lambda value: "none",
            "normalize_defect_category": lambda category, value: "surface_damage",
            "RISK_TYPE_ENUM": [
                "appearance_abnormality", "structural_damage", "surface_defect",
                "deformation", "contamination", "safety_risk", "quality_defect", "none",
            ],
            "_IMAGE_DEFECT_TO_RISK_TYPE": {"surface_damage": "surface_defect"},
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source_path), "exec"), namespace)
        value = namespace["_infer_image_risk_type"](
            "screw", "none", "thread_side", "侧面螺纹发生形变"
        )
        self.assertEqual(value, "surface_defect")

    def test_llm_reviewer_is_injected_and_parsed(self):
        calls = []
        def reviewer(prompt):
            calls.append(json.loads(prompt))
            return {"relation": "supports", "score": 0.91, "reason": "语义支持"}
        result = QDLMatcher(llm_reviewer=reviewer).match(self.text, self.image, use_llm_review=True)
        self.assertTrue(calls)
        self.assertTrue(result["audit"]["llm_review_used"])
        self.assertTrue(any(edge["decision_source"] == "llm_review" for edge in result["accepted_edges"]))

    def test_field_score_details_separate_support_conflict_and_unknown(self):
        result = QDLMatcher(config=QDLConfig(llm_review=False)).match(
            {"has_defect": "Unknown", "defect_category": "unknown"},
            {"has_defect": "Unknown", "defect_category": "unknown"},
        )
        self.assertIn("positive_score", result["field_score_details"]["defect_category"])
        self.assertEqual(result["field_score_details"]["defect_category"]["status"], "unknown")

    def test_specialized_bbox_region_score_is_audited(self):
        result = QDLMatcher(config=QDLConfig(llm_review=False, max_candidates=None)).match(
            {"has_defect": "Yes", "location_hint": "左上角"},
            {"has_defect": "Yes", "bbox": [0.05, 0.05, 0.20, 0.20]},
        )
        edge = next(e for e in result["candidate_edges"] if e["image_field"] == "bbox")
        self.assertEqual(edge["specialized_match_type"], "region_bbox")
        self.assertEqual(len(result["candidate_edges"]), result["audit"]["candidate_pool_count"])

    def test_contradiction_reduces_score(self):
        image = dict(self.image, has_defect="No", defect_category="none", risk_type="none")
        result = QDLMatcher(config=QDLConfig(llm_review=False)).match(self.text, image)
        self.assertLess(result["field_scores"]["has_defect"], 1.0)
        self.assertIn(result["consistency_label"], {"partial", "not_supported"})
        presence_edge = next(
            edge for edge in result["candidate_edges"]
            if edge["text_field"] == edge["image_field"] == "has_defect"
        )
        self.assertIn("critical_same_field", presence_edge["candidate_selection_reasons"])

    def test_calibration_returns_normalized_weights(self):
        records = [
            {"field_scores": {"has_defect": 1, "defect_category": 1, "evidence_summary": 1}, "label": "supported"},
            {"field_scores": {"has_defect": 0, "defect_category": 0, "evidence_summary": 0}, "label": "not_supported"},
        ]
        result = calibrate_qdl_weights(records)
        self.assertAlmostEqual(sum(result["weights"].values()), 1.0, places=6)

if __name__ == "__main__":
    unittest.main()
