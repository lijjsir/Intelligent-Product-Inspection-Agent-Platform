from pathlib import Path

from scripts.seed_mvtec_product_master import (
    batch_name,
    batch_no,
    discover_batches,
    discover_categories,
)


def test_discover_mvtec_categories_and_batches(tmp_path: Path):
    (tmp_path / "bottle" / "train" / "good").mkdir(parents=True)
    (tmp_path / "bottle" / "test" / "broken_large").mkdir(parents=True)
    (tmp_path / "bottle" / "test" / "good").mkdir(parents=True)
    (tmp_path / ".ignored").mkdir()

    assert discover_categories(tmp_path) == ["bottle"]
    assert discover_batches(tmp_path, "bottle") == [
        ("test", "broken_large"),
        ("test", "good"),
        ("train", "good"),
    ]


def test_batch_labels_are_dataset_traceable_and_readable():
    assert batch_no("test", "broken_large") == "TEST-BROKEN-LARGE"
    assert batch_name("test", "broken_large") == "测试集 - 大面积破损"
    assert batch_name("train", "good") == "训练集 - 良品"
