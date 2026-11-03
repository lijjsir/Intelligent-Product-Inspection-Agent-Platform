"""Source knowledge to target ontology mapping for QDL.

This module maps retrieved source documents into the target vocabulary used by
the structured text/image fields.  It never changes a model prediction; its
output is context for QDL review and generation.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

try:
    from .defect_ontology import (
        CATEGORY_TO_RISK, DATASET_TO_CATEGORY, DEFECT_CATEGORIES, RISK_TYPES,
        infer_semantic_profile,
    )
except ImportError:  # direct module execution / unittest discovery
    from defect_ontology import (
        CATEGORY_TO_RISK, DATASET_TO_CATEGORY, DEFECT_CATEGORIES, RISK_TYPES,
        infer_semantic_profile,
    )

_TEXT_TO_CATEGORY = {
    "crack": "crack", "裂纹": "crack", "裂缝": "crack", "开裂": "crack",
    "broken": "broken", "破损": "broken", "断裂": "broken", "缺口": "broken",
    "scratch": "scratch", "划痕": "scratch", "刮痕": "scratch", "磨损": "scratch",
    "cut": "cut", "切口": "cut", "割裂": "cut", "撕裂": "cut",
    "hole": "hole", "孔洞": "hole", "针孔": "hole", "poke": "hole",
    "contamination": "contamination", "污染": "contamination", "污渍": "contamination",
    "liquid": "liquid", "漏液": "liquid", "油污": "liquid",
    "bent": "deformation", "变形": "deformation", "弯曲": "deformation", "弯折": "deformation",
    "misalignment": "misalignment", "错位": "misalignment", "偏移": "misalignment",
    "color": "color_abnormality", "变色": "color_abnormality", "色差": "color_abnormality",
    "print": "print_defect", "印刷": "print_defect", "印字": "print_defect",
}


def _clean(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    return re.sub(r"\s+", " ", text)


def infer_category(source_label: Any, description: str = "", criteria: str = "") -> tuple[str, str, float]:
    """Return ``(category, source, confidence)`` without using target labels as GT."""
    profile = infer_semantic_profile(
        source_label,
        description=f"{description} {criteria}".strip(),
    )
    return (
        str(profile["defect_category"]),
        str(profile["mapping_source"]),
        float(profile["mapping_confidence"]),
    )


def transform_retrieved_doc(doc: dict[str, Any], category: str | None = None) -> dict[str, Any]:
    """Convert one source knowledge document into target-context ``K'``."""
    source_label = doc.get("defect_type", doc.get("source_defect_type", ""))
    description = str(doc.get("defect_desc", doc.get("description", "")) or "")
    criteria = str(doc.get("criteria", "") or "")
    profile = infer_semantic_profile(
        source_label,
        description=f"{description} {criteria}".strip(),
        product_category=category or doc.get("category"),
    )
    return {
        "id": doc.get("id"),
        "category": category or doc.get("category"),
        "source": doc.get("source", "mvtec"),
        "source_defect_type": source_label,
        "defect_family": profile["defect_family"],
        "defect_category": profile["defect_category"],
        "defect_subtype": profile["defect_subtype"],
        "component": profile["component"],
        "morphology": profile["morphology"],
        "risk_type": profile["risk_type"],
        "defect_desc": description,
        "criteria": criteria,
        "mapping_source": profile["mapping_source"],
        "mapping_confidence": profile["mapping_confidence"],
    }


def transform_retrieved_docs(docs: Iterable[dict[str, Any]] | None, category: str | None = None) -> list[dict[str, Any]]:
    return [transform_retrieved_doc(doc, category=category) for doc in (docs or [])]


def format_qdl_knowledge_context(docs: Iterable[dict[str, Any]] | None, limit: int = 3) -> str:
    lines = []
    for doc in list(docs or [])[:limit]:
        lines.append(
            f"- source={doc.get('source_defect_type', '')}; "
            f"defect_category={doc.get('defect_category', 'other')}; "
            f"defect_subtype={doc.get('defect_subtype', 'other')}; "
            f"component={doc.get('component', 'unknown')}; "
            f"morphology={doc.get('morphology', 'unspecified_anomaly')}; "
            f"risk_type={doc.get('risk_type', 'quality_defect')}; "
            f"criteria={doc.get('criteria', '')}"
        )
    return "\n".join(lines) if lines else "（无检索知识）"


__all__ = [
    "RISK_TYPES", "DEFECT_CATEGORIES", "DATASET_TO_CATEGORY", "CATEGORY_TO_RISK",
    "infer_category", "infer_semantic_profile", "transform_retrieved_doc", "transform_retrieved_docs",
    "format_qdl_knowledge_context",
]
