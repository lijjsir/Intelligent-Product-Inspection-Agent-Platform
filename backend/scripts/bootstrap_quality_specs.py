from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

from sqlalchemy import desc, func, select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.ids import uuid7
from app.models.inspection_standard_library import InspectionStandardLibrary
from app.models.inspection_spec import InspectionSpec, InspectionSpecItem
from app.models.product import ProductLine, ProductSku
from app.models.task import InspectionTask
from infra.database.session import get_session, reset_async_engine_pool


def slugify(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", value.strip()).strip("-")
    return text.upper() or "GENERAL"


def build_spec_payload(*, org_id: str | None, spec_code: str, name: str, product_id: str | None, product_family: str) -> dict:
    required_views = ["front", "rear", "detail"]
    required_image_count = 1
    if product_family == "food":
        required_views = ["label", "packaging", "traceability"]
    elif product_family == "electronics":
        required_views = ["marking", "safety", "documents"]
    return {
        "id": str(uuid7()),
        "org_id": org_id,
        "spec_code": spec_code,
        "name": name,
        "version": "2026.1",
        "product_id": product_id,
        "product_family": product_family,
        "applicable_skus": [product_id] if product_id else [],
        "required_views": required_views,
        "required_image_count": required_image_count,
        "aggregation_rules": {
            "overall": "fail_if_any_critical_else_manual_when_unmapped",
            "max_minor_count": 2,
        },
        "ai_gate_rules": {
            "confidence": 0.72,
            "evidence": 0.5,
            "traceability": 0.5,
            "faithfulness": 0.85,
            "physical_hallucination": 0.2,
        },
        "manual_review_policies": {
            "missing_required_views": "manual_required",
            "unmapped_defect": "manual_required",
            "low_evidence": "manual_required",
        },
        "auto_pass_enabled": True,
        "is_active": True,
    }


def build_screw_spec_items(spec_row_id: str) -> list[dict]:
    return [
        {
            "id": str(uuid7()),
            "spec_row_id": spec_row_id,
            "defect_type": "crack",
            "severity": "critical",
            "disposition": "fail",
            "confidence_threshold": 0.45,
            "zone_name": "surface",
            "max_count": 1,
            "description": "Cracks are critical defects and immediately fail the inspection.",
        },
        {
            "id": str(uuid7()),
            "spec_row_id": spec_row_id,
            "defect_type": "surface_scratch",
            "severity": "major",
            "disposition": "fail",
            "confidence_threshold": 0.62,
            "zone_name": "surface",
            "max_count": 1,
            "description": "Significant surface scratches are rejected.",
        },
        {
            "id": str(uuid7()),
            "spec_row_id": spec_row_id,
            "defect_type": "stain",
            "severity": "minor",
            "disposition": "manual_required",
            "confidence_threshold": 0.55,
            "zone_name": "surface",
            "max_count": 2,
            "description": "Minor stains require manual review.",
        },
    ]


def build_food_spec_items(spec_row_id: str) -> list[dict]:
    return [
        {
            "id": str(uuid7()),
            "spec_row_id": spec_row_id,
            "defect_type": "food.label.additive_common_names_complete",
            "severity": "major",
            "disposition": "fail",
            "confidence_threshold": 0.70,
            "zone_name": "label",
            "max_count": 1,
            "description": "Food additives must use complete common names on the label.",
        },
        {
            "id": str(uuid7()),
            "spec_row_id": spec_row_id,
            "defect_type": "food.process.traceability_record",
            "severity": "major",
            "disposition": "fail",
            "confidence_threshold": 0.70,
            "zone_name": "process",
            "max_count": 1,
            "description": "Traceability process records are required.",
        },
        {
            "id": str(uuid7()),
            "spec_row_id": spec_row_id,
            "defect_type": "food.traceability.qr_code_required",
            "severity": "major",
            "disposition": "fail",
            "confidence_threshold": 0.70,
            "zone_name": "traceability",
            "max_count": 1,
            "description": "Traceability QR code is required.",
        },
        {
            "id": str(uuid7()),
            "spec_row_id": spec_row_id,
            "defect_type": "food.packaging.seal_integrity",
            "severity": "critical",
            "disposition": "fail",
            "confidence_threshold": 0.65,
            "zone_name": "packaging",
            "max_count": 1,
            "description": "Packaging seal integrity issues directly fail the inspection.",
        },
        {
            "id": str(uuid7()),
            "spec_row_id": spec_row_id,
            "defect_type": "food.packaging.leakage",
            "severity": "critical",
            "disposition": "fail",
            "confidence_threshold": 0.65,
            "zone_name": "packaging",
            "max_count": 1,
            "description": "Packaging leakage directly fails the inspection.",
        },
        {
            "id": str(uuid7()),
            "spec_row_id": spec_row_id,
            "defect_type": "food.microbiology.coliform_present",
            "severity": "critical",
            "disposition": "fail",
            "confidence_threshold": 0.70,
            "zone_name": "microbiology",
            "max_count": 1,
            "description": "Coliform should not be detected for the current food baseline.",
        },
        {
            "id": str(uuid7()),
            "spec_row_id": spec_row_id,
            "defect_type": "food.microbiology.salmonella_detected",
            "severity": "critical",
            "disposition": "fail",
            "confidence_threshold": 0.80,
            "zone_name": "microbiology",
            "max_count": 1,
            "description": "Salmonella detection directly fails the inspection.",
        },
    ]


def build_electronics_spec_items(spec_row_id: str) -> list[dict]:
    return [
        {
            "id": str(uuid7()),
            "spec_row_id": spec_row_id,
            "defect_type": "electronics.marking.rated_output_marked",
            "severity": "major",
            "disposition": "fail",
            "confidence_threshold": 0.70,
            "zone_name": "marking",
            "max_count": 1,
            "description": "Rated output marking is required for electronics products.",
        },
        {
            "id": str(uuid7()),
            "spec_row_id": spec_row_id,
            "defect_type": "electronics.marking.manufacturer_address_marked",
            "severity": "major",
            "disposition": "fail",
            "confidence_threshold": 0.70,
            "zone_name": "marking",
            "max_count": 1,
            "description": "Manufacturer address marking is required.",
        },
        {
            "id": str(uuid7()),
            "spec_row_id": spec_row_id,
            "defect_type": "electronics.marking.warning_marked",
            "severity": "major",
            "disposition": "fail",
            "confidence_threshold": 0.70,
            "zone_name": "marking",
            "max_count": 1,
            "description": "Safety warning marking is required.",
        },
        {
            "id": str(uuid7()),
            "spec_row_id": spec_row_id,
            "defect_type": "electronics.structure.socket_shutter_present",
            "severity": "critical",
            "disposition": "fail",
            "confidence_threshold": 0.70,
            "zone_name": "structure",
            "max_count": 1,
            "description": "Socket shutter protection is mandatory for this baseline.",
        },
        {
            "id": str(uuid7()),
            "spec_row_id": spec_row_id,
            "defect_type": "electronics.structure.sharp_edge",
            "severity": "critical",
            "disposition": "fail",
            "confidence_threshold": 0.70,
            "zone_name": "structure",
            "max_count": 1,
            "description": "Sharp enclosure edges directly fail the inspection.",
        },
        {
            "id": str(uuid7()),
            "spec_row_id": spec_row_id,
            "defect_type": "electronics.structure.fire_enclosure_material_grade",
            "severity": "critical",
            "disposition": "fail",
            "confidence_threshold": 0.70,
            "zone_name": "structure",
            "max_count": 1,
            "description": "Fire enclosure material grade must meet the baseline requirement.",
        },
        {
            "id": str(uuid7()),
            "spec_row_id": spec_row_id,
            "defect_type": "electronics.safety.ground_continuity_ohm",
            "severity": "critical",
            "disposition": "fail",
            "confidence_threshold": 0.75,
            "zone_name": "safety",
            "max_count": 1,
            "description": "Ground continuity resistance exceeds the allowed threshold.",
        },
        {
            "id": str(uuid7()),
            "spec_row_id": spec_row_id,
            "defect_type": "electronics.safety.electric_strength_kv",
            "severity": "critical",
            "disposition": "fail",
            "confidence_threshold": 0.75,
            "zone_name": "safety",
            "max_count": 1,
            "description": "Electric strength must meet the baseline withstand requirement.",
        },
        {
            "id": str(uuid7()),
            "spec_row_id": spec_row_id,
            "defect_type": "electronics.safety.temperature_rise_max_c",
            "severity": "major",
            "disposition": "fail",
            "confidence_threshold": 0.75,
            "zone_name": "safety",
            "max_count": 1,
            "description": "Temperature rise exceeds the allowed baseline.",
        },
        {
            "id": str(uuid7()),
            "spec_row_id": spec_row_id,
            "defect_type": "electronics.safety.creepage_distance_mm",
            "severity": "critical",
            "disposition": "fail",
            "confidence_threshold": 0.75,
            "zone_name": "safety",
            "max_count": 1,
            "description": "Creepage distance is below the baseline requirement.",
        },
        {
            "id": str(uuid7()),
            "spec_row_id": spec_row_id,
            "defect_type": "electronics.safety.clearance_mm",
            "severity": "critical",
            "disposition": "fail",
            "confidence_threshold": 0.75,
            "zone_name": "safety",
            "max_count": 1,
            "description": "Clearance distance is below the baseline requirement.",
        },
        {
            "id": str(uuid7()),
            "spec_row_id": spec_row_id,
            "defect_type": "electronics.emc.conducted_emission",
            "severity": "major",
            "disposition": "fail",
            "confidence_threshold": 0.70,
            "zone_name": "emc",
            "max_count": 1,
            "description": "Conducted emission must pass.",
        },
        {
            "id": str(uuid7()),
            "spec_row_id": spec_row_id,
            "defect_type": "electronics.emc.radiated_emission",
            "severity": "major",
            "disposition": "fail",
            "confidence_threshold": 0.70,
            "zone_name": "emc",
            "max_count": 1,
            "description": "Radiated emission must pass.",
        },
        {
            "id": str(uuid7()),
            "spec_row_id": spec_row_id,
            "defect_type": "electronics.emc.esd_immunity",
            "severity": "major",
            "disposition": "fail",
            "confidence_threshold": 0.70,
            "zone_name": "emc",
            "max_count": 1,
            "description": "ESD immunity must pass without function loss.",
        },
        {
            "id": str(uuid7()),
            "spec_row_id": spec_row_id,
            "defect_type": "electronics.emc.surge_immunity",
            "severity": "major",
            "disposition": "fail",
            "confidence_threshold": 0.70,
            "zone_name": "emc",
            "max_count": 1,
            "description": "Surge immunity must pass.",
        },
        {
            "id": str(uuid7()),
            "spec_row_id": spec_row_id,
            "defect_type": "electronics.emc.eft_immunity",
            "severity": "major",
            "disposition": "fail",
            "confidence_threshold": 0.70,
            "zone_name": "emc",
            "max_count": 1,
            "description": "EFT immunity must pass.",
        },
        {
            "id": str(uuid7()),
            "spec_row_id": spec_row_id,
            "defect_type": "electronics.documents.inspection_report",
            "severity": "major",
            "disposition": "fail",
            "confidence_threshold": 0.70,
            "zone_name": "documents",
            "max_count": 1,
            "description": "Inspection report is required.",
        },
        {
            "id": str(uuid7()),
            "spec_row_id": spec_row_id,
            "defect_type": "electronics.documents.certificate_file",
            "severity": "major",
            "disposition": "fail",
            "confidence_threshold": 0.70,
            "zone_name": "documents",
            "max_count": 1,
            "description": "Certificate file is required.",
        },
        {
            "id": str(uuid7()),
            "spec_row_id": spec_row_id,
            "defect_type": "electronics.documents.traceability_code",
            "severity": "major",
            "disposition": "fail",
            "confidence_threshold": 0.70,
            "zone_name": "documents",
            "max_count": 1,
            "description": "Traceability code is required.",
        },
        {
            "id": str(uuid7()),
            "spec_row_id": spec_row_id,
            "defect_type": "electronics.documents.ccc_file",
            "severity": "major",
            "disposition": "fail",
            "confidence_threshold": 0.70,
            "zone_name": "documents",
            "max_count": 1,
            "description": "CCC file is required.",
        },
        {
            "id": str(uuid7()),
            "spec_row_id": spec_row_id,
            "defect_type": "electronics.functional.usb_output_voltage_v",
            "severity": "major",
            "disposition": "fail",
            "confidence_threshold": 0.70,
            "zone_name": "functional",
            "max_count": 1,
            "description": "USB output voltage must remain within the baseline range.",
        },
    ]


def build_spec_items(spec_row_id: str, product_family: str) -> list[dict]:
    if product_family == "food":
        return build_food_spec_items(spec_row_id)
    if product_family == "electronics":
        return build_electronics_spec_items(spec_row_id)
    return build_screw_spec_items(spec_row_id)


def _spec_code_for_sku(sku_code: str) -> str:
    if slugify(sku_code) == "SCREW":
        return "SCREW-A-2026-V1"
    return f"AUTO-{slugify(sku_code)}-V1"


def _spec_name_for_sku(sku_name: str, sku_code: str) -> str:
    return f"{sku_name or sku_code} 质检门槛"


def _library_name_for_sku(sku_name: str, sku_code: str) -> str:
    return f"{sku_name or sku_code} 检测标准"


def _apply_sku_scope(spec: InspectionSpec, *, org_id: str, sku_code: str, sku_name: str) -> None:
    spec.org_id = org_id
    spec.name = _spec_name_for_sku(sku_name, sku_code)
    spec.product_id = sku_code
    spec.product_family = sku_code
    spec.applicable_skus = [sku_code]
    spec.is_active = True


async def resolve_top_product_ids(org_id: str | None, limit: int) -> list[str]:
    async with get_session() as session:
        stmt = (
            select(InspectionTask.product_id, func.count().label("task_count"))
            .where(InspectionTask.deleted_at.is_(None))
            .group_by(InspectionTask.product_id)
            .order_by(desc("task_count"))
            .limit(limit)
        )
        if org_id:
            stmt = stmt.where(InspectionTask.org_id == org_id)
        rows = (await session.execute(stmt)).all()
        return [str(row.product_id) for row in rows if row.product_id]


async def upsert_specs(org_id: str | None, product_ids: list[str]) -> dict:
    created_codes: list[str] = []
    skipped_codes: list[str] = []

    seed_specs = [
        build_spec_payload(
            org_id=org_id,
            spec_code="GLOBAL-QUALITY-BASE-2026",
            name="Global default quality baseline",
            product_id=None,
            product_family="global-default",
        ),
        build_spec_payload(
            org_id=org_id,
            spec_code="QS-009-EXAMPLE-2026",
            name="QS-009 document example baseline",
            product_id="example-product",
            product_family="document-example",
        ),
        build_spec_payload(
            org_id=org_id,
            spec_code="FOOD-RAG-BASE-V1",
            name="Food structured inspection baseline",
            product_id="food",
            product_family="food",
        ),
        build_spec_payload(
            org_id=org_id,
            spec_code="ELEC-RAG-BASE-V1",
            name="Electronics structured inspection baseline",
            product_id="electronics",
            product_family="electronics",
        ),
    ]
    for product_id in product_ids:
        seed_specs.append(
            build_spec_payload(
                org_id=org_id,
                spec_code=f"AUTO-{slugify(product_id)}-V1",
                name=f"Auto imported baseline - {product_id}",
                product_id=product_id,
                product_family=product_id,
            )
        )

    async with get_session() as session:
        for payload in seed_specs:
            stmt = select(InspectionSpec).where(
                InspectionSpec.spec_code == payload["spec_code"],
                InspectionSpec.deleted_at.is_(None),
            )
            if payload["org_id"] is None:
                stmt = stmt.where(InspectionSpec.org_id.is_(None))
            else:
                stmt = stmt.where(InspectionSpec.org_id == payload["org_id"])
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing:
                skipped_codes.append(payload["spec_code"])
                continue

            spec = InspectionSpec(**payload)
            session.add(spec)
            for item in build_spec_items(payload["id"], str(payload["product_family"])):
                session.add(InspectionSpecItem(**item))
            created_codes.append(payload["spec_code"])

        await session.commit()

    return {
        "org_id": org_id,
        "requested_products": product_ids,
        "created_spec_codes": created_codes,
        "skipped_spec_codes": skipped_codes,
    }


async def seed_specs_and_libraries_for_active_skus(org_id: str) -> dict:
    created_specs: list[str] = []
    updated_libraries: list[str] = []
    created_libraries: list[str] = []

    async with get_session() as session:
        sku_rows = (
            await session.execute(
                select(ProductSku, ProductLine)
                .join(ProductLine, ProductLine.id == ProductSku.product_line_id)
                .where(
                    ProductSku.org_id == org_id,
                    ProductSku.deleted_at.is_(None),
                    ProductSku.is_active.is_(True),
                    ProductLine.deleted_at.is_(None),
                    ProductLine.is_active.is_(True),
                )
                .order_by(ProductLine.code.asc(), ProductSku.code.asc())
            )
        ).all()
        library_rows = (
            await session.execute(
                select(InspectionStandardLibrary).where(
                    InspectionStandardLibrary.org_id == org_id,
                    InspectionStandardLibrary.deleted_at.is_(None),
                    InspectionStandardLibrary.applicable_product_sku_ids.is_not(None),
                )
            )
        ).scalars().all()

        for sku, line in sku_rows:
            spec_code = _spec_code_for_sku(str(sku.code))
            spec = (
                await session.execute(
                    select(InspectionSpec).where(
                        InspectionSpec.org_id == org_id,
                        InspectionSpec.spec_code == spec_code,
                        InspectionSpec.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if spec is None:
                spec = (
                    await session.execute(
                        select(InspectionSpec).where(
                            InspectionSpec.org_id.is_(None),
                            InspectionSpec.spec_code == spec_code,
                            InspectionSpec.deleted_at.is_(None),
                        )
                    )
                ).scalar_one_or_none()
            if spec is None:
                payload = build_spec_payload(
                    org_id=org_id,
                    spec_code=spec_code,
                    name=_spec_name_for_sku(str(sku.name), str(sku.code)),
                    product_id=str(sku.code),
                    product_family=str(sku.code),
                )
                spec = InspectionSpec(**payload)
                session.add(spec)
                for item in build_spec_items(payload["id"], str(sku.code)):
                    session.add(InspectionSpecItem(**item))
                created_specs.append(spec_code)
            else:
                _apply_sku_scope(spec, org_id=org_id, sku_code=str(sku.code), sku_name=str(sku.name))

            matched_library = next(
                (
                    item
                    for item in library_rows
                    if str(sku.id) in list(item.applicable_product_sku_ids or [])
                ),
                None,
            )
            if matched_library is None:
                matched_library = InspectionStandardLibrary(
                    id=str(uuid7()),
                    org_id=org_id,
                    name=_library_name_for_sku(str(sku.name), str(sku.code)),
                    product_family=str(sku.code),
                    inspection_spec_id=str(spec.id),
                    spec_code=str(spec.spec_code),
                    applicable_product_line_ids=[str(line.id)],
                    applicable_product_sku_ids=[str(sku.id)],
                    description=f"Auto-seeded standard binding for SKU {sku.code}.",
                    rag_space_ids=[],
                    domain=str(line.code),
                    product_category=str(sku.code),
                    file_glob="*.pdf",
                    chunk_strategy="heading_then_size",
                    standard_status="现行",
                    auto_reindex=False,
                    pdf_count=0,
                    document_count=0,
                    chunk_count=0,
                    import_status="not_scanned",
                    is_active=True,
                )
                session.add(matched_library)
                library_rows.append(matched_library)
                created_libraries.append(str(sku.code))
            else:
                matched_library.name = _library_name_for_sku(str(sku.name), str(sku.code))
                matched_library.product_family = str(sku.code)
                matched_library.inspection_spec_id = str(spec.id)
                matched_library.spec_code = str(spec.spec_code)
                matched_library.applicable_product_line_ids = [str(line.id)]
                matched_library.applicable_product_sku_ids = [str(sku.id)]
                matched_library.domain = str(line.code)
                matched_library.product_category = str(sku.code)
                matched_library.is_active = True
                updated_libraries.append(str(sku.code))

        await session.commit()

    return {
        "org_id": org_id,
        "created_specs": created_specs,
        "created_libraries": created_libraries,
        "updated_libraries": updated_libraries,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap multi-product quality specs")
    parser.add_argument("--org-id", default=None, help="Target org id. Omit to seed global defaults.")
    parser.add_argument("--top-products", type=int, default=5, help="Number of top product_ids to bootstrap")
    parser.add_argument("--active-skus", action="store_true", help="Seed one spec and one standard binding for each active SKU in the org.")
    args = parser.parse_args()

    if args.active_skus:
        if not args.org_id:
            raise ValueError("--org-id is required when using --active-skus")
        result = await seed_specs_and_libraries_for_active_skus(args.org_id)
    else:
        product_ids = await resolve_top_product_ids(args.org_id, args.top_products)
        result = await upsert_specs(args.org_id, product_ids)
    print(json.dumps(result, ensure_ascii=False))


async def _run_cli() -> None:
    try:
        await main()
    finally:
        await reset_async_engine_pool()


if __name__ == "__main__":
    asyncio.run(_run_cli())
