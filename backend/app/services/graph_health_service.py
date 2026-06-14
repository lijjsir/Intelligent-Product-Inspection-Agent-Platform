from app.core.config import settings
from app.services.neo4j_memory_graph_store import Neo4jMemoryGraphStore


class GraphHealthService:
    async def assert_neo4j_ready(self) -> None:
        if not settings.neo4j_enabled:
            raise RuntimeError("Neo4j is required but neo4j_enabled=False")

        store = Neo4jMemoryGraphStore(
            uri=settings.neo4j_uri,
            username=settings.neo4j_username,
            password=settings.neo4j_password,
            database=settings.neo4j_database,
        )
        try:
            await store.verify_connectivity()
            await store.ensure_schema()
        except Exception as exc:
            raise RuntimeError(f"Neo4j connectivity check failed: {exc}") from exc
