"""Shared hierarchical defect ontology used by normalization and QDL.

The public structured-input schema remains unchanged.  This module derives an
internal semantic profile from the existing defect category, evidence and
location fields, so fine-grained dataset labels are not destroyed by the
closed-set normalization step.
"""

from __future__ import annotations

import re
from typing import Any, Mapping


DEFECT_CATEGORIES = {
    "crack", "broken", "scratch", "hole", "cut", "contamination", "liquid",
    "deformation", "color_abnormality", "misalignment", "missing_part",
    "print_defect", "surface_damage", "combined", "other", "none",
}

RISK_TYPES = {
    "appearance_abnormality", "structural_damage", "surface_defect",
    "deformation", "contamination", "safety_risk", "quality_defect", "none",
}

CATEGORY_DEFAULTS: dict[str, dict[str, str]] = {
    "crack": {"defect_family": "surface_defect", "morphology": "fissure", "risk_type": "surface_defect"},
    "broken": {"defect_family": "structural_damage", "morphology": "fracture", "risk_type": "structural_damage"},
    "scratch": {"defect_family": "surface_defect", "morphology": "linear_abrasion", "risk_type": "surface_defect"},
    "hole": {"defect_family": "structural_damage", "morphology": "perforation", "risk_type": "structural_damage"},
    "cut": {"defect_family": "surface_defect", "morphology": "cut_or_tear", "risk_type": "surface_defect"},
    "contamination": {"defect_family": "contamination", "morphology": "foreign_material", "risk_type": "contamination"},
    "liquid": {"defect_family": "contamination", "morphology": "liquid_residue", "risk_type": "contamination"},
    "deformation": {"defect_family": "geometric_defect", "morphology": "shape_deformation", "risk_type": "deformation"},
    "color_abnormality": {"defect_family": "appearance_defect", "morphology": "color_change", "risk_type": "appearance_abnormality"},
    "misalignment": {"defect_family": "geometric_defect", "morphology": "misplacement", "risk_type": "deformation"},
    "missing_part": {"defect_family": "structural_damage", "morphology": "material_absence", "risk_type": "structural_damage"},
    "print_defect": {"defect_family": "appearance_defect", "morphology": "print_irregularity", "risk_type": "appearance_abnormality"},
    "surface_damage": {"defect_family": "surface_defect", "morphology": "surface_irregularity", "risk_type": "surface_defect"},
    "combined": {"defect_family": "composite_defect", "morphology": "multiple_anomalies", "risk_type": "quality_defect"},
    "other": {"defect_family": "quality_defect", "morphology": "unspecified_anomaly", "risk_type": "quality_defect"},
    "none": {"defect_family": "none", "morphology": "none", "risk_type": "none"},
}


def _entry(category: str, subtype: str, component: str = "unknown",
           morphology: str | None = None, family: str | None = None,
           risk_type: str | None = None) -> dict[str, str]:
    base = CATEGORY_DEFAULTS[category]
    return {
        "defect_family": family or base["defect_family"],
        "defect_category": category,
        "defect_subtype": subtype,
        "component": component,
        "morphology": morphology or base["morphology"],
        "risk_type": risk_type or base["risk_type"],
    }


# Canonical source-label registry.  The original source label is always kept as
# ``defect_subtype`` when it carries more information than the closed category.
DEFECT_ONTOLOGY: dict[str, dict[str, str]] = {
    "broken_large": _entry("broken", "broken_large", morphology="large_fracture"),
    "broken_small": _entry("broken", "broken_small", morphology="small_fracture"),
    "contamination": _entry("contamination", "contamination"),
    "bent_wire": _entry("deformation", "bent_wire", "wire", "wire_bending"),
    "cable_swap": _entry("misalignment", "cable_swap", "cable", "cable_transposition"),
    "combined": _entry("combined", "combined"),
    "cut_inner_insulation": _entry("cut", "cut_inner_insulation", "inner_insulation"),
    "cut_outer_insulation": _entry("cut", "cut_outer_insulation", "outer_insulation"),
    "missing_cable": _entry("missing_part", "missing_cable", "cable"),
    "missing_wire": _entry("missing_part", "missing_wire", "wire"),
    "poke_insulation": _entry("hole", "poke_insulation", "insulation", "puncture"),
    "crack": _entry("crack", "crack"),
    "faulty_imprint": _entry("print_defect", "faulty_imprint", "print_area"),
    "poke": _entry("hole", "poke", morphology="puncture"),
    "scratch": _entry("scratch", "scratch"),
    "squeeze": _entry("deformation", "squeeze", morphology="compression"),
    "color": _entry("color_abnormality", "color"),
    "cut": _entry("cut", "cut"),
    "hole": _entry("hole", "hole"),
    "metal_contamination": _entry("contamination", "metal_contamination", morphology="metal_foreign_material"),
    "thread": _entry("surface_damage", "thread", "surface", "loose_thread"),
    "bent": _entry("deformation", "bent", morphology="bending"),
    "broken": _entry("broken", "broken"),
    "glue": _entry("contamination", "glue", morphology="adhesive_residue"),
    "print": _entry("print_defect", "print", "print_area"),
    "fold": _entry("deformation", "fold", morphology="folding"),
    "flip": _entry("misalignment", "flip", morphology="orientation_flip"),
    "type": _entry("other", "type", morphology="type_mismatch"),
    "manipulated_front": _entry("misalignment", "manipulated_front", "front", "front_displacement"),
    "scratch_head": _entry("scratch", "scratch_head", "head", "linear_abrasion"),
    "scratch_neck": _entry("scratch", "scratch_neck", "neck", "linear_abrasion"),
    # Keep the compatible category while retaining the structural subtype.
    "thread_side": _entry("surface_damage", "thread_side", "side_thread", "thread_deformation", "structural_or_geometric", "structural_damage"),
    "thread_top": _entry("surface_damage", "thread_top", "top_thread", "thread_deformation", "structural_or_geometric", "structural_damage"),
    "glue_strip": _entry("contamination", "glue_strip", "strip", "adhesive_residue"),
    "gray_stroke": _entry("color_abnormality", "gray_stroke", "surface", "gray_discoloration"),
    "oil": _entry("liquid", "oil", "surface", "oil_residue"),
    "rough": _entry("surface_damage", "rough", "surface", "surface_roughness"),
    "defective": _entry("surface_damage", "defective", morphology="surface_irregularity"),
    "bent_lead": _entry("deformation", "bent_lead", "lead", "lead_bending"),
    "cut_lead": _entry("cut", "cut_lead", "lead"),
    "damaged_case": _entry("broken", "damaged_case", "case", "case_fracture"),
    "misplaced": _entry("misalignment", "misplaced"),
    "liquid": _entry("liquid", "liquid"),
    "broken_teeth": _entry("broken", "broken_teeth", "teeth", "tooth_fracture"),
    "fabric_border": _entry("surface_damage", "fabric_border", "border", "fabric_damage"),
    "fabric_interior": _entry("surface_damage", "fabric_interior", "interior", "fabric_damage"),
    "split_teeth": _entry("broken", "split_teeth", "teeth", "tooth_split"),
    "squeezed_teeth": _entry("deformation", "squeezed_teeth", "teeth", "tooth_compression"),
}

DATASET_TO_CATEGORY = {key: value["defect_category"] for key, value in DEFECT_ONTOLOGY.items()}
CATEGORY_TO_RISK = {key: value["risk_type"] for key, value in CATEGORY_DEFAULTS.items()}

_SPECIFIC_ALIASES: list[tuple[tuple[str, ...], str]] = [
    (("thread_side", "thread side", "side thread", "侧面螺纹", "螺纹侧面"), "thread_side"),
    (("thread_top", "thread top", "top thread", "顶部螺纹", "螺纹顶部"), "thread_top"),
    (("scratch_neck", "scratch neck", "neck scratch", "颈部划痕", "螺颈划痕"), "scratch_neck"),
    (("scratch_head", "scratch head", "head scratch", "头部划痕", "螺钉头划痕"), "scratch_head"),
    (("cut_inner_insulation", "inner insulation cut", "内层绝缘切口"), "cut_inner_insulation"),
    (("cut_outer_insulation", "outer insulation cut", "外层绝缘切口"), "cut_outer_insulation"),
    (("missing_cable", "missing cable", "电缆缺失"), "missing_cable"),
    (("missing_wire", "missing wire", "导线缺失"), "missing_wire"),
    (("bent_lead", "bent lead", "引脚弯曲"), "bent_lead"),
    (("cut_lead", "cut lead", "引脚切断"), "cut_lead"),
    (("damaged_case", "damaged case", "外壳破损"), "damaged_case"),
    (("broken_teeth", "broken teeth", "齿牙断裂"), "broken_teeth"),
    (("split_teeth", "split teeth", "齿牙开裂"), "split_teeth"),
    (("squeezed_teeth", "squeezed teeth", "齿牙挤压"), "squeezed_teeth"),
]

_CATEGORY_ALIASES: list[tuple[tuple[str, ...], str]] = [
    (("crack", "裂纹", "裂缝", "开裂"), "crack"),
    (("broken", "break", "破损", "破裂", "断裂", "缺口"), "broken"),
    (("scratch", "abrasion", "划痕", "刮痕", "磨损"), "scratch"),
    (("hole", "puncture", "孔洞", "针孔"), "hole"),
    (("cut", "tear", "切口", "割裂", "撕裂"), "cut"),
    (("contamination", "stain", "dirty", "污染", "污渍", "异物"), "contamination"),
    (("liquid", "oil", "漏液", "油污", "液体"), "liquid"),
    (("deformation", "bent", "fold", "变形", "弯曲", "弯折"), "deformation"),
    (("misalignment", "misplaced", "错位", "偏移"), "misalignment"),
    (("missing", "缺失", "缺少"), "missing_part"),
    (("color", "discolor", "变色", "色差"), "color_abnormality"),
    (("print", "imprint", "印刷", "印字"), "print_defect"),
    (("rough", "thread", "surface damage", "表面损伤", "粗糙"), "surface_damage"),
]

_COMPONENT_ALIASES: list[tuple[tuple[str, ...], str]] = [
    (("side thread", "thread side", "侧面螺纹"), "side_thread"),
    (("top thread", "thread top", "顶部螺纹"), "top_thread"),
    (("neck", "颈部", "螺颈"), "neck"),
    (("head", "头部", "螺钉头"), "head"),
    (("inner insulation", "内层绝缘"), "inner_insulation"),
    (("outer insulation", "外层绝缘"), "outer_insulation"),
    (("wire", "导线", "电线"), "wire"),
    (("lead", "引脚"), "lead"),
    (("case", "外壳"), "case"),
    (("teeth", "齿牙", "齿"), "teeth"),
    (("border", "边缘"), "border"),
    (("interior", "内部"), "interior"),
]


def _clean(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    text = re.sub(r"[(){}\[\],;:]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _base_profile(category: str, subtype: str | None = None) -> dict[str, str]:
    category = category if category in CATEGORY_DEFAULTS else "other"
    return _entry(category, subtype or category)


def infer_semantic_profile(source_label: Any, description: str = "",
                           location_hint: str = "", product_category: str | None = None) -> dict[str, Any]:
    """Infer a hierarchical profile without consulting evaluation labels."""
    label = _clean(source_label)
    combined = " ".join(part for part in (label, _clean(description), _clean(location_hint)) if part)

    matched_key = None
    mapping_source = "empty"
    confidence = 1.0
    # An explicit fine-grained label is stronger than a phrase match.  Generic
    # labels such as ``scratch`` may still be refined by location/evidence.
    if label in DEFECT_ONTOLOGY and label not in CATEGORY_DEFAULTS:
        matched_key, mapping_source, confidence = label, "ontology_exact", 1.0
    if matched_key is None:
        for aliases, key in _SPECIFIC_ALIASES:
            if any(alias in combined for alias in aliases):
                matched_key, mapping_source, confidence = key, "fine_grained_alias", 0.90
                break
    if matched_key is None and label in DEFECT_ONTOLOGY:
        matched_key, mapping_source, confidence = label, "ontology_exact", 1.0

    if matched_key is not None:
        profile = dict(DEFECT_ONTOLOGY[matched_key])
    else:
        canonical = label if label in CATEGORY_DEFAULTS and label not in {"none", "other"} else None
        if canonical is None:
            for aliases, category in _CATEGORY_ALIASES:
                if any(alias in combined for alias in aliases):
                    canonical, mapping_source, confidence = category, "semantic_alias", 0.78
                    break
        if canonical is None:
            canonical = "none" if not combined or label in {"none", "null", "unknown", "n/a"} else "other"
            mapping_source = "empty" if canonical == "none" else "fallback"
            confidence = 1.0 if canonical == "none" else 0.35
        elif mapping_source == "empty":
            mapping_source = "category_exact"
        profile = _base_profile(canonical)

    if profile["component"] == "unknown":
        for aliases, component in _COMPONENT_ALIASES:
            if any(alias in combined for alias in aliases):
                profile["component"] = component
                break

    return {
        "source_label": str(source_label or ""),
        **profile,
        "product_category": product_category,
        "mapping_source": mapping_source,
        "mapping_confidence": confidence,
    }


def profile_from_structured(record: Mapping[str, Any] | None,
                            product_category: str | None = None) -> dict[str, Any]:
    data = dict(record or {})
    return infer_semantic_profile(
        data.get("defect_category"),
        description=str(data.get("evidence_summary", "") or ""),
        location_hint=str(data.get("location_hint", "") or ""),
        product_category=product_category,
    )


def semantic_profile_score(left: Mapping[str, Any], right: Mapping[str, Any]) -> tuple[float, str]:
    """Return the agreed hierarchy score and an auditable match level."""
    lc, rc = left.get("defect_category"), right.get("defect_category")
    if lc == rc == "none":
        return 1.0, "both_none"
    if "none" in {lc, rc}:
        return 0.10, "presence_conflict"
    same_component = (
        left.get("component") == right.get("component")
        and left.get("component") not in {None, "", "unknown"}
    )
    if left.get("defect_subtype") == right.get("defect_subtype") and same_component:
        return 1.00, "subtype_and_component"
    if lc == rc and same_component:
        return 0.90, "category_and_component"
    if lc == rc:
        return 0.75, "category"
    if left.get("defect_family") == right.get("defect_family") and left.get("defect_family") not in {None, "", "none"}:
        return 0.55, "family"
    return 0.10, "semantic_conflict"


__all__ = [
    "DEFECT_CATEGORIES", "RISK_TYPES", "CATEGORY_DEFAULTS", "CATEGORY_TO_RISK",
    "DEFECT_ONTOLOGY", "DATASET_TO_CATEGORY", "infer_semantic_profile",
    "profile_from_structured", "semantic_profile_score",
]
