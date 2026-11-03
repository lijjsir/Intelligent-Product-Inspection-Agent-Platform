from __future__ import annotations

import json
import importlib.util
import tempfile
import unittest
from pathlib import Path

from build_qdl_train_manifest import build_manifest

_selection_path = (
    Path(__file__).resolve().parent / "qdl_selection.py"
)
_selection_spec = importlib.util.spec_from_file_location("qdl_selection", _selection_path)
_selection_module = importlib.util.module_from_spec(_selection_spec)
_selection_spec.loader.exec_module(_selection_module)
image_key = _selection_module.image_key
load_qdl_image_manifest = _selection_module.load_qdl_image_manifest
validate_manifest_coverage = _selection_module.validate_manifest_coverage


class QDLTrainManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.audit = self.root / "audit.jsonl"
        self.output = self.root / "manifest.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def _sample(self, category: str, filename: str, bucket: str, split: str = "train"):
        image = self.root / category / "train" / "good" / filename
        image.parent.mkdir(parents=True, exist_ok=True)
        image.touch()
        return {
            "id": f"{category}/{filename}",
            "image": str(image),
            "category": category,
            "split": split,
            "defect_type": "good",
            "ground_truth": {"has_defect": "No"},
            "qdl_bucket": bucket,
            "candidate_edge_count": 8,
            "qdl_result": {"accepted_edges": [{"relation": "equivalent"}]},
        }

    def _write_rows(self, rows):
        self.audit.write_text(
            "\n".join(json.dumps(row) for row in rows) + "\n",
            encoding="utf-8",
        )

    def test_qdl_high_and_random_matched_are_equal_and_disjoint(self):
        rows = [
            self._sample("bottle", "high_1.png", "high"),
            self._sample("bottle", "high_2.png", "high"),
            self._sample("bottle", "other_1.png", "medium"),
            self._sample("bottle", "other_2.png", "conflict"),
            self._sample("cable", "high_1.png", "high"),
            self._sample("cable", "other_1.png", "medium"),
            self._sample("cable", "other_2.png", "conflict"),
            self._sample("cable", "validation.png", "high", split="validation"),
        ]
        self._write_rows(rows)

        high = build_manifest(self.audit, self.root, self.output, "qdl_high")
        high_images = set(high["selected_images"])
        random_manifest = build_manifest(
            self.audit, self.root, self.output, "random_matched", seed=17
        )
        random_images = set(random_manifest["selected_images"])

        self.assertEqual(len(high_images), 3)
        self.assertEqual(len(random_images), len(high_images))
        self.assertTrue(high_images.isdisjoint(random_images))
        self.assertEqual(high["category_counts"], random_manifest["category_counts"])
        self.assertEqual(random_manifest["qdl_edge_counts"], {"candidate": 24, "accepted": 3})

    def test_test_path_is_rejected_even_when_marked_train(self):
        image = self.root / "bottle" / "test" / "good" / "leaked.png"
        image.parent.mkdir(parents=True)
        image.touch()
        self._write_rows([{
            "id": "leak",
            "image": str(image),
            "category": "bottle",
            "split": "train",
            "ground_truth": {"has_defect": "No"},
            "qdl_bucket": "high",
        }])

        with self.assertRaisesRegex(ValueError, "test image"):
            build_manifest(self.audit, self.root, self.output, "qdl_high")

    def test_anomalous_source_is_rejected_for_unsupervised_training(self):
        row = self._sample("bottle", "bad.png", "high")
        row["ground_truth"] = {"has_defect": "Yes"}
        row["defect_type"] = "crack"
        self._write_rows([row])

        with self.assertRaisesRegex(ValueError, "anomalous"):
            build_manifest(self.audit, self.root, self.output, "qdl_high")

    def test_manifest_loader_checks_schema_and_coverage(self):
        row = self._sample("bottle", "selected.png", "high")
        self._write_rows([row])
        manifest = build_manifest(self.audit, self.root, self.output, "qdl_high")
        selected = load_qdl_image_manifest(str(self.output))

        self.assertEqual(selected, {image_key(manifest["selected_images"][0])})
        validate_manifest_coverage(selected, selected, "MVTec")
        with self.assertRaisesRegex(ValueError, "not eligible"):
            validate_manifest_coverage(selected, set(), "MVTec")


if __name__ == "__main__":
    unittest.main()
