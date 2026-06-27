from pathlib import Path

from scripts.seed_mvtec_product_master import (
    discover_categories,
)
from app.services.product_master_service import UNSPECIFIED_BATCH_NAME, UNSPECIFIED_BATCH_NO


def test_discover_mvtec_categories(tmp_path: Path):
    (tmp_path / "bottle" / "train" / "good").mkdir(parents=True)
    (tmp_path / "bottle" / "test" / "broken_large").mkdir(parents=True)
    (tmp_path / "bottle" / "test" / "good").mkdir(parents=True)
    (tmp_path / ".ignored").mkdir()

    assert discover_categories(tmp_path) == ["bottle"]


def test_dataset_batches_use_unspecified_default():
    assert UNSPECIFIED_BATCH_NO == "UNSPECIFIED"
    assert UNSPECIFIED_BATCH_NAME == "未指定批次"
