from __future__ import annotations

from typing import Any

from app.services.quality_kg_schema import (
    NODE_TYPES,
    QKG_NODE_LABELS,
    RELATION_TYPES,
    QualityKgNode,
    QualityKgRelationship,
)

try:
    from neo4j import AsyncGraphDatabase
except Exception:
    AsyncGraphDatabase = None


class Neo4jQualityKgRepository:
    def __init__(self, uri: str, username: str, password: str, database: str = "neo4j"):
        if AsyncGraphDatabase is None:
            raise RuntimeError("neo4j driver is not installed")
        self._database = database
        self._driver = AsyncGraphDatabase.driver(uri, auth=(username, password))

    async def ensure_schema(self) -> None:
        cyphers = [
            *[
                f"CREATE CONSTRAINT {to_snake(node_label(node_type))}_id IF NOT EXISTS "
                f"FOR (n:{node_label(node_type)}) REQUIRE n.id IS UNIQUE"
                for node_type in NODE_TYPES
            ],
            "CREATE INDEX qkg_product_category_name IF NOT EXISTS FOR (n:QkgProductCategory) ON (n.name)",
            "CREATE INDEX qkg_metric_name IF NOT EXISTS FOR (n:QkgMetric) ON (n.name)",
            "CREATE INDEX qkg_defect_type_name IF NOT EXISTS FOR (n:QkgDefectType) ON (n.name)",
            "CREATE INDEX qkg_action_name IF NOT EXISTS FOR (n:QkgAction) ON (n.name)",
        ]
        async with self._driver.session(database=self._database) as session:
            for cypher in cyphers:
                await session.run(cypher)

    async def ingest_chain(
        self,
        *,
        nodes: list[QualityKgNode],
        relationships: list[QualityKgRelationship],
    ) -> None:
        for node in nodes:
            await self._merge_node(node)
        for relationship in relationships:
            await self._merge_relationship(relationship)

    async def search_actions_by_product_and_metric(
        self,
        *,
        org_id: str,
        domain: str,
        product_category: str = "",
        metric: str,
    ) -> list[str]:
        records = await self._execute_read(
            """
            MATCH (m:QkgMetric {org_id: $org_id, normalized_name: $metric, domain: $domain})
            WITH
              [(m)-[mr:METRIC_ABNORMAL_ACTION]->(a:QkgAction)
                WHERE $product_category = '' OR mr.product_category = $product_category | a.name] AS direct_actions,
              [(m)-[idr:INDICATES_DEFECT]->(:QkgDefectType)-[ds:DEFECT_SUGGESTS_ACTION]->(a:QkgAction)
                WHERE $product_category = ''
                   OR (idr.product_category = $product_category AND ds.product_category = $product_category) | a.name] AS defect_actions,
              [(m)-[idr:INDICATES_DEFECT]->(:QkgDefectType)-[lr:LEADS_TO_RISK]->(:QkgRiskType)-[rr:RISK_REQUIRES_ACTION]->(a:QkgAction)
                WHERE $product_category = ''
                   OR (idr.product_category = $product_category AND lr.product_category = $product_category AND rr.product_category = $product_category) | a.name] AS risk_actions,
              [(m)-[idr:INDICATES_DEFECT]->(:QkgDefectType)-[dc:MAY_BE_CAUSED_BY]->(:QkgCause)-[ch:CAUSE_HANDLED_BY]->(a:QkgAction)
                WHERE $product_category = ''
                   OR (idr.product_category = $product_category AND dc.product_category = $product_category AND ch.product_category = $product_category) | a.name] AS cause_actions
            UNWIND direct_actions + defect_actions + risk_actions + cause_actions AS action
            RETURN DISTINCT action AS action
            ORDER BY action
            """,
            {
                "org_id": org_id,
                "domain": domain,
                "product_category": product_category,
                "metric": metric,
            },
        )
        return _string_values(records, "action")

    async def search_risks_by_defect(
        self,
        *,
        org_id: str,
        domain: str,
        defect_type: str,
    ) -> list[str]:
        records = await self._execute_read(
            """
            MATCH (d:QkgDefectType {org_id: $org_id, normalized_name: $defect_type, domain: $domain})
            MATCH (d)-[:LEADS_TO_RISK]->(r:QkgRiskType {org_id: $org_id, domain: $domain})
            RETURN DISTINCT r.name AS risk
            ORDER BY risk
            """,
            {"org_id": org_id, "domain": domain, "defect_type": defect_type},
        )
        return _string_values(records, "risk")

    async def search_actions_by_defect(
        self,
        *,
        org_id: str,
        domain: str,
        defect_type: str,
    ) -> list[str]:
        records = await self._execute_read(
            """
            MATCH (d:QkgDefectType {org_id: $org_id, normalized_name: $defect_type, domain: $domain})
            OPTIONAL MATCH (d)-[:DEFECT_SUGGESTS_ACTION]->(da:QkgAction)
            OPTIONAL MATCH (d)-[:LEADS_TO_RISK]->(:QkgRiskType)-[:RISK_REQUIRES_ACTION]->(ra:QkgAction)
            OPTIONAL MATCH (d)-[:MAY_BE_CAUSED_BY]->(:QkgCause)-[:CAUSE_HANDLED_BY]->(ca:QkgAction)
            WITH [action IN [da, ra, ca] WHERE action IS NOT NULL] AS actions
            UNWIND actions AS action
            RETURN DISTINCT action.name AS action
            ORDER BY action
            """,
            {"org_id": org_id, "domain": domain, "defect_type": defect_type},
        )
        return _string_values(records, "action")

    async def search_standards_by_product(
        self,
        *,
        org_id: str,
        domain: str,
        product_category: str,
    ) -> list[str]:
        records = await self._execute_read(
            """
            MATCH (p:QkgProductCategory {org_id: $org_id, normalized_name: $product_category, domain: $domain})
            MATCH (p)-[:APPLIES_STANDARD]->(s:QkgStandard {org_id: $org_id, domain: $domain})
            RETURN DISTINCT s.name AS standard
            ORDER BY standard
            """,
            {"org_id": org_id, "domain": domain, "product_category": product_category},
        )
        return _string_values(records, "standard")

    async def search_clauses_by_standard(
        self,
        *,
        org_id: str,
        domain: str,
        standard: str,
    ) -> list[str]:
        records = await self._execute_read(
            """
            MATCH (s:QkgStandard {org_id: $org_id, normalized_name: $standard, domain: $domain})
            MATCH (s)-[:HAS_CLAUSE]->(c:QkgStandardClause {org_id: $org_id, domain: $domain})
            RETURN DISTINCT c.name AS clause
            ORDER BY clause
            """,
            {"org_id": org_id, "domain": domain, "standard": standard},
        )
        return _string_values(records, "clause")

    async def search_items_by_clause(
        self,
        *,
        org_id: str,
        domain: str,
        standard_clause: str,
    ) -> list[str]:
        records = await self._execute_read(
            """
            MATCH (c:QkgStandardClause {org_id: $org_id, normalized_name: $standard_clause, domain: $domain})
            MATCH (c)-[:REQUIRES_ITEM]->(i:QkgInspectionItem {org_id: $org_id, domain: $domain})
            RETURN DISTINCT i.name AS item
            ORDER BY item
            """,
            {"org_id": org_id, "domain": domain, "standard_clause": standard_clause},
        )
        return _string_values(records, "item")

    async def search_metrics_by_item(
        self,
        *,
        org_id: str,
        domain: str,
        inspection_item: str,
    ) -> list[str]:
        records = await self._execute_read(
            """
            MATCH (i:QkgInspectionItem {org_id: $org_id, normalized_name: $inspection_item, domain: $domain})
            MATCH (i)-[:HAS_METRIC]->(m:QkgMetric {org_id: $org_id, domain: $domain})
            RETURN DISTINCT m.name AS metric
            ORDER BY metric
            """,
            {"org_id": org_id, "domain": domain, "inspection_item": inspection_item},
        )
        return _string_values(records, "metric")

    async def search_defects_by_metric(
        self,
        *,
        org_id: str,
        domain: str,
        metric: str,
    ) -> list[str]:
        records = await self._execute_read(
            """
            MATCH (m:QkgMetric {org_id: $org_id, normalized_name: $metric, domain: $domain})
            MATCH (m)-[:INDICATES_DEFECT]->(d:QkgDefectType {org_id: $org_id, domain: $domain})
            RETURN DISTINCT d.name AS defect
            ORDER BY defect
            """,
            {"org_id": org_id, "domain": domain, "metric": metric},
        )
        return _string_values(records, "defect")

    async def search_causes_by_defect(
        self,
        *,
        org_id: str,
        domain: str,
        defect_type: str,
    ) -> list[str]:
        records = await self._execute_read(
            """
            MATCH (d:QkgDefectType {org_id: $org_id, normalized_name: $defect_type, domain: $domain})
            MATCH (d)-[:MAY_BE_CAUSED_BY]->(c:QkgCause {org_id: $org_id, domain: $domain})
            RETURN DISTINCT c.name AS cause
            ORDER BY cause
            """,
            {"org_id": org_id, "domain": domain, "defect_type": defect_type},
        )
        return _string_values(records, "cause")

    async def search_chain_paths_by_product(
        self,
        *,
        org_id: str,
        domain: str,
        product_category: str,
    ) -> list[dict]:
        records = await self._execute_read(
            """
            MATCH (p:QkgProductCategory {org_id: $org_id, normalized_name: $product_category, domain: $domain})
            MATCH (p)-[:APPLIES_STANDARD]->(s:QkgStandard {org_id: $org_id, domain: $domain})
                  -[:HAS_CLAUSE]->(c:QkgStandardClause {org_id: $org_id, domain: $domain})
                  -[:REQUIRES_ITEM]->(i:QkgInspectionItem {org_id: $org_id, domain: $domain})
                  -[:HAS_METRIC]->(m:QkgMetric {org_id: $org_id, domain: $domain})
            OPTIONAL MATCH (m)-[:INDICATES_DEFECT]->(d:QkgDefectType {org_id: $org_id, domain: $domain})
            OPTIONAL MATCH (d)-[:LEADS_TO_RISK]->(r:QkgRiskType {org_id: $org_id, domain: $domain})
            OPTIONAL MATCH (d)-[:MAY_BE_CAUSED_BY]->(cause:QkgCause {org_id: $org_id, domain: $domain})
            OPTIONAL MATCH (d)-[:DEFECT_SUGGESTS_ACTION]->(action:QkgAction {org_id: $org_id, domain: $domain})
            RETURN
              s.name AS standard,
              c.name AS standard_clause,
              i.name AS inspection_item,
              m.name AS metric,
              d.name AS defect_type,
              r.name AS risk_type,
              collect(DISTINCT cause.name) AS causes,
              collect(DISTINCT action.name) AS actions
            ORDER BY standard, standard_clause, inspection_item, metric
            LIMIT 500
            """,
            {"org_id": org_id, "domain": domain, "product_category": product_category},
        )
        return [dict(record) for record in records]

    async def delete_relationship(
        self,
        *,
        org_id: str,
        relation_type: str,
        start_node_id: str,
        end_node_id: str,
        domain: str,
        product_category: str = "",
    ) -> int:
        relationship_type = validate_relationship_type(relation_type)
        records = await self._execute_read(
            f"""
            MATCH (src {{id: $start_node_id}})-[r:{relationship_type} {{
                org_id: $org_id,
                start_node_id: $start_node_id,
                end_node_id: $end_node_id,
                domain: $domain,
                product_category: $product_category
            }}]->(dst {{id: $end_node_id}})
            WITH r
            DELETE r
            RETURN count(*) AS deleted
            """,
            {
                "org_id": org_id,
                "start_node_id": start_node_id,
                "end_node_id": end_node_id,
                "domain": domain,
                "product_category": product_category,
            },
        )
        return int(records[0]["deleted"]) if records else 0

    async def delete_node(self, *, org_id: str, node_id: str) -> int:
        records = await self._execute_read(
            """
            MATCH (n {org_id: $org_id, id: $node_id})
            WITH n
            DETACH DELETE n
            RETURN count(*) AS deleted
            """,
            {"org_id": org_id, "node_id": node_id},
        )
        return int(records[0]["deleted"]) if records else 0

    async def _merge_node(self, node: QualityKgNode) -> None:
        label = node_label(node.type)
        await self._execute(
            f"""
            MERGE (n:{label} {{id: $id}})
            SET n.org_id = $org_id,
                n.name = $name,
                n.normalized_name = $normalized_name,
                n.domain = $domain,
                n.type = $type,
                n.created_at = coalesce(n.created_at, datetime()),
                n.updated_at = datetime()
            """,
            {
                "id": node.id,
                "org_id": node.org_id,
                "name": node.name,
                "normalized_name": node.normalized_name,
                "domain": node.domain,
                "type": node.type,
            },
        )

    async def _merge_relationship(self, relationship: QualityKgRelationship) -> None:
        relationship_type = validate_relationship_type(relationship.type)
        await self._execute(
            f"""
            MATCH (src {{id: $start_node_id}})
            MATCH (dst {{id: $end_node_id}})
            MERGE (src)-[r:{relationship_type} {{
                org_id: $org_id,
                start_node_id: $start_node_id,
                end_node_id: $end_node_id,
                domain: $domain,
                product_category: $product_category
            }}]->(dst)
            SET r.confidence = CASE
                    WHEN r.confidence IS NULL OR r.confidence < $confidence THEN $confidence
                    ELSE r.confidence
                END,
                r.count = coalesce(r.count, 0) + 1,
                r.source = $source,
                r.created_at = coalesce(r.created_at, datetime()),
                r.updated_at = datetime()
            """,
            {
                "org_id": relationship.org_id,
                "start_node_id": relationship.start_node_id,
                "end_node_id": relationship.end_node_id,
                "domain": relationship.domain,
                "product_category": relationship.product_category,
                "confidence": relationship.confidence,
                "source": relationship.source,
            },
        )

    async def _execute(self, query: str, params: dict[str, Any]) -> None:
        async def _run(tx, q, p):
            result = await tx.run(q, p)
            await result.consume()

        async with self._driver.session(database=self._database) as session:
            await session.execute_write(_run, query, params)

    async def _execute_read(self, query: str, params: dict[str, Any]) -> list[Any]:
        async def _run(tx, q, p):
            result = await tx.run(q, p)
            return [record async for record in result]

        async with self._driver.session(database=self._database) as session:
            return await session.execute_read(_run, query, params)


def validate_node_type(node_type: str) -> str:
    if node_type not in NODE_TYPES:
        raise ValueError(f"Unsupported quality KG node type: {node_type}")
    return node_type


def node_label(node_type: str) -> str:
    return QKG_NODE_LABELS[validate_node_type(node_type)]


def validate_relationship_type(relationship_type: str) -> str:
    if relationship_type not in RELATION_TYPES:
        raise ValueError(f"Unsupported quality KG relationship type: {relationship_type}")
    return relationship_type


def to_snake(value: str) -> str:
    chars: list[str] = []
    for index, char in enumerate(value):
        if char.isupper() and index > 0:
            chars.append("_")
        chars.append(char.lower())
    return "".join(chars)


def _string_values(records: list[Any], key: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for record in records:
        value = record[key]
        if value and value not in seen:
            values.append(str(value))
            seen.add(str(value))
    return values
