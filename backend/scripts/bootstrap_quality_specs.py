from __future__ import annotations

import argparse
import asyncio
import json
import re

from sqlalchemy import desc, func, select

from app.core.ids import uuid7
from app.models.inspection_spec import InspectionSpec, InspectionSpecItem
from app.models.task import InspectionTask
from infra.database.session import get_session


def slugify(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", value.strip()).strip("-")
    return text.upper() or "GENERAL"


def build_spec_payload(*, org_id: str | None, spec_code: str, name: str, product_id: str | None, product_family: str) -> dict:
    required_views = ["front", "rear", "detail"]
    required_image_count = 3
    if product_family == "food":
        required_views = ["label", "packaging", "traceability"]
        required_image_count = 1
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
        "auto_pass_enabled": False,
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


def build_spec_items(spec_row_id: str, product_family: str) -> list[dict]:
    if product_family == "food":
        return build_food_spec_items(spec_row_id)
    return build_screw_spec_items(spec_row_id)


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


async def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap multi-product quality specs")
    parser.add_argument("--org-id", default=None, help="Target org id. Omit to seed global defaults.")
    parser.add_argument("--top-products", type=int, default=5, help="Number of top product_ids to bootstrap")
    args = parser.parse_args()

    product_ids = await resolve_top_product_ids(args.org_id, args.top_products)
    result = await upsert_specs(args.org_id, product_ids)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
