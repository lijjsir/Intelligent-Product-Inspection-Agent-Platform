from __future__ import annotations

import re
from typing import Any

from app.core.config import settings
from app.core.exceptions import ValidationError
from app.repositories.quality_kg_repo import Neo4jQualityKgRepository
from app.services.quality_kg_schema import (
    QualityKgNodeDelete,
    QualityKgNode,
    QualityKgRelationship,
    QualityKgRelationshipDelete,
    QualityKnowledgeChain,
)


_CORE_OPTIONAL_FIELDS = ("standard", "inspection_item", "metric", "defect_type")
_SENTENCE_MARKERS = ("，", "。", "；", ";", " therefore ", " because ")
_DOMAIN_BY_PRODUCT_FAMILY = {
    "food": "食品接触材料",
    "foods": "食品接触材料",
    "electronics": "电子产品",
    "electronic": "电子产品",
    "elec": "电子产品",
    "screw": "紧固件",
    "fastener": "紧固件",
    "fasteners": "紧固件",
    "textile": "纺织品",
    "textiles": "纺织品",
}
_ACTION_BY_DISPOSITION = {
    "fail": "禁止放行",
    "manual_required": "人工复核",
    "uncertain": "人工复核",
    "pass": "放行",
}


class QualityKnowledgeGraphService:
    def __init__(self, *, repo=None, org_id: str):
        self._repo = repo or Neo4jQualityKgRepository(
            uri=settings.neo4j_uri,
            username=settings.neo4j_username,
            password=settings.neo4j_password,
            database=settings.neo4j_database,
        )
        self._org_id = str(org_id or "").strip()

    async def ingest_chain(self, chain: QualityKnowledgeChain) -> None:
        await self._repo.ensure_schema()
        await self._ingest_validated_chain(chain)

    async def ingest_chains(self, chains: list[QualityKnowledgeChain]) -> None:
        await self._repo.ensure_schema()
        for chain in chains:
            await self._ingest_validated_chain(chain)

    async def search_actions_by_product_and_metric(
        self,
        domain: str,
        product_category: str = "",
        metric: str = "",
    ) -> list[str]:
        return await self._repo.search_actions_by_product_and_metric(
            org_id=self._org_id,
            domain=normalize_name(domain),
            product_category=normalize_name(product_category),
            metric=normalize_name(metric),
        )

    async def search_risks_by_defect(self, domain: str, defect_type: str) -> list[str]:
        return await self._repo.search_risks_by_defect(
            org_id=self._org_id,
            domain=normalize_name(domain),
            defect_type=normalize_name(defect_type),
        )

    async def search_actions_by_defect(self, domain: str, defect_type: str) -> list[str]:
        return await self._repo.search_actions_by_defect(
            org_id=self._org_id,
            domain=normalize_name(domain),
            defect_type=normalize_name(defect_type),
        )

    async def search_standards_by_product(self, domain: str, product_category: str) -> list[str]:
        return await self._repo.search_standards_by_product(
            org_id=self._org_id,
            domain=normalize_name(domain),
            product_category=normalize_name(product_category),
        )

    async def search_clauses_by_standard(self, domain: str, standard: str) -> list[str]:
        return await self._repo.search_clauses_by_standard(
            org_id=self._org_id,
            domain=normalize_name(domain),
            standard=normalize_name(standard),
        )

    async def search_items_by_clause(self, domain: str, standard_clause: str) -> list[str]:
        return await self._repo.search_items_by_clause(
            org_id=self._org_id,
            domain=normalize_name(domain),
            standard_clause=normalize_name(standard_clause),
        )

    async def search_metrics_by_item(self, domain: str, inspection_item: str) -> list[str]:
        return await self._repo.search_metrics_by_item(
            org_id=self._org_id,
            domain=normalize_name(domain),
            inspection_item=normalize_name(inspection_item),
        )

    async def search_defects_by_metric(self, domain: str, metric: str) -> list[str]:
        return await self._repo.search_defects_by_metric(
            org_id=self._org_id,
            domain=normalize_name(domain),
            metric=normalize_name(metric),
        )

    async def search_causes_by_defect(self, domain: str, defect_type: str) -> list[str]:
        return await self._repo.search_causes_by_defect(
            org_id=self._org_id,
            domain=normalize_name(domain),
            defect_type=normalize_name(defect_type),
        )

    async def search_chain_paths_by_product(self, domain: str, product_category: str) -> list[dict]:
        return await self._repo.search_chain_paths_by_product(
            org_id=self._org_id,
            domain=normalize_name(domain),
            product_category=normalize_name(product_category),
        )

    async def delete_relationship(self, payload: QualityKgRelationshipDelete) -> int:
        if not self._org_id:
            raise ValidationError("org_id is required for quality knowledge graph deletes")
        return await self._repo.delete_relationship(
            org_id=self._org_id,
            relation_type=payload.relation_type,
            start_node_id=payload.start_node_id,
            end_node_id=payload.end_node_id,
            domain=normalize_name(payload.domain),
            product_category=normalize_name(payload.product_category),
        )

    async def delete_node(self, payload: QualityKgNodeDelete) -> int:
        if not self._org_id:
            raise ValidationError("org_id is required for quality knowledge graph deletes")
        return await self._repo.delete_node(org_id=self._org_id, node_id=payload.node_id)

    async def ingest_completed_result(self, result: object) -> int:
        chains = extract_quality_kg_chains(result)
        if not chains:
            return 0
        await self.ingest_chains([QualityKnowledgeChain(**item) for item in chains])
        return len(chains)

    async def _ingest_validated_chain(self, chain: QualityKnowledgeChain) -> None:
        self._validate_chain(chain)
        nodes, node_by_key = self._build_nodes(chain)
        relationships = self._build_relationships(chain, node_by_key)
        await self._repo.ingest_chain(nodes=nodes, relationships=relationships)

    def _validate_chain(self, chain: QualityKnowledgeChain) -> None:
        if not self._org_id:
            raise ValidationError("org_id is required for quality knowledge graph writes")
        populated = sum(1 for field in _CORE_OPTIONAL_FIELDS if getattr(chain, field))
        if populated < 2:
            raise ValidationError(
                "quality knowledge chain must contain at least two of standard, "
                "inspection_item, metric, defect_type"
            )
        for value in self._iter_names(chain):
            if len(value) > 80:
                raise ValidationError("quality knowledge graph node names must be 80 characters or fewer")
            if len(value) > 36 and any(marker in value for marker in _SENTENCE_MARKERS):
                raise ValidationError("quality knowledge graph node names must be short reusable terms")

    def _build_nodes(
        self,
        chain: QualityKnowledgeChain,
    ) -> tuple[list[QualityKgNode], dict[tuple[str, str], QualityKgNode]]:
        domain = normalize_name(chain.domain)
        node_by_key: dict[tuple[str, str], QualityKgNode] = {}

        def add_node(node_type: str, name: str | None) -> QualityKgNode | None:
            if not name:
                return None
            normalized = normalize_name(name)
            key = (node_type, normalized)
            if key in node_by_key:
                return node_by_key[key]
            node = QualityKgNode(
                id=make_node_id(self._org_id, node_type, domain, normalized),
                org_id=self._org_id,
                type=node_type,
                name=compact_name(name),
                normalized_name=normalized,
                domain=domain,
            )
            node_by_key[key] = node
            return node

        add_node("DetectionDomain", chain.domain)
        add_node("ProductCategory", chain.product_category)
        add_node("Standard", chain.standard)
        add_node("StandardClause", chain.standard_clause)
        add_node("InspectionItem", chain.inspection_item)
        add_node("Metric", chain.metric)
        add_node("DefectType", chain.defect_type)
        add_node("RiskType", chain.risk_type)
        add_node("Cause", chain.cause)
        for action in chain.actions:
            add_node("Action", action)

        return list(node_by_key.values()), node_by_key

    def _build_relationships(
        self,
        chain: QualityKnowledgeChain,
        node_by_key: dict[tuple[str, str], QualityKgNode],
    ) -> list[QualityKgRelationship]:
        domain = normalize_name(chain.domain)
        product_category = normalize_name(chain.product_category)
        relationships: list[QualityKgRelationship] = []

        def node(node_type: str, name: str | None) -> QualityKgNode | None:
            return node_by_key.get((node_type, normalize_name(name))) if name else None

        def add_rel(rel_type: str, start: QualityKgNode | None, end: QualityKgNode | None) -> None:
            if not start or not end:
                return
            relationships.append(
                QualityKgRelationship(
                    type=rel_type,
                    start_node_id=start.id,
                    end_node_id=end.id,
                    org_id=self._org_id,
                    domain=domain,
                    product_category=product_category,
                    confidence=chain.confidence,
                    source=chain.source,
                )
            )

        domain_node = node("DetectionDomain", chain.domain)
        product_node = node("ProductCategory", chain.product_category)
        standard_node = node("Standard", chain.standard)
        clause_node = node("StandardClause", chain.standard_clause)
        item_node = node("InspectionItem", chain.inspection_item)
        metric_node = node("Metric", chain.metric)
        defect_node = node("DefectType", chain.defect_type)
        risk_node = node("RiskType", chain.risk_type)
        cause_node = node("Cause", chain.cause)

        add_rel("HAS_CATEGORY", domain_node, product_node)
        add_rel("APPLIES_STANDARD", product_node, standard_node)
        add_rel("HAS_CLAUSE", standard_node, clause_node)
        add_rel("REQUIRES_ITEM", clause_node, item_node)
        add_rel("HAS_METRIC", item_node, metric_node)
        add_rel("INDICATES_DEFECT", metric_node, defect_node)
        add_rel("LEADS_TO_RISK", defect_node, risk_node)
        add_rel("MAY_BE_CAUSED_BY", defect_node, cause_node)

        for action in chain.actions:
            action_node = node("Action", action)
            add_rel("CAUSE_HANDLED_BY", cause_node, action_node)
            add_rel("RISK_REQUIRES_ACTION", risk_node, action_node)
            add_rel("DEFECT_SUGGESTS_ACTION", defect_node, action_node)
            add_rel("METRIC_ABNORMAL_ACTION", metric_node, action_node)
            add_rel("ITEM_DIRECT_ACTION", item_node, action_node)

        return relationships

    def _iter_names(self, chain: QualityKnowledgeChain):
        for value in (
            chain.domain,
            chain.product_category,
            chain.standard,
            chain.standard_clause,
            chain.inspection_item,
            chain.metric,
            chain.defect_type,
            chain.risk_type,
            chain.cause,
            *chain.actions,
        ):
            if value:
                yield compact_name(value)


def compact_name(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def normalize_name(value: str | None) -> str:
    text = compact_name(value)
    return text.casefold()


def make_node_id(org_id: str, node_type: str, domain: str, normalized_name: str) -> str:
    return f"qkg:{org_id}:{node_type}:{domain}:{normalized_name}"


def extract_quality_kg_chains(result: object) -> list[dict]:
    payload = _object_to_mapping(result)
    reasoning_chain = _object_to_mapping(payload.get("reasoning_chain"))
    candidates = (
        payload.get("quality_kg_chains"),
        payload.get("quality_knowledge_chains"),
        reasoning_chain.get("quality_kg_chains"),
        reasoning_chain.get("quality_knowledge_chains"),
        _object_to_mapping(reasoning_chain.get("quality_kg")).get("items"),
    )
    for candidate in candidates:
        if isinstance(candidate, list):
            return [dict(item) for item in candidate if isinstance(item, dict)]
    return derive_quality_kg_chains(payload, reasoning_chain)


def derive_quality_kg_chains(payload: dict, reasoning_chain: dict | None = None) -> list[dict]:
    reasoning = _object_to_mapping(reasoning_chain if reasoning_chain is not None else payload.get("reasoning_chain"))
    standard_evaluation = _object_to_mapping(reasoning.get("standard_evaluation"))
    structured_record = _object_to_mapping(reasoning.get("structured_record"))
    spec = _object_to_mapping(standard_evaluation.get("spec"))
    if not standard_evaluation:
        return []

    product_family = _first_text(
        structured_record.get("product_family"),
        structured_record.get("category"),
        spec.get("product_family"),
        payload.get("product_family"),
    )
    domain = _first_text(
        structured_record.get("domain"),
        structured_record.get("detection_domain"),
        spec.get("domain"),
        _DOMAIN_BY_PRODUCT_FAMILY.get(product_family.casefold()),
        product_family,
        "通用质量检测",
    )
    product_category = _first_text(
        structured_record.get("product_category"),
        structured_record.get("category"),
        product_family,
        spec.get("product_id"),
        payload.get("product_id"),
        "通用产品",
    )
    standard = _first_text(
        spec.get("spec_code"),
        payload.get("spec_code"),
        spec.get("name"),
        structured_record.get("spec_code"),
    )

    chains: list[dict] = []
    for rule in list(standard_evaluation.get("matched_rules") or []):
        rule_map = _object_to_mapping(rule)
        defect_type = _first_text(rule_map.get("defect_type"))
        if not defect_type:
            continue
        chains.append(
            _build_derived_chain(
                domain=domain,
                product_category=product_category,
                standard=standard,
                defect_type=defect_type,
                zone_name=_first_text(rule_map.get("zone_name")),
                severity=_first_text(rule_map.get("severity"), "major"),
                disposition=_first_text(rule_map.get("disposition"), "manual_required"),
                confidence=_float_or_default(rule_map.get("confidence"), 1.0),
            )
        )

    for defect_type in list(standard_evaluation.get("unmatched_defects") or []):
        defect = _first_text(defect_type)
        if not defect:
            continue
        chains.append(
            _build_derived_chain(
                domain=domain,
                product_category=product_category,
                standard=standard,
                defect_type=defect,
                zone_name="",
                severity="unknown",
                disposition="manual_required",
                confidence=1.0,
            )
        )

    return list(_dedupe_chains(chains))


def _object_to_mapping(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    return {
        key: getattr(value, key)
        for key in ("reasoning_chain", "quality_kg_chains", "quality_knowledge_chains")
        if hasattr(value, key)
    }


def _build_derived_chain(
    *,
    domain: str,
    product_category: str,
    standard: str,
    defect_type: str,
    zone_name: str,
    severity: str,
    disposition: str,
    confidence: float,
) -> dict[str, Any]:
    segments = [segment for segment in defect_type.split(".") if segment]
    inspection_item = zone_name or (segments[-2] if len(segments) >= 2 else defect_type)
    metric = segments[-1] if segments else defect_type
    action = _ACTION_BY_DISPOSITION.get(disposition.casefold(), "人工复核")
    return {
        "domain": domain,
        "product_category": product_category,
        "standard": standard or None,
        "inspection_item": inspection_item,
        "metric": metric,
        "defect_type": defect_type,
        "risk_type": f"{severity.casefold()}_quality_risk",
        "actions": [action],
        "confidence": max(0.0, min(1.0, confidence)),
        "source": "standard_evaluation",
    }


def _dedupe_chains(chains: list[dict]):
    seen: set[tuple] = set()
    for chain in chains:
        key = (
            chain.get("domain"),
            chain.get("product_category"),
            chain.get("standard"),
            chain.get("inspection_item"),
            chain.get("metric"),
            chain.get("defect_type"),
            chain.get("risk_type"),
            tuple(chain.get("actions") or []),
        )
        if key in seen:
            continue
        seen.add(key)
        yield chain


def _first_text(*values: object) -> str:
    for value in values:
        text = compact_name(value)
        if text:
            return text
    return ""


def _float_or_default(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
