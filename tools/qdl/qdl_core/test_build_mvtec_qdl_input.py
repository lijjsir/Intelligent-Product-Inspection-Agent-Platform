import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from build_mvtec_qdl_input import _resolve_pipeline_dir, build_input


class TestMVTecQDLInput(unittest.TestCase):
    def make_dataset(self, root: Path):
        category = root / "bottle"
        for defect in ("crack", "broken_large"):
            image_dir = category / "test" / defect
            mask_dir = category / "ground_truth" / defect
            image_dir.mkdir(parents=True)
            mask_dir.mkdir(parents=True)
            for i in range(6):
                name = f"{i:03d}.png"
                Image.new("RGB", (20, 20), (255, 255, 255)).save(image_dir / name)
                mask = Image.new("L", (20, 20), 0)
                mask.putpixel((2, 3), 255)
                mask.save(mask_dir / f"{i:03d}_mask.png")
        good_dir = category / "test" / "good"
        good_dir.mkdir(parents=True)
        Image.new("RGB", (20, 20), (255, 255, 255)).save(good_dir / "000.png")
        train_good = category / "train" / "good"
        train_good.mkdir(parents=True)
        for i in range(6):
            Image.new("RGB", (20, 20), (240, 240, 240)).save(train_good / f"train_{i:03d}.png")

    def test_builds_only_normal_train_good_and_creates_text_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_dataset(root)
            output = root / "input.jsonl"
            stats = build_input(root, output, ["bottle"], 42, 0.7, 0.15, None)
            rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(stats["total"], 6)
            self.assertTrue(all("/train/good/" in row["image"].replace("\\", "/") for row in rows))
            self.assertTrue(all(row["source_split"] == "official_train_good" for row in rows))
            self.assertTrue(all(row["ground_truth"]["has_defect"] == "No" for row in rows))
            self.assertTrue(all(row["split"] in {"train", "validation", "test"} for row in rows))
            self.assertEqual(len(rows[0]["text_structured_candidates"]), 4)
            self.assertEqual(rows[0]["text_structured"]["mapping_source"], "mvtec_template")

    def test_external_structured_text_has_priority(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_dataset(root)
            image = str((root / "bottle" / "train" / "good" / "train_000.png").resolve())
            external = root / "text.jsonl"
            external.write_text(json.dumps({"image": image, "text_structured": {"has_defect": "No", "defect_category": "none", "evidence_summary": "外部文本"}}, ensure_ascii=False) + "\n", encoding="utf-8")
            output = root / "input.jsonl"
            build_input(root, output, ["bottle"], 1, 0.7, 0.15, external)
            rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            row = next(r for r in rows if r["image"] == image)
            self.assertEqual(row["text_structured"]["defect_category"], "none")
            self.assertEqual(row["text_structured"]["evidence_summary"], "外部文本")

    def test_pipeline_directory_can_be_explicitly_resolved(self):
        with tempfile.TemporaryDirectory() as directory:
            pipeline_dir = Path(directory) / "test-code"
            pipeline_dir.mkdir()
            for filename in ("models.py", "utils.py", "structured_generation_module.py"):
                (pipeline_dir / filename).write_text("", encoding="utf-8")
            self.assertEqual(_resolve_pipeline_dir(pipeline_dir), pipeline_dir.resolve())


if __name__ == "__main__":
    unittest.main()
