"""MemoryGraphStore — abstract interface for memory relationship graph operations."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(slots=True)
class MemoryGraphNode:
    memory_id: str
    org_id: str
    memory_type: str = ""
    status: str = "active"
    trust_score: float = 0.0
    confidence: float = 0.0
    scope_key: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class MemoryGraphEdge:
    org_id: str
    source_memory_id: str
    target_memory_id: str
    edge_type: str
    strength: float = 1.0
    trace_id: str | None = None
    reason: str | None = None
    metadata_json: dict | None = None
    created_at: str = ""


class MemoryGraphStore(ABC):
    """Abstract interface for memory relationship graph operations."""

    @abstractmethod
    async def upsert_memory_node(self, node: MemoryGraphNode) -> None:
        ...

    @abstractmethod
    async def upsert_rag_chunk_node(self, org_id: str, chunk_id: str, rag_space_id: str = "",
                                     document_id: str = "", title: str = "", page_number: int = 0) -> None:
        ...

    @abstractmethod
    async def create_memory_edge(self, edge: MemoryGraphEdge) -> None:
        ...

    @abstractmethod
    async def create_memory_rag_edge(self, memory_id: str, chunk_id: str, edge_type: str,
                                      confidence: float = 1.0, org_id: str = "") -> None:
        ...

    @abstractmethod
    async def build_propagation_graph(self, org_id: str, root_memory_id: str,
                                       edge_types: list[str] | None = None,
                                       max_depth: int = 4) -> list[dict]:
        ...

    @abstractmethod
    async def trace_provenance(self, org_id: str, memory_id: str) -> list[dict]:
        ...

    @abstractmethod
    async def find_conflict_chain(self, org_id: str, memory_id: str) -> list[dict]:
        ...

    @abstractmethod
    async def create_event_memory_edge(self, org_id: str, event_id: str, memory_id: str,
                                        edge_type: str, trace_id: str = "") -> None:
        ...

    @abstractmethod
    async def create_agent_memory_edge(self, org_id: str, trace_id: str, memory_id: str,
                                        edge_type: str, agent_id: str = "", task_id: str = "") -> None:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...

    @abstractmethod
    async def list_downstream_memories(
        self, *, org_id: str, root_memory_id: str,
        edge_types: list[str], max_depth: int,
    ) -> list[dict]: ...

    @abstractmethod
    async def list_upstream_memories(
        self, *, org_id: str, memory_id: str,
        edge_types: list[str] | None = None, max_depth: int = 4,
    ) -> list[dict]: ...

    @abstractmethod
    async def list_conflict_edges(
        self, *, org_id: str, memory_id: str | None = None,
        include_resolved: bool = False,
    ) -> list[dict]: ...

    @abstractmethod
    async def soft_delete_memory_edges(
        self, *, org_id: str, memory_id: str,
        edge_types: list[str] | None = None,
    ) -> int: ...

    @abstractmethod
    async def mark_conflict_resolved(
        self, *, org_id: str, source_memory_id: str,
        target_memory_id: str, resolution: str, resolved_by: str,
    ) -> None: ...


class MySQLMemoryGraphStore(MemoryGraphStore):
    """MySQL-backed implementation using existing MemoryDependencyRepository."""

    def __init__(self, session, org_id: str):
        self._session = session
        self._org_id = org_id

    async def upsert_memory_node(self, node: MemoryGraphNode) -> None:
        return None

    async def upsert_rag_chunk_node(self, org_id: str, chunk_id: str, **kwargs) -> None:
        return None

    async def create_memory_edge(self, edge: MemoryGraphEdge) -> None:
        # MySQL memory_dependency_edges table was dropped (migrated to Neo4j).
        # The DualWriteMemoryGraphStore still calls this for dual-write; skip safely.
        return None

    async def create_memory_rag_edge(self, memory_id: str, chunk_id: str, edge_type: str,
                                      confidence: float = 1.0, org_id: str = "") -> None:
        return None

    async def build_propagation_graph(self, org_id: str, root_memory_id: str,
                                       edge_types: list[str] | None = None,
                                       max_depth: int = 4) -> list[dict]:
        from app.services.memory_governance_service import MemoryPropagationService
        svc = MemoryPropagationService(self._session, org_id)
        result = await svc.build_propagation_graph(root_memory_id, max_depth=max_depth)
        return [n.model_dump() for n in result.nodes]

    async def trace_provenance(self, org_id: str, memory_id: str) -> list[dict]:
        from app.services.memory_governance_service import MemoryProvenanceService
        svc = MemoryProvenanceService(self._session, org_id)
        result = await svc.trace_provenance(memory_id)
        return [result]

    async def find_conflict_chain(self, org_id: str, memory_id: str) -> list[dict]:
        # memory_dependency_edges table was dropped (migrated to Neo4j).
        # Conflict chains are resolved in Neo4jMemoryGraphStore.
        return []

    async def create_event_memory_edge(self, org_id: str, event_id: str, memory_id: str,
                                        edge_type: str, trace_id: str = "") -> None:
        return None  # Events are recorded via MemoryEventRepository in MySQL

    async def create_agent_memory_edge(self, org_id: str, trace_id: str, memory_id: str,
                                        edge_type: str, agent_id: str = "", task_id: str = "") -> None:
        return None  # Agent run edges are not stored in MySQL dependency table

    async def health_check(self) -> bool:
        return True

    async def list_downstream_memories(self, *, org_id, root_memory_id, edge_types, max_depth):
        return []

    async def list_upstream_memories(self, *, org_id, memory_id, edge_types=None, max_depth=4):
        return []

    async def list_conflict_edges(self, *, org_id, memory_id=None, include_resolved=False):
        return []

    async def soft_delete_memory_edges(self, *, org_id, memory_id, edge_types=None):
        return 0

    async def mark_conflict_resolved(self, *, org_id, source_memory_id, target_memory_id, resolution, resolved_by):
        pass
