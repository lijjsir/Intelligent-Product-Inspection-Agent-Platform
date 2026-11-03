import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from build_qdl_sft_dataset import build_record, generate
from qdl_module import QDLConfig, QDLMatcher


class TestQDLDatasetBuilder(unittest.TestCase):
    def sample(self, score_fields=None):
        return {
            "id": "sample-1",
            "image": "images/sample.png",
            "category": "bottle",
            "split": "train",
            "ground_truth": {"has_defect": "Yes", "defect_category": "crack"},
            "text_structured": {
                "has_defect": "Yes", "risk_type": "surface_defect",
                "severity": "medium", "defect_category": "crack",
                "evidence_summary": "瓶口有裂纹",
            },
            "image_structured": {
                "has_defect": "Yes", "risk_type": "surface_defect",
                "severity": "medium", "defect_category": "crack",
                "evidence_summary": "可见裂纹", "bbox": [10, 10, 40, 40],
            },
        }

    def test_build_record_contains_audit_and_sft_fields(self):
        audit, sft = build_record(
            self.sample(), QDLMatcher(config=QDLConfig(llm_review=False)), 0.80, 0.55
        )
        self.assertIn("field_score_details", audit["qdl_result"])
        self.assertIn("audit", audit["qdl_result"])
        self.assertIn("conversations", sft)
        self.assertEqual(sft["conversations"][0]["value"].count("<image>"), 1)
        self.assertIn(audit["qdl_bucket"], {"high", "medium", "conflict"})

    def test_missing_image_structured_is_recorded_and_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "input.jsonl"
            input_path.write_text(json.dumps({"image": "x", "text_structured": {}}) + "\n", encoding="utf-8")
            stats = generate(input_path, root / "out", llm_review=False)
            self.assertEqual(stats["processed"], 0)
            errors = (root / "out" / "qdl_generation_errors.jsonl").read_text(encoding="utf-8")
            self.assertIn("image_structured", errors)

    def test_invalid_json_does_not_abort_following_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "input.jsonl"
            input_path.write_text("not json\n" + json.dumps(self.sample()) + "\n", encoding="utf-8")
            stats = generate(input_path, root / "out", llm_review=False)
            self.assertEqual(stats["processed"], 1)
            self.assertEqual(stats["errors"], 1)

    def test_threshold_arguments_create_expected_bucket_boundaries(self):
        # Use a matcher stub to exercise exact boundary behavior independently
        class StubMatcher:
            def __init__(self, score):
                self.score = score
            def match(self, **kwargs):
                return {
                    "alignment_score": self.score, "consistency_label": "supported",
                    "field_scores": {}, "field_score_details": {}, "audit": {},
                }
        from build_qdl_sft_dataset import build_record as make
        for score, expected in ((0.80, "high"), (0.55, "medium"), (0.54, "conflict")):
            audit, _ = make(self.sample(), StubMatcher(score), 0.80, 0.55)
            self.assertEqual(audit["qdl_bucket"], expected)

    def test_multiple_text_candidates_are_matched_and_audited(self):
        record = self.sample()
        second = dict(record["text_structured"], evidence_summary="检查发现瓶口存在裂纹", candidate_id="variant_1")
        record["text_structured_candidates"] = [record["text_structured"], second]
        audit, sft = build_record(
            record, QDLMatcher(config=QDLConfig(llm_review=False)), 0.80, 0.55
        )
        result = audit["qdl_result"]
        self.assertEqual(result["text_candidate_count"], 2)
        self.assertEqual(len(result["candidate_edges_by_text_candidate"]), 2)
        self.assertEqual(len(result["candidate_alignment_scores"]), 2)
        self.assertEqual(len(sft["text_structured_candidates"]), 2)

    def test_candidate_edge_limit_is_per_image_across_text_variants(self):
        record = self.sample()
        record["text_structured_candidates"] = [
            dict(record["text_structured"], candidate_id=f"variant_{index}")
            for index in range(4)
        ]
        audit, _ = build_record(
            record,
            QDLMatcher(config=QDLConfig(llm_review=False, max_candidates=None)),
            0.80,
            0.55,
            max_candidates_per_image=5,
        )
        self.assertEqual(audit["candidate_edge_count"], 5)
        self.assertEqual(audit["max_candidate_edges_per_image"], 5)

    def test_default_model_loader_supplies_embedder_and_reviewer(self):
        class Embedder:
            def encode(self, texts, normalize_embeddings=True):
                return [[1.0, 0.0] for _ in texts]

        def reviewer(_prompt):
            return {"relation": "supports", "score": 0.9}

        with tempfile.TemporaryDirectory() as directory, patch(
            "build_qdl_sft_dataset._load_default_models",
            return_value=(Embedder(), reviewer),
        ) as loader:
            input_path = Path(directory) / "input.jsonl"
            input_path.write_text(json.dumps(self.sample()) + "\n", encoding="utf-8")
            stats = generate(input_path, Path(directory) / "out")
            self.assertEqual(stats["processed"], 1)
            loader.assert_called_once()
            audit = json.loads(
                (Path(directory) / "out" / "qdl_train_all.jsonl").read_text(encoding="utf-8").splitlines()[0]
            )
            self.assertTrue(audit["qdl_result"]["audit"]["llm_review_used"])
            self.assertTrue(any(edge["decision_source"] == "llm_review"
                                for edge in audit["qdl_result"]["accepted_edges"]))

    def test_validation_and_test_are_audited_but_not_written_as_training(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "input.jsonl"
            rows = []
            for split in ("train", "validation", "test"):
                rows.append(dict(self.sample(), id=split, split=split))
            input_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            stats = generate(input_path, root / "out", llm_review=False)
            audits = [json.loads(line) for line in (root / "out" / "qdl_train_all.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(stats["processed"], 3)
            self.assertEqual({row["split"] for row in audits}, {"train", "validation", "test"})
            for bucket in ("high", "medium", "conflict"):
                train_rows = [json.loads(line) for line in (root / "out" / f"qdl_train_{bucket}.jsonl").read_text(encoding="utf-8").splitlines()]
                self.assertTrue(all(row["split"] == "train" for row in train_rows))


if __name__ == "__main__":
    unittest.main()
