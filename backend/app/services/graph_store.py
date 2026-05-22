from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.core.config import settings

try:
    from neo4j import GraphDatabase
except Exception:  # pragma: no cover - optional dependency for local dev
    GraphDatabase = None


@dataclass(slots=True)
class GraphNodePayload:
    id: str
    dataset_id: str
    knowledge_graph_id: str
    name: str
    entity_type: str
    description: str | None
    properties_json: dict[str, Any]
    confidence: float | None


@dataclass(slots=True)
class GraphEdgePayload:
    id: str
    dataset_id: str
    knowledge_graph_id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    properties_json: dict[str, Any]
    confidence: float | None


class GraphStore(Protocol):
    enabled: bool

    def reset_graph(self, *, dataset_id: str, knowledge_graph_id: str) -> None:
        ...

    def upsert_entity(self, payload: GraphNodePayload) -> None:
        ...

    def upsert_relation(self, payload: GraphEdgePayload) -> None:
        ...

    def delete_entity(self, *, entity_id: str) -> None:
        ...

    def delete_relation(self, *, relation_id: str) -> None:
        ...


class NullGraphStore:
    enabled = False

    def reset_graph(self, *, dataset_id: str, knowledge_graph_id: str) -> None:
        return None

    def upsert_entity(self, payload: GraphNodePayload) -> None:
        return None

    def upsert_relation(self, payload: GraphEdgePayload) -> None:
        return None

    def delete_entity(self, *, entity_id: str) -> None:
        return None

    def delete_relation(self, *, relation_id: str) -> None:
        return None


class Neo4jGraphStore:
    enabled = True

    def __init__(
        self,
        *,
        uri: str,
        username: str,
        password: str,
        database: str,
        driver=None,
    ):
        if GraphDatabase is None and driver is None:
            raise RuntimeError("neo4j driver is not installed")
        self._database = database
        self._driver = driver or GraphDatabase.driver(uri, auth=(username, password))

    def reset_graph(self, *, dataset_id: str, knowledge_graph_id: str) -> None:
        query = """
        MATCH (n {dataset_id: $dataset_id, knowledge_graph_id: $knowledge_graph_id})
        DETACH DELETE n
        """
        self._execute(query, {"dataset_id": dataset_id, "knowledge_graph_id": knowledge_graph_id})

    def upsert_entity(self, payload: GraphNodePayload) -> None:
        query = """
        MERGE (n:Entity {id: $id})
        SET n.dataset_id = $dataset_id,
            n.knowledge_graph_id = $knowledge_graph_id,
            n.name = $name,
            n.entity_type = $entity_type,
            n.description = $description,
            n.properties_json = $properties_json,
            n.confidence = $confidence
        """
        self._execute(
            query,
            {
                "id": payload.id,
                "dataset_id": payload.dataset_id,
                "knowledge_graph_id": payload.knowledge_graph_id,
                "name": payload.name,
                "entity_type": payload.entity_type,
                "description": payload.description,
                "properties_json": payload.properties_json,
                "confidence": payload.confidence,
            },
        )

    def upsert_relation(self, payload: GraphEdgePayload) -> None:
        query = """
        MATCH (s:Entity {id: $source_entity_id})
        MATCH (t:Entity {id: $target_entity_id})
        MERGE (s)-[r:RELATED {id: $id}]->(t)
        SET r.dataset_id = $dataset_id,
            r.knowledge_graph_id = $knowledge_graph_id,
            r.relation_type = $relation_type,
            r.properties_json = $properties_json,
            r.confidence = $confidence
        """
        self._execute(
            query,
            {
                "id": payload.id,
                "dataset_id": payload.dataset_id,
                "knowledge_graph_id": payload.knowledge_graph_id,
                "source_entity_id": payload.source_entity_id,
                "target_entity_id": payload.target_entity_id,
                "relation_type": payload.relation_type,
                "properties_json": payload.properties_json,
                "confidence": payload.confidence,
            },
        )

    def delete_entity(self, *, entity_id: str) -> None:
        self._execute("MATCH (n:Entity {id: $id}) DETACH DELETE n", {"id": entity_id})

    def delete_relation(self, *, relation_id: str) -> None:
        self._execute("MATCH ()-[r:RELATED {id: $id}]->() DELETE r", {"id": relation_id})

    def _execute(self, query: str, params: dict[str, Any]) -> None:
        with self._driver.session(database=self._database) as session:
            session.run(query, params)


def build_graph_store() -> GraphStore:
    if not settings.neo4j_enabled:
        return NullGraphStore()
    return Neo4jGraphStore(
        uri=settings.neo4j_uri,
        username=settings.neo4j_username,
        password=settings.neo4j_password,
        database=settings.neo4j_database,
    )
