from __future__ import annotations

import re
from typing import Any


def slugify_standard_key(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", str(value or "").strip()).strip("-")
    return text.upper() or "GENERAL"


def standard_library_spec_code(product_family: str) -> str:
    return f"STD-{slugify_standard_key(product_family)}-V1"


def standard_library_spec_name(domain: str | None, product_family: str) -> str:
    label = str(domain or product_family or "").strip() or "通用质检"
    return f"{label}质检门槛"


def standard_library_spec_payload(
    *,
    spec_id: str,
    org_id: str,
    domain: str | None,
    product_family: str,
) -> dict[str, Any]:
    return {
        "id": spec_id,
        "org_id": org_id,
        "spec_code": standard_library_spec_code(product_family),
        "name": standard_library_spec_name(domain, product_family),
        "version": "2026.1",
        "product_id": product_family,
        "product_family": product_family,
        "applicable_skus": [product_family],
        "required_views": ["overview"],
        "required_image_count": 1,
        "ai_gate_confidence_threshold": 0.72,
        "ai_gate_evidence_threshold": 0.5,
        "ai_gate_traceability_threshold": 0.5,
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


def standard_library_spec_items(*, spec_id: str, item_id: str, product_family: str) -> list[dict[str, Any]]:
    defect_prefix = str(product_family or "standard").strip().lower()
    return [
        {
            "id": item_id,
            "spec_row_id": spec_id,
            "defect_type": f"{defect_prefix}.critical_defect",
            "severity": "critical",
            "disposition": "fail",
            "confidence_threshold": 0.55,
            "zone_name": "overview",
            "max_count": 1,
            "description": "Critical defects fail the inspection.",
        }
    ]
