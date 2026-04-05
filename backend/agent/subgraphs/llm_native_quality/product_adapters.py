from __future__ import annotations

import json
from typing import Any


SCREW_COUNT_FIELD_TO_DEFECT = {
    "crack_count": "crack",
    "surface_scratch_count": "surface_scratch",
    "coating_defect_count": "coating_defect",
    "thread_damage_count": "thread_damage",
    "oil_stain_count": "oil_stain",
}

SCREW_STRUCTURED_FIELDS = {
    "record_id",
    "product_id",
    "spec_code",
    "inspection_type",
    "surface_condition",
    "crack_count",
    "surface_scratch_count",
    "coating_defect_count",
    "thread_damage_count",
    "oil_stain_count",
    "inspector_note",
    "expected_decision",
    "priority",
    "image_urls",
}

FOOD_DEFAULT_SPEC_CODE = "FOOD-RAG-BASE-V1"
SCREW_DEFAULT_SPEC_CODE = "SCREW-A-2026-V1"

FOOD_BOOLEAN_RULES: dict[str, tuple[tuple[str, ...], str, str, float]] = {
    "food.label.product_name_present": (("label_info", "product_name_present"), "eq_true", "Product name must be present on label.", 0.95),
    "food.label.ingredient_list_present": (("label_info", "ingredient_list_present"), "eq_true", "Ingredient list must be present on label.", 0.95),
    "food.label.net_content_present": (("label_info", "net_content_present"), "eq_true", "Net content must be present on label.", 0.94),
    "food.label.manufacturer_present": (("label_info", "manufacturer_present"), "eq_true", "Manufacturer information must be present on label.", 0.94),
    "food.label.production_date_present": (("label_info", "production_date_present"), "eq_true", "Production date must be present on label.", 0.94),
    "food.label.shelf_life_present": (("label_info", "shelf_life_present"), "eq_true", "Shelf life must be present on label.", 0.94),
    "food.label.storage_condition_present": (("label_info", "storage_condition_present"), "eq_true", "Storage condition must be present on label.", 0.93),
    "food.label.nutrition_table_present": (("label_info", "nutrition_table_present"), "eq_true", "Nutrition table must be present on label.", 0.92),
    "food.label.font_clear": (("label_info", "font_clear"), "eq_true", "Label text must be clear and readable.", 0.9),
    "food.label.additive_common_names_complete": (("label_info", "additive_common_names_complete"), "eq_true", "Food additive common names must be declared completely.", 0.96),
    "food.process.traceability_record": (("process_records", "traceability_record"), "eq_true", "Traceability process record must be available.", 0.97),
    "food.traceability.supplier_batch_linked": (("traceability", "supplier_batch_linked"), "eq_true", "Supplier batch linkage is required.", 0.96),
    "food.traceability.qr_code_required": (("traceability", "qr_code"), "non_empty", "Traceability QR code is required.", 0.98),
    "food.packaging.leakage": (("packaging", "leakage"), "eq_false", "Packaging must not leak.", 0.99),
    "food.packaging.deformation": (("packaging", "deformation"), "eq_false", "Packaging must not deform.", 0.93),
    "food.packaging.surface_contamination": (("packaging", "surface_contamination"), "eq_false", "Packaging surface must be clean.", 0.95),
}

FOOD_ALLOWED_SEAL_VALUES = {"good", "sealed", "intact", "normal"}


def normalize_key(raw_key: str) -> str:
    return str(raw_key or "").strip().lower().replace("-", "_").replace(" ", "_")


def parse_kv_text(text: str) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, value = line.split("=", 1)
        elif ":" in line:
            key, value = line.split(":", 1)
        else:
            continue
        normalized_key = normalize_key(key)
        parsed[normalized_key] = value.strip()
    return parsed


def parse_structured_text(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    if raw.startswith("{") and raw.endswith("}"):
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
    return parse_kv_text(raw)


def deep_merge(target: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            target[key] = deep_merge(dict(target[key]), value)
        elif value not in (None, "", [], {}):
            target[key] = value
    return target


def detect_product_family(record: dict[str, Any], fallback_product_id: str | None = None) -> str:
    for key in ("product_family", "category", "product_category"):
        value = str(record.get(key) or "").strip().lower()
        if value:
            return value
    if any(key in record for key in ("label_info", "packaging", "process_records", "traceability", "test_results")):
        return "food"
    if any(key in record for key in SCREW_STRUCTURED_FIELDS):
        return "screw"
    candidate = str(record.get("product_id") or fallback_product_id or "").strip().lower()
    if candidate == "screw":
        return "screw"
    if candidate.startswith("food"):
        return "food"
    return candidate or "general"


def resolve_spec_code(record: dict[str, Any], product_family: str, fallback_spec_code: str | None = None) -> str:
    explicit = str(record.get("spec_code") or fallback_spec_code or "").strip()
    if explicit:
        return explicit
    if product_family == "food":
        return FOOD_DEFAULT_SPEC_CODE
    if product_family == "screw":
        return SCREW_DEFAULT_SPEC_CODE
    return ""


def resolve_product_id(record: dict[str, Any], product_family: str, fallback_product_id: str | None = None) -> str:
    explicit = str(record.get("product_id") or fallback_product_id or "").strip()
    if explicit:
        return explicit
    return product_family


def int_value(value: Any) -> int:
    try:
        return max(0, int(float(str(value or "0").strip())))
    except Exception:
        return 0


def list_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]
    return []


def get_nested(payload: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = payload
    for part in path:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def expected_verdict_from_record(record: dict[str, Any], product_family: str) -> str | None:
    if product_family == "food":
        expected = record.get("expected_result")
        if isinstance(expected, dict):
            if expected.get("is_qualified") is True:
                return "pass"
            if expected.get("is_qualified") is False:
                return "fail"
        return None
    return str(record.get("expected_decision") or "").strip().lower() or None


def build_screw_defects(record: dict[str, Any]) -> list[dict[str, Any]]:
    defects: list[dict[str, Any]] = []
    for field_name, defect_type in SCREW_COUNT_FIELD_TO_DEFECT.items():
        count = int_value(record.get(field_name))
        for _ in range(count):
            defects.append(
                {
                    "type": defect_type,
                    "confidence": 0.93 if defect_type in {"crack", "surface_scratch", "coating_defect"} else 0.74,
                    "description": f"Derived from structured field {field_name}",
                }
            )
    return defects


def build_food_defects(record: dict[str, Any]) -> list[dict[str, Any]]:
    defects: list[dict[str, Any]] = []
    for rule_key, (path, mode, description, confidence) in FOOD_BOOLEAN_RULES.items():
        value = get_nested(record, path)
        failed = False
        if mode == "eq_true":
            failed = value is False
        elif mode == "eq_false":
            failed = value is True
        elif mode == "non_empty":
            failed = not str(value or "").strip()
        if failed:
            defects.append(
                {
                    "type": rule_key,
                    "confidence": confidence,
                    "description": description,
                }
            )

    seal_integrity = str(get_nested(record, ("packaging", "seal_integrity")) or "").strip().lower()
    if seal_integrity and seal_integrity not in FOOD_ALLOWED_SEAL_VALUES:
        defects.append(
            {
                "type": "food.packaging.seal_integrity",
                "confidence": 0.97,
                "description": f"Packaging seal integrity is abnormal: {seal_integrity}",
            }
        )

    coliform = int_value(get_nested(record, ("test_results", "microbiology", "coliform_cfu_per_ml")))
    if coliform > 0:
        defects.append(
            {
                "type": "food.microbiology.coliform_present",
                "confidence": 0.92,
                "description": "Coliform should not be detected in the current food sample baseline.",
            }
        )

    coliform_g = int_value(get_nested(record, ("test_results", "microbiology", "coliform_cfu_per_g")))
    if coliform_g > 0:
        defects.append(
            {
                "type": "food.microbiology.coliform_present",
                "confidence": 0.92,
                "description": "Coliform should not be detected in the current food sample baseline.",
            }
        )

    salmonella = str(get_nested(record, ("test_results", "microbiology", "pathogen_salmonella")) or "").strip().lower()
    if salmonella and salmonella != "not_detected":
        defects.append(
            {
                "type": "food.microbiology.salmonella_detected",
                "confidence": 0.99,
                "description": "Salmonella must not be detected.",
            }
        )
    return defects


def build_defects(record: dict[str, Any], product_family: str) -> list[dict[str, Any]]:
    if product_family == "food":
        return build_food_defects(record)
    return build_screw_defects(record)


def score_from_record(defects: list[dict[str, Any]], expected_verdict: str | None) -> float:
    total_defects = len(defects)
    if total_defects == 0:
        return 0.96
    if str(expected_verdict or "").lower() == "fail":
        return max(0.24, 0.58 - min(total_defects, 4) * 0.08)
    return max(0.22, 0.64 - min(total_defects, 4) * 0.09)


def collect_rule_hits(evaluation: dict[str, Any]) -> list[str]:
    return [str(item.get("defect_type") or "") for item in list(evaluation.get("matched_rules") or []) if item.get("defect_type")]

