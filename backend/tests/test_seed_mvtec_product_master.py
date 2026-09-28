from pathlib import Path

from scripts.seed_mvtec_product_master import (
    PRODUCT_META,
    discover_categories,
)


def test_discover_mvtec_categories(tmp_path: Path):
    (tmp_path / "bottle" / "train" / "good").mkdir(parents=True)
    (tmp_path / "bottle" / "test" / "broken_large").mkdir(parents=True)
    (tmp_path / "bottle" / "test" / "good").mkdir(parents=True)
    (tmp_path / ".ignored").mkdir()

    assert discover_categories(tmp_path) == ["bottle"]


def test_mvtec_metadata_maps_dataset_category_to_product_category_and_product():
    category_code, category_name, product_name = PRODUCT_META["bottle"]
    assert category_code == "packaging"
    assert category_name == "包装容器"
    assert product_name == "瓶子"
