"""QDL: semantic many-to-many alignment for structured text/image fields.

The core is dependency-light.  ``embedder`` may be any object exposing
``encode(list[str])``.  ``llm_reviewer`` is an optional injected callback that
receives a prompt and returns a JSON string or mapping.  This keeps model
loading outside the QDL implementation and makes deterministic tests possible.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

try:  # package import
    from .knowledge_mapping import CATEGORY_TO_RISK, DEFECT_CATEGORIES, RISK_TYPES, format_qdl_knowledge_context, infer_category
    from .defect_ontology import profile_from_structured, semantic_profile_score
except ImportError:  # flat source directory imports
    from knowledge_mapping import CATEGORY_TO_RISK, DEFECT_CATEGORIES, RISK_TYPES, format_qdl_knowledge_context, infer_category
    from defect_ontology import profile_from_structured, semantic_profile_score

TEXT_FIELDS = [
    "has_defect", "risk_type", "severity", "defect_category", "location_hint",
    "evidence_summary", "emotion_label", "emotion_intensity",
]
IMAGE_FIELDS = [
    "has_defect", "risk_type", "severity", "defect_category", "location_hint",
    "evidence_summary", "bbox",
]

COMPATIBLE_FIELD_PAIRS = {
    "has_defect": {"has_defect", "risk_type", "defect_category"},
    "risk_type": {"risk_type", "defect_category", "evidence_summary"},
    "severity": {"severity", "evidence_summary"},
    "defect_category": {"defect_category", "risk_type", "evidence_summary"},
    "location_hint": {"location_hint", "bbox", "evidence_summary"},
    "evidence_summary": {"risk_type", "defect_category", "location_hint", "evidence_summary", "bbox"},
    "emotion_label": {"evidence_summary"},
    "emotion_intensity": {"severity"},
}

DEFAULT_WEIGHTS = {
    "has_defect": 0.20, "defect_category": 0.25, "evidence_summary": 0.20,
    "risk_type": 0.10, "location_hint": 0.10, "bbox": 0.10, "severity": 0.05,
}


@dataclass(frozen=True)
class QDLConfig:
    candidate_threshold: float = 0.55
    edge_threshold: float = 0.60
    supported_threshold: float = 0.70
    partial_threshold: float = 0.40
    llm_review: bool = True
    allow_rule_fallback: bool = True
    max_candidates: int | None = 128
    # ``None`` means keep every candidate after the compatibility/threshold
    # stage.  The live pipeline may override this with an experiment budget.
    alignment_lambda: float = 0.80
    enable_specialized_matching: bool = True
    field_weights: Mapping[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    # Reserved for validation-fitted temperature scaling.  It has no effect
    # unless both Yes/No logits are explicitly present in the image record.
    probability_temperature: float | None = None


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(str(x) for x in value)
    if isinstance(value, dict):
        return " ".join(f"{k} {v}" for k, v in value.items())
    return str(value).strip().lower().replace("_", " ")


def _empty(value: Any) -> bool:
    return _text(value).strip() in {"", "none", "null", "unknown", "n/a", "nan"}


def _yes_no(value: Any) -> str:
    value = _text(value)
    if value in {"yes", "true", "1", "是", "有"}:
        return "yes"
    if value in {"no", "false", "0", "否", "无"}:
        return "no"
    return value


def _cosine(a: Any, b: Any) -> float:
    try:
        av, bv = list(a), list(b)
        dot = sum(float(x) * float(y) for x, y in zip(av, bv))
        na = math.sqrt(sum(float(x) ** 2 for x in av))
        nb = math.sqrt(sum(float(y) ** 2 for y in bv))
        if not na or not nb:
            return 0.0
        return max(0.0, min(1.0, (dot / (na * nb) + 1.0) / 2.0))
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


def _token_similarity(a: str, b: str) -> float:
    def tokens(value: str) -> set[str]:
        chunks = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", value.lower())
        result = set(chunks)
        for chunk in chunks:
            if any("\u4e00" <= char <= "\u9fff" for char in chunk):
                result.update(chunk[idx:idx + 2] for idx in range(len(chunk) - 1))
        return result
    ta = tokens(a)
    tb = tokens(b)
    if not ta or not tb:
        return 1.0 if a == b and a else 0.0
    return len(ta & tb) / len(ta | tb)


def _parse_bbox(value: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        box = tuple(float(v) for v in value)
    except (TypeError, ValueError):
        return None
    x1, y1, x2, y2 = box
    return box if x2 >= x1 and y2 >= y1 else None


def _region_from_text(value: Any) -> str | None:
    text = _text(value)
    aliases = {
        "top_left": ("top left", "upper left", "左上", "左上角"),
        "top_right": ("top right", "upper right", "右上", "右上角"),
        "bottom_left": ("bottom left", "lower left", "左下", "左下角"),
        "bottom_right": ("bottom right", "lower right", "右下", "右下角"),
        "center": ("center", "middle", "中心", "中间"),
    }
    for region, words in aliases.items():
        if any(word in text for word in words):
            return region
    return None


def _region_bbox_score(region: str, box: tuple[float, float, float, float]) -> float:
    x1, y1, x2, y2 = box
    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    # Coordinates can be pixels or normalized; only relative position matters.
    xmax = max(abs(x2), 1.0)
    ymax = max(abs(y2), 1.0)
    left, top = cx <= xmax / 2.0, cy <= ymax / 2.0
    if region == "center":
        return 1.0 if abs(cx / xmax - 0.5) <= 0.2 and abs(cy / ymax - 0.5) <= 0.2 else 0.4
    expected = {
        "top_left": (True, True), "top_right": (False, True),
        "bottom_left": (True, False), "bottom_right": (False, False),
    }.get(region)
    return 1.0 if expected == (left, top) else 0.2


def _parse_review(value: Any) -> dict[str, Any] | None:
    if isinstance(value, Mapping):
        return dict(value)
    if not isinstance(value, str):
        return None
    clean = re.sub(r"```(?:json)?|```", "", value, flags=re.I).strip()
    try:
        parsed = json.loads(clean)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        start, end = clean.find("{"), clean.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(clean[start:end + 1])
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                return None
    return None


class QDLMatcher:
    """Build and score a text-field/image-field many-to-many relation graph."""

    RELATIONS = {"same_concept", "supports", "refines", "locates", "contradicts", "unrelated"}

    def __init__(self, embedder: Any = None, llm_reviewer: Callable[[str], Any] | None = None,
                 config: QDLConfig | None = None,
                 trace_callback: Callable[[Mapping[str, Any]], None] | None = None):
        self.embedder = embedder
        self.llm_reviewer = llm_reviewer
        self.config = config or QDLConfig()
        self.trace_callback = trace_callback

    def _trace(self, event: Mapping[str, Any]) -> None:
        if self.trace_callback is None:
            return
        try:
            self.trace_callback(dict(event))
        except Exception:
            # Diagnostics must never change the matching result.
            pass

    def match(self, text_structured: Mapping[str, Any] | None,
              image_structured: Mapping[str, Any] | None,
              category: str | None = None,
              retrieved_docs: Iterable[dict[str, Any]] | None = None,
              use_llm_review: bool | None = None) -> dict[str, Any]:
        text_data = dict(text_structured or {})
        image_data = dict(image_structured or {})
        semantic_profiles = {
            "text": profile_from_structured(text_data, product_category=category),
            "image": profile_from_structured(image_data, product_category=category),
        }
        semantic_repairs: dict[str, dict[str, dict[str, Any]]] = {}
        for side, data in (("text", text_data), ("image", image_data)):
            profile = semantic_profiles[side]
            changes: dict[str, dict[str, Any]] = {}
            current_category = _text(data.get("defect_category")).replace(" ", "_")
            inferred_category = str(profile.get("defect_category", "none"))
            if current_category in {"", "none", "other"} and inferred_category not in {"none", "other"}:
                changes["defect_category"] = {"from": data.get("defect_category"), "to": inferred_category}
                data["defect_category"] = inferred_category
            current_risk = _text(data.get("risk_type")).replace(" ", "_")
            inferred_risk = str(profile.get("risk_type", "none"))
            if current_risk in {"", "none"} and inferred_risk != "none" and _yes_no(data.get("has_defect")) != "no":
                changes["risk_type"] = {"from": data.get("risk_type"), "to": inferred_risk}
                data["risk_type"] = inferred_risk
            if changes:
                semantic_repairs[side] = changes
        profile_score, profile_level = semantic_profile_score(
            semantic_profiles["text"], semantic_profiles["image"]
        )
        nodes = self._build_nodes(text_data, image_data, semantic_profiles)
        candidate_pool = self._candidate_edges(text_data, image_data, category, semantic_profiles)
        candidates = self._limit_candidates(candidate_pool)
        self._trace({
            "event": "candidate_pool_ready",
            "candidate_pool_count": len(candidate_pool),
            "candidate_count": len(candidates),
        })
        accepted, review_used, fallback_used = [], False, False
        fallback_reasons: dict[str, int] = {}
        knowledge = list(retrieved_docs or [])
        allow_llm = self.config.llm_review if use_llm_review is None else bool(use_llm_review)
        for edge_index, edge in enumerate(candidates, 1):
            self._trace({
                "event": "edge_start",
                "edge_index": edge_index,
                "edge_total": len(candidates),
                "text_field": edge.get("text_field"),
                "image_field": edge.get("image_field"),
            })
            review = None
            if allow_llm and self.llm_reviewer is not None:
                review = self._review(
                    edge, text_data, image_data, category, knowledge, semantic_profiles
                )
                review_used = True
            if review is None:
                fallback_used = fallback_used or (allow_llm and self.llm_reviewer is not None)
                if not allow_llm:
                    reason = "llm_disabled"
                elif self.llm_reviewer is None:
                    reason = "llm_unavailable"
                else:
                    reason = "llm_invalid_or_exception"
                fallback_reasons[reason] = fallback_reasons.get(reason, 0) + 1
                if self.config.allow_rule_fallback:
                    edge = self._rule_review(edge, text_data, image_data)
                else:
                    edge = {**edge, "relation": "unrelated", "score": 0.0,
                            "decision_source": "llm_required"}
            else:
                edge = self._apply_review(edge, review)
            if edge["score"] >= self.config.edge_threshold and edge["relation"] != "unrelated":
                accepted.append(edge)
            self._trace({
                "event": "edge_done",
                "edge_index": edge_index,
                "edge_total": len(candidates),
                "text_field": edge.get("text_field"),
                "image_field": edge.get("image_field"),
                "relation": edge.get("relation"),
                "score": edge.get("score"),
                "accepted": edge in accepted,
            })
        field_scores, field_score_details = self._aggregate_field_scores(
            text_data, image_data, accepted
        )
        alignment = self._aggregate_alignment(field_scores, text_data, image_data)
        return {
            "nodes": nodes,
            "candidate_edges": candidates,
            "accepted_edges": accepted,
            "relation_matrix": self._relation_matrix(accepted),
            "field_scores": field_scores,
            "field_score_details": field_score_details,
            "field_alignment_score": alignment["field_alignment_score"],
            "has_defect_score": alignment["has_defect_score"],
            "alignment_score": alignment["alignment_score"],
            "consistency_label": self._label(alignment["alignment_score"]),
            "semantic_profiles": semantic_profiles,
            "semantic_profile_score": profile_score,
            "semantic_profile_match_level": profile_level,
            "probability_calibration": self._probability_calibration(image_data),
            "thresholds": {
                "edge_accept": self.config.edge_threshold,
                "supported": self.config.supported_threshold,
                "partial": self.config.partial_threshold,
                "alignment_lambda": self.config.alignment_lambda,
            },
            "audit": {
                "llm_review_used": review_used,
                "embedding_backend": "injected_embedder" if self.embedder is not None else "token_jaccard_fallback",
                "fallback_used": fallback_used,
                "candidate_pool_count": len(candidate_pool),
                "candidate_count": len(candidates),
                "accepted_edge_count": len(accepted),
                "semantic_profile_match_level": profile_level,
                "semantic_repairs": semantic_repairs,
                "fallback_reasons": fallback_reasons,
                "relation_counts": self._relation_counts(accepted),
                "raw_vs_normalized": {
                    "text_changed_fields": text_data.get("changed_fields", []),
                    "image_changed_fields": image_data.get("changed_fields", []),
                },
            },
        }

    def _build_nodes(self, text_data: dict, image_data: dict,
                     semantic_profiles: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
        nodes = []
        for side, data, fields in (("text", text_data, TEXT_FIELDS), ("image", image_data, IMAGE_FIELDS)):
            for field_name in fields:
                if field_name in data:
                    nodes.append({
                        "node_id": f"{side}.{field_name}", "side": side, "field": field_name,
                        "value": data.get(field_name), "normalized_value": _text(data.get(field_name)),
                        "source": "normalized", "confidence": data.get("confidence"),
                    })
            for field_name in ("defect_family", "defect_subtype", "component", "morphology"):
                value = semantic_profiles.get(side, {}).get(field_name)
                if value not in {None, "", "unknown", "none"}:
                    nodes.append({
                        "node_id": f"{side}.semantic.{field_name}",
                        "side": side,
                        "field": field_name,
                        "value": value,
                        "normalized_value": _text(value),
                        "source": "derived_semantic_profile",
                        "confidence": semantic_profiles.get(side, {}).get("mapping_confidence"),
                    })
        return nodes

    def _candidate_edges(self, text_data: dict, image_data: dict, category: str | None,
                         semantic_profiles: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
        edges = []
        for text_field in TEXT_FIELDS:
            if text_field not in text_data:
                continue
            for image_field in IMAGE_FIELDS:
                if image_field not in image_data or image_field not in COMPATIBLE_FIELD_PAIRS.get(text_field, set()):
                    continue
                components = self._component_scores(
                    text_field, text_data[text_field], image_field, image_data[image_field],
                    category, semantic_profiles,
                )
                candidate_score = (
                    0.45 * components["embedding_score"]
                    + 0.25 * components["ontology_score"]
                    + 0.20 * components["context_score"]
                    + 0.10 * components["compatibility_score"]
                )
                # A category-level hierarchical match (0.75) is sufficient to
                # preserve an edge when cross-language embeddings are weak.
                # Critical same-field pairs are also retained: contradictions
                # naturally have low similarity and would otherwise disappear
                # before the relation-review stage.
                selection_reasons = []
                if candidate_score >= self.config.candidate_threshold:
                    selection_reasons.append("candidate_threshold")
                if components["ontology_score"] >= 0.75:
                    selection_reasons.append("ontology_preserve")
                if text_field == image_field and text_field in {
                    "has_defect", "risk_type", "severity", "defect_category"
                }:
                    selection_reasons.append("critical_same_field")
                if selection_reasons:
                    edges.append({
                        "text_field": text_field, "image_field": image_field,
                        "candidate_score": candidate_score, **components,
                        "candidate_selection_reasons": selection_reasons,
                        "relation": "unrelated", "score": candidate_score,
                        "decision_source": "candidate_rules",
                    })
        return sorted(edges, key=lambda item: item["candidate_score"], reverse=True)

    def _limit_candidates(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self.config.max_candidates is None or int(self.config.max_candidates) < 0:
            return candidates
        limit = max(0, int(self.config.max_candidates))
        if len(candidates) <= limit:
            return candidates
        critical = [
            edge for edge in candidates
            if "critical_same_field" in edge.get("candidate_selection_reasons", [])
        ]
        optional = [edge for edge in candidates if edge not in critical]
        selected = critical[:limit]
        selected.extend(optional[:max(0, limit - len(selected))])
        return sorted(selected, key=lambda item: item["candidate_score"], reverse=True)

    def _component_scores(self, text_field: str, text_value: Any, image_field: str,
                          image_value: Any, category: str | None,
                          semantic_profiles: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
        a, b = _text(text_value), _text(image_value)
        embedding = self._embedding_score(a, b)
        specialized, specialized_kind = self._specialized_score(
            text_field, text_value, image_field, image_value
        )
        if specialized is not None:
            # Domain-specific evidence is more reliable than text similarity
            # for coordinates and ordered severity values.
            embedding = specialized
        ontology, ontology_level = self._ontology_score(
            text_field, a, image_field, b, semantic_profiles
        )
        context = self._context_score(a, b, category)
        return {
            "embedding_score": embedding,
            "ontology_score": ontology,
            "ontology_match_level": ontology_level,
            "context_score": context,
            "compatibility_score": 1.0,
            "specialized_score": specialized,
            "specialized_match_type": specialized_kind,
        }

    def _embedding_score(self, a: str, b: str) -> float:
        if not a or not b:
            return 1.0 if not a and not b else 0.0
        if self.embedder is not None:
            try:
                vectors = self.embedder.encode([a, b], normalize_embeddings=True)
                return _cosine(vectors[0], vectors[1])
            except Exception:
                pass
        return _token_similarity(a, b)

    @staticmethod
    def _ontology_score(text_field: str, text_value: str, image_field: str, image_value: str,
                        semantic_profiles: Mapping[str, Mapping[str, Any]] | None = None) -> tuple[float, str]:
        if text_field == "has_defect" or image_field == "has_defect":
            left, right = _yes_no(text_value), _yes_no(image_value)
            if left in {"yes", "no"} and left == right:
                return 1.0, "presence_exact"
            if left == "unknown" or right == "unknown":
                return 0.25, "presence_unknown"
            return 0.0, "presence_conflict"
        if text_field == "severity" or image_field == "severity":
            order = {"none": 0, "low": 1, "medium": 2, "high": 3}
            if text_value in order and image_value in order:
                return max(0.0, 1.0 - abs(order[text_value] - order[image_value]) / 3.0), "severity_distance"
        semantic_fields = {"defect_category", "evidence_summary"}
        if semantic_profiles and (text_field in semantic_fields or image_field in semantic_fields):
            score, level = semantic_profile_score(
                semantic_profiles.get("text", {}), semantic_profiles.get("image", {})
            )
            return score, level
        if text_field in {"risk_type", "defect_category"} or image_field in {"risk_type", "defect_category"}:
            if text_value == image_value:
                return 1.0, "exact"
            # Evidence prose may name the canonical morphology in Chinese while
            # the image side emits the English closed-set category.
            if image_field == "defect_category" and image_value in DEFECT_CATEGORIES:
                inferred, _, confidence = infer_category("", text_value, text_value)
                if inferred == image_value:
                    return max(0.85, confidence), "description_category"
            if text_field == "defect_category" and text_value in DEFECT_CATEGORIES:
                inferred, _, confidence = infer_category("", image_value, image_value)
                if inferred == text_value:
                    return max(0.85, confidence), "description_category"
            if text_value in CATEGORY_TO_RISK and CATEGORY_TO_RISK[text_value] == image_value:
                return 0.85, "category_to_risk"
            if image_value in CATEGORY_TO_RISK and CATEGORY_TO_RISK[image_value] == text_value:
                return 0.85, "category_to_risk"
            if text_value in RISK_TYPES and image_value in RISK_TYPES:
                return (0.5, "risk_family") if text_value != "none" and image_value != "none" else (0.0, "risk_conflict")
        if text_value and image_value:
            return 0.4, "generic_nonempty"
        if not text_value and not image_value:
            return 1.0, "both_empty"
        return 0.0, "one_empty"

    @staticmethod
    def _context_score(a: str, b: str, category: str | None) -> float:
        if not category:
            return 0.5 if a and b else 1.0
        category_text = category.lower().replace("_", " ")
        return 0.75 if category_text in a or category_text in b else 0.5

    def _specialized_score(self, text_field: str, text_value: Any,
                           image_field: str, image_value: Any) -> tuple[float | None, str]:
        if not self.config.enable_specialized_matching:
            return None, "disabled"
        if {text_field, image_field} == {"severity"}:
            order = {"none": 0, "low": 1, "mild": 1, "medium": 2,
                     "moderate": 2, "high": 3, "severe": 3}
            a, b = _text(text_value), _text(image_value)
            if a in order and b in order:
                return max(0.0, 1.0 - abs(order[a] - order[b]) / 3.0), "ordinal_severity"
        if text_field == "location_hint" and image_field == "bbox":
            region = _region_from_text(text_value)
            box = _parse_bbox(image_value)
            if region and box:
                return _region_bbox_score(region, box), "region_bbox"
        if text_field == "evidence_summary" and image_field == "bbox":
            region = _region_from_text(text_value)
            box = _parse_bbox(image_value)
            if region and box:
                return _region_bbox_score(region, box), "evidence_bbox_region"
        return None, "none"

    def _rule_review(self, edge: dict[str, Any], text_data: dict, image_data: dict) -> dict[str, Any]:
        tf, inf = edge["text_field"], edge["image_field"]
        tv, iv = _text(text_data.get(tf)), _text(image_data.get(inf))
        relation = "unrelated"
        score = edge["candidate_score"]
        if _empty(tv) or _empty(iv):
            return {**edge, "relation": "unrelated", "score": min(1.0, score), "decision_source": "rule_review"}
        if tf == inf and tv == iv and tv:
            relation, score = "same_concept", 1.0
        elif tf == "location_hint" and inf == "bbox":
            relation, score = "locates", max(score, 0.65)
        elif tf == "evidence_summary" and inf in {"defect_category", "risk_type", "evidence_summary"}:
            relation, score = "supports", max(score, 0.60)
        elif tf == "defect_category" and inf == "risk_type":
            relation, score = "supports", max(score, 0.65)
        elif tv and iv and float(edge.get("ontology_score", 0.0)) >= 0.85:
            relation, score = "same_concept", max(score, 0.80)
        elif tv and iv and float(edge.get("ontology_score", 0.0)) < 0.25:
            relation, score = "contradicts", max(score, 0.70)
        return {**edge, "relation": relation, "score": min(1.0, score), "decision_source": "rule_review"}

    def _review(self, edge: dict[str, Any], text_data: dict, image_data: dict,
                category: str | None, docs: list[dict[str, Any]],
                semantic_profiles: Mapping[str, Mapping[str, Any]]) -> dict[str, Any] | None:
        prompt = {
            "task": "判断一个文本结构化字段与图像结构化字段之间的语义关系",
            "category": category,
            "text_field": edge["text_field"], "text_value": text_data.get(edge["text_field"]),
            "image_field": edge["image_field"], "image_value": image_data.get(edge["image_field"]),
            "text_record": text_data,
            "image_record": image_data,
            "candidate_scores": {k: edge[k] for k in ("embedding_score", "ontology_score", "context_score")},
            "ontology_match_level": edge.get("ontology_match_level"),
            "semantic_profiles": semantic_profiles,
            "allowed_relations": sorted(self.RELATIONS),
            "knowledge": format_qdl_knowledge_context(docs),
            "output": {"relation": "supports", "score": 0.0, "confidence": 0.0, "reason": ""},
        }
        try:
            parsed = _parse_review(self.llm_reviewer(json.dumps(prompt, ensure_ascii=False)))
        except Exception:
            return None
        if not parsed or parsed.get("relation") not in self.RELATIONS:
            return None
        try:
            score = max(0.0, min(1.0, float(parsed.get("score", edge["candidate_score"]))))
        except (TypeError, ValueError):
            score = edge["candidate_score"]
        return {"relation": parsed["relation"], "score": score, "reason": str(parsed.get("reason", ""))}

    @staticmethod
    def _apply_review(edge: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]:
        return {**edge, **review, "decision_source": "llm_review"}

    @staticmethod
    def _relation_matrix(edges: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
        matrix: dict[str, dict[str, dict[str, Any]]] = {}
        for edge in edges:
            matrix.setdefault(edge["text_field"], {})[edge["image_field"]] = {
                "relation": edge["relation"], "score": edge["score"]
            }
        return matrix

    def _aggregate_field_scores(self, text_data: dict, image_data: dict,
                                edges: list[dict[str, Any]]) -> tuple[dict[str, float], dict[str, dict[str, Any]]]:
        scores = {}
        details = {}
        for field in ("has_defect", "risk_type", "severity", "defect_category", "location_hint", "evidence_summary", "bbox"):
            related = [e for e in edges if e["text_field"] == field or e["image_field"] == field]
            positive_edges = [e for e in related if e["relation"] in {"same_concept", "supports", "refines", "locates"}]
            contradiction_edges = [e for e in related if e["relation"] == "contradicts"]
            supports = [e["score"] for e in positive_edges]
            contradictions = [e["score"] for e in contradiction_edges]
            score = max(supports, default=0.0) - max(contradictions, default=0.0)
            status = "supported" if positive_edges else "unknown"
            if contradiction_edges:
                status = "conflict"
            if field == "bbox" and not text_data.get("location_hint") and not text_data.get("evidence_summary"):
                status = "not_applicable"
                score = 0.0
            if field == "has_defect":
                left, right = _yes_no(text_data.get(field)), _yes_no(image_data.get(field))
                score = 1.0 if left == right and left in {"yes", "no"} else 0.0
                status = "supported" if score else ("unknown" if "unknown" in {left, right} else "conflict")
            scores[field] = max(0.0, min(1.0, score))
            details[field] = {
                "positive_score": max(supports, default=0.0),
                "contradiction_score": max(contradictions, default=0.0),
                "field_score": scores[field],
                "positive_edge_count": len(positive_edges),
                "contradiction_edge_count": len(contradiction_edges),
                "status": status,
            }
        return scores, details

    def _aggregate_alignment(self, field_scores: dict[str, float], text_data: dict, image_data: dict) -> dict[str, float]:
        weights = dict(self.config.field_weights)
        active = {field: score for field, score in field_scores.items() if field in weights}
        total = sum(float(weights[field]) for field in active)
        field_score = sum(float(weights[field]) * score for field, score in active.items()) / total if total else 0.0
        has_score = field_scores.get("has_defect", 0.0)
        return {"field_alignment_score": field_score, "has_defect_score": has_score,
                "alignment_score": self.config.alignment_lambda * field_score + (1.0 - self.config.alignment_lambda) * has_score}

    @staticmethod
    def _relation_counts(edges: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for edge in edges:
            relation = str(edge.get("relation", "unknown"))
            counts[relation] = counts.get(relation, 0) + 1
        return counts

    def _label(self, score: float) -> str:
        if score >= self.config.supported_threshold:
            return "supported"
        if score >= self.config.partial_threshold:
            return "partial"
        return "not_supported"

    def _probability_calibration(self, image_data: Mapping[str, Any]) -> dict[str, Any]:
        temperature = self.config.probability_temperature
        result = {
            "enabled": temperature is not None,
            "applied": False,
            "temperature": temperature,
            "calibrated_yes_probability": None,
            "reason": "temperature_not_fitted" if temperature is None else "yes_no_logits_missing",
        }
        if temperature is None:
            return result
        try:
            yes_logit = float(image_data["yes_logit"])
            no_logit = float(image_data["no_logit"])
            temperature = float(temperature)
            if temperature <= 0:
                result["reason"] = "invalid_temperature"
                return result
            yes_scaled, no_scaled = yes_logit / temperature, no_logit / temperature
            pivot = max(yes_scaled, no_scaled)
            yes_exp = math.exp(yes_scaled - pivot)
            no_exp = math.exp(no_scaled - pivot)
            result.update({
                "applied": True,
                "calibrated_yes_probability": yes_exp / (yes_exp + no_exp),
                "reason": "applied_from_validation_fitted_temperature",
            })
        except (KeyError, TypeError, ValueError, OverflowError):
            pass
        return result


def calibrate_qdl_weights(records: Iterable[Mapping[str, Any]], precision_floor: float = 0.85) -> dict[str, Any]:
    """Small dependency-free grid search over field weights and thresholds.

    Each record must contain ``field_scores`` and ``label``. Labels may be
    ``supported``, ``partial`` or ``not_supported``. The returned weights are
    non-negative and sum to one. This is intentionally conservative until
    field-pair annotations are available for a learned matcher.
    """
    rows = list(records)
    if not rows:
        return {"weights": dict(DEFAULT_WEIGHTS), "supported_threshold": 0.70, "partial_threshold": 0.40}
    fields = list(DEFAULT_WEIGHTS)
    targets = {"supported": 1.0, "partial": 0.5, "not_supported": 0.0}
    best = None
    weight_sets = [
        dict(DEFAULT_WEIGHTS),
        {"has_defect": .30, "defect_category": .30, "evidence_summary": .20, "risk_type": .05, "location_hint": .05, "bbox": .05, "severity": .05},
        {"has_defect": .20, "defect_category": .20, "evidence_summary": .30, "risk_type": .10, "location_hint": .10, "bbox": .05, "severity": .05},
        {"has_defect": .20, "defect_category": .25, "evidence_summary": .20, "risk_type": .10, "location_hint": .15, "bbox": .05, "severity": .05},
    ]
    for weights in weight_sets:
        for supported in (0.60, 0.65, 0.70, 0.75, 0.80):
            for partial in (0.30, 0.35, 0.40, 0.45, 0.50):
                if partial >= supported:
                    continue
                predictions, gold = [], []
                for row in rows:
                    fs = row.get("field_scores", {})
                    total = sum(weights.get(f, 0.0) for f in fields)
                    score = sum(weights.get(f, 0.0) * float(fs.get(f, 0.0)) for f in fields) / total
                    predictions.append(score >= supported)
                    gold.append(targets.get(str(row.get("label", "partial")), 0.5) >= 0.75)
                tp = sum(p and g for p, g in zip(predictions, gold))
                fp = sum(p and not g for p, g in zip(predictions, gold))
                fn = sum((not p) and g for p, g in zip(predictions, gold))
                precision = tp / (tp + fp) if tp + fp else 0.0
                recall = tp / (tp + fn) if tp + fn else 0.0
                objective = recall if precision >= precision_floor else recall - (precision_floor - precision) * 2
                if best is None or objective > best["objective"]:
                    best = {"weights": weights, "supported_threshold": supported, "partial_threshold": partial,
                            "precision": precision, "recall": recall, "objective": objective}
    return best or {"weights": dict(DEFAULT_WEIGHTS), "supported_threshold": 0.70, "partial_threshold": 0.40}


__all__ = ["QDLMatcher", "QDLConfig", "calibrate_qdl_weights", "TEXT_FIELDS", "IMAGE_FIELDS"]
