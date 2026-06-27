from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys

from sqlalchemy import func, select


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.product import ProductBatch, ProductLine, ProductSku
from app.repositories.organization_repo import OrganizationRepository
from app.repositories.product_master_repo import ProductMasterRepository
from app.services.product_master_service import UNSPECIFIED_BATCH_NAME, UNSPECIFIED_BATCH_NO
from infra.database.session import create_session, reset_async_engine_pool


DEFAULT_DATASET_DIR = Path(r"D:\dataset\mvtec_anomaly_detection")
DEFAULT_ORG_SLUG = "cqupt"
LEGACY_PRODUCT_DESCRIPTION = "由历史检测任务的产品编号自动创建。"
LEGACY_BATCH_DESCRIPTION = "为没有批次号的历史任务自动创建的兼容批次。"

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

LEGACY_LINE_CODE_RENAMES: dict[str, str] = {
    "mvtec-electronics": "electronics",
    "mvtec-food": "food",
    "mvtec-industrial-parts": "industrial-parts",
    "mvtec-packaging": "packaging",
    "mvtec-pharma-daily": "pharma-daily",
    "mvtec-texture-surfaces": "texture-surfaces",
}

DEFECT_NAME_ZH: dict[str, str] = {
    "bent": "弯曲",
    "bent_lead": "引脚弯曲",
    "broken": "破损",
    "broken_large": "大面积破损",
    "broken_small": "小面积破损",
    "color": "颜色异常",
    "combined": "复合缺陷",
    "contamination": "污染",
    "crack": "裂纹",
    "cut": "切口",
    "cut_inner_insulation": "内绝缘层切口",
    "cut_lead": "引脚切断",
    "cut_outer_insulation": "外绝缘层切口",
    "damaged_case": "外壳损伤",
    "faulty_imprint": "印字异常",
    "flip": "翻转",
    "fold": "折痕",
    "glue": "胶痕",
    "good": "良品",
    "hole": "孔洞",
    "liquid": "液体污染",
    "manipulated_front": "正面篡改",
    "metal_contamination": "金属污染",
    "misplaced": "位置偏移",
    "missing_cable": "线缆缺失",
    "missing_hole": "孔位缺失",
    "missing_wire": "导线缺失",
    "poke": "戳孔",
    "scratch": "划痕",
    "scratch_head": "头部划痕",
    "scratch_neck": "颈部划痕",
    "squeeze": "挤压变形",
    "thread": "线头",
    "thread_side": "侧面螺纹异常",
    "thread_top": "顶部螺纹异常",
}


def normalize_code(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def batch_no(split: str, defect: str) -> str:
    return f"{split}-{defect}".upper().replace("_", "-")


def defect_label(defect: str) -> str:
    return DEFECT_NAME_ZH.get(defect, defect.replace("_", " "))


def batch_name(split: str, defect: str) -> str:
    split_name = "训练集" if split == "train" else "测试集"
    return f"{split_name} - {defect_label(defect)}"


def discover_categories(dataset_dir: Path) -> list[str]:
    if not dataset_dir.exists():
        raise FileNotFoundError(f"MVTec 数据集目录不存在：{dataset_dir}")
    return sorted(
        item.name
        for item in dataset_dir.iterdir()
        if item.is_dir() and not item.name.startswith(".")
    )


async def get_or_create_line(
    repo: ProductMasterRepository,
    *,
    org_id: str,
    code: str,
    name: str,
    dry_run: bool,
    stats: dict[str, int],
) -> ProductLine:
    line = await repo.get_line_by_code(org_id, code)
    legacy_line = None
    for old_code, new_code in LEGACY_LINE_CODE_RENAMES.items():
        if new_code == code:
            legacy_line = await repo.get_line_by_code(org_id, old_code)
            break
    if line is None and legacy_line is not None:
        line = legacy_line
        line_patch = {"code": code}
        if line.name != name:
            line_patch["name"] = name
        if line.description:
            line_patch["description"] = None
        if not line.is_active:
            line_patch["is_active"] = True
        if not dry_run:
            line = await repo.update(line, line_patch)
        stats["lines_updated"] += 1
        return line

    if line is None:
        line = ProductLine(
            org_id=org_id,
            code=code,
            name=name,
            description=None,
            is_active=True,
        )
        if not dry_run:
            line = await repo.create_line(line)
        stats["lines_created"] += 1
        return line

    line_patch = {}
    if line.name != name:
        line_patch["name"] = name
    if line.description:
        line_patch["description"] = None
    if not line.is_active:
        line_patch["is_active"] = True
    if line_patch:
        if not dry_run:
            line = await repo.update(line, line_patch)
        stats["lines_updated"] += 1
    return line


async def seed_mvtec_product_master(
    *,
    org_slug: str,
    dataset_dir: Path,
    dry_run: bool = False,
) -> dict[str, int]:
    session = create_session()
    try:
        org = await OrganizationRepository(session).get_by_slug(org_slug)
        if org is None:
            rows = await OrganizationRepository(session).list_all()
            available = ", ".join(org.slug for org, _count in rows) or "无"
            raise ValueError(f"找不到组织 slug：{org_slug}。可用组织 slug：{available}")

        repo = ProductMasterRepository(session)
        stats = {
            "lines_created": 0,
            "lines_updated": 0,
            "legacy_lines_deleted": 0,
            "skus_created": 0,
            "skus_updated": 0,
            "batches_created": 0,
            "batches_updated": 0,
            "categories_seen": 0,
        }
        line_cache: dict[str, ProductLine] = {}

        for category in discover_categories(dataset_dir):
            stats["categories_seen"] += 1
            line_code, line_name, sku_name = PRODUCT_META.get(
                category,
                ("mvtec-other", "其他 MVTec 产品", category.replace("_", " ")),
            )
            line = line_cache.get(line_code) or await get_or_create_line(
                repo,
                org_id=str(org.id),
                code=line_code,
                name=line_name,
                dry_run=dry_run,
                stats=stats,
            )
            line_cache[line_code] = line

            sku = await repo.get_sku_by_code(str(org.id), category)
            if sku is None:
                sku = ProductSku(
                    org_id=str(org.id),
                    product_line_id=str(line.id),
                    code=category,
                    name=sku_name,
                    description=None,
                    is_active=True,
                )
                if not dry_run:
                    sku = await repo.create_sku(sku)
                stats["skus_created"] += 1
            else:
                sku_patch = {}
                if str(sku.product_line_id) != str(line.id):
                    sku_patch["product_line_id"] = str(line.id)
                if sku.name != sku_name:
                    sku_patch["name"] = sku_name
                if sku.description:
                    sku_patch["description"] = None
                if not sku.is_active:
                    sku_patch["is_active"] = True
                if sku_patch:
                    if not dry_run:
                        sku = await repo.update(sku, sku_patch)
                    stats["skus_updated"] += 1

            existing_batches = [
                item
                for item in await repo.list_batches(str(org.id))
                if str(item.product_sku_id) == str(sku.id)
            ]
            unspecified_batch = next(
                (item for item in existing_batches if str(item.batch_no).strip().upper() == UNSPECIFIED_BATCH_NO),
                None,
            )
            if unspecified_batch is None:
                if not dry_run:
                    await repo.create_batch(
                        ProductBatch(
                            org_id=str(org.id),
                            product_sku_id=str(sku.id),
                            batch_no=UNSPECIFIED_BATCH_NO,
                            name=UNSPECIFIED_BATCH_NAME,
                            description=None,
                            is_active=True,
                        )
                    )
                stats["batches_created"] += 1
            else:
                batch_patch = {}
                if unspecified_batch.name != UNSPECIFIED_BATCH_NAME:
                    batch_patch["name"] = UNSPECIFIED_BATCH_NAME
                if unspecified_batch.description:
                    batch_patch["description"] = None
                if not unspecified_batch.is_active:
                    batch_patch["is_active"] = True
                if batch_patch:
                    if not dry_run:
                        await repo.update(unspecified_batch, batch_patch)
                    stats["batches_updated"] += 1

            for batch in existing_batches:
                if str(batch.batch_no).strip().upper() == UNSPECIFIED_BATCH_NO:
                    continue
                if not dry_run:
                    await repo.soft_delete(batch)
                stats["batches_updated"] += 1

        for category in discover_categories(dataset_dir):
            if category not in PRODUCT_META:
                continue
            legacy_line = await repo.get_line_by_code(str(org.id), category)
            if legacy_line is None:
                continue
            sku_total = await session.scalar(
                select(func.count())
                .select_from(ProductSku)
                .where(
                    ProductSku.org_id == str(org.id),
                    ProductSku.product_line_id == str(legacy_line.id),
                    ProductSku.deleted_at.is_(None),
                )
            )
            if int(sku_total or 0) == 0:
                if not dry_run:
                    await repo.soft_delete(legacy_line)
                stats["legacy_lines_deleted"] += 1

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
    parser = argparse.ArgumentParser(description="补充 MVTec AD 数据集的产品线、SKU 和批次主数据。")
    parser.add_argument("--org-slug", default=DEFAULT_ORG_SLUG, help=f"目标组织 slug，默认：{DEFAULT_ORG_SLUG}")
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET_DIR, help=f"MVTec AD 数据集目录，默认：{DEFAULT_DATASET_DIR}")
    parser.add_argument("--dry-run", action="store_true", help="只统计将创建的数据，不提交数据库")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    try:
        stats = await seed_mvtec_product_master(
            org_slug=args.org_slug,
            dataset_dir=args.dataset_dir,
            dry_run=args.dry_run,
        )
        mode = "预演完成" if args.dry_run else "导入完成"
        print(
            f"{mode}：识别类别 {stats['categories_seen']} 个，"
            f"新增产品线 {stats['lines_created']} 条，"
            f"更新产品线 {stats['lines_updated']} 条，"
            f"清理旧产品线 {stats['legacy_lines_deleted']} 条，"
            f"新增 SKU {stats['skus_created']} 条，"
            f"更新 SKU {stats['skus_updated']} 条，"
            f"新增批次 {stats['batches_created']} 条，"
            f"更新批次 {stats['batches_updated']} 条。"
        )
    finally:
        await reset_async_engine_pool()


if __name__ == "__main__":
    asyncio.run(main())
