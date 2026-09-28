"""Seed MVTec categories as v4 product categories and concrete products."""

# ruff: noqa: E402 - the executable script must add the backend root before app imports.

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.quality_risk import ProductCategory, QualityProduct
from app.repositories.organization_repo import OrganizationRepository
from infra.database.session import create_session, reset_async_engine_pool

DEFAULT_DATASET_DIR = Path(r"D:\dataset\mvtec_anomaly_detection")
DEFAULT_ORG_SLUG = "cqupt"

PRODUCT_META: dict[str, tuple[str, str, str]] = {
    "bottle": ("packaging", "包装容器", "瓶子"),
    "cable": ("industrial-parts", "工业零部件", "电缆"),
    "capsule": ("pharma-daily", "医药日用品", "胶囊"),
    "carpet": ("texture-surfaces", "纹理表面", "地毯"),
    "grid": ("texture-surfaces", "纹理表面", "网格"),
    "hazelnut": ("food", "食品原料", "榛子"),
    "leather": ("texture-surfaces", "纹理表面", "皮革"),
    "metal_nut": ("industrial-parts", "工业零部件", "金属螺母"),
    "pill": ("pharma-daily", "医药日用品", "药片"),
    "screw": ("industrial-parts", "工业零部件", "螺丝"),
    "tile": ("texture-surfaces", "纹理表面", "瓷砖"),
    "toothbrush": ("pharma-daily", "医药日用品", "牙刷"),
    "transistor": ("electronics", "电子元件", "晶体管"),
    "wood": ("texture-surfaces", "纹理表面", "木材"),
    "zipper": ("pharma-daily", "医药日用品", "拉链"),
}


def discover_categories(dataset_dir: Path) -> list[str]:
    if not dataset_dir.exists():
        raise FileNotFoundError(f"MVTec 数据集目录不存在：{dataset_dir}")
    return sorted(
        item.name
        for item in dataset_dir.iterdir()
        if item.is_dir() and not item.name.startswith(".")
    )


async def seed_mvtec_product_master(
    *, org_slug: str, dataset_dir: Path, dry_run: bool = False
) -> dict[str, int]:
    session = create_session()
    try:
        org = await OrganizationRepository(session).get_by_slug(org_slug)
        if org is None:
            rows = await OrganizationRepository(session).list_all()
            available = ", ".join(item.slug for item, _count in rows) or "无"
            raise ValueError(f"找不到组织 slug：{org_slug}。可用组织 slug：{available}")
        stats = {
            "categories_seen": 0,
            "categories_created": 0,
            "categories_updated": 0,
            "products_created": 0,
            "products_updated": 0,
        }
        category_cache: dict[str, ProductCategory] = {}
        for dataset_category in discover_categories(dataset_dir):
            stats["categories_seen"] += 1
            category_code, category_name, product_name = PRODUCT_META.get(
                dataset_category,
                ("mvtec-other", "其他 MVTec 产品", dataset_category.replace("_", " ")),
            )
            category = category_cache.get(category_code) or await session.scalar(
                select(ProductCategory).where(
                    ProductCategory.org_id == str(org.id),
                    ProductCategory.code == category_code,
                    ProductCategory.deleted_at.is_(None),
                )
            )
            if category is None:
                category = ProductCategory(
                    org_id=str(org.id),
                    code=category_code,
                    name=category_name,
                    description="MVTec AD 数据类别",
                    is_active=True,
                )
                session.add(category)
                await session.flush()
                stats["categories_created"] += 1
            elif category.name != category_name or not category.is_active:
                category.name = category_name
                category.is_active = True
                stats["categories_updated"] += 1
            category_cache[category_code] = category

            product = await session.scalar(
                select(QualityProduct).where(
                    QualityProduct.org_id == str(org.id),
                    QualityProduct.category_id == category.id,
                    QualityProduct.model == dataset_category,
                    QualityProduct.deleted_at.is_(None),
                )
            )
            if product is None:
                session.add(
                    QualityProduct(
                        org_id=str(org.id),
                        category_id=category.id,
                        name=product_name,
                        model=dataset_category,
                        brand="MVTec AD",
                        attributes={"dataset": "mvtec_ad"},
                        is_active=True,
                    )
                )
                stats["products_created"] += 1
            elif product.name != product_name or not product.is_active:
                product.name = product_name
                product.is_active = True
                stats["products_updated"] += 1

        if dry_run:
            await session.rollback()
        else:
            await session.commit()
        return stats
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="将 MVTec AD 目录登记为产品类别与具体产品。")
    parser.add_argument("--org-slug", default=DEFAULT_ORG_SLUG)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET_DIR)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    try:
        stats = await seed_mvtec_product_master(
            org_slug=args.org_slug, dataset_dir=args.dataset_dir, dry_run=args.dry_run
        )
        mode = "预演完成" if args.dry_run else "导入完成"
        print(
            f"{mode}：识别目录 {stats['categories_seen']} 个，"
            f"新增类别 {stats['categories_created']} 条，更新类别 {stats['categories_updated']} 条，"
            f"新增具体产品 {stats['products_created']} 条，更新具体产品 {stats['products_updated']} 条。"
        )
    finally:
        await reset_async_engine_pool()


if __name__ == "__main__":
    asyncio.run(main())
