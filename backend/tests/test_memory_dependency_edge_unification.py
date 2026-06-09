"""Tests for MemoryDependencyEdge unification."""
import pytest
from app.schemas.memory import (
    EdgeType,
    MemoryDependencyInput,
    MemoryWriteRequest,
    MemorySource,
    MemoryContent,
    MemoryType,
    ConflictRelation,
)


class TestEdgeTypeEnum:
    def test_provenance_edges(self):
        provenances = [
            EdgeType.VERSION_OF,
            EdgeType.SUMMARIZED_FROM,
            EdgeType.MERGED_FROM,
            EdgeType.DERIVED_FROM,
            EdgeType.CITED_AS_EVIDENCE,
            EdgeType.PLANNED_FROM,
            EdgeType.ROLLBACK_DEPENDS_ON,
        ]
        for p in provenances:
            assert isinstance(p.value, str)

    def test_conflicts_with_is_semantic_edge(self):
        assert EdgeType.CONFLICTS_WITH.value == "conflicts_with"

    def test_no_non_actionable_semantic_edge_types(self):
        values = {edge.value for edge in EdgeType}

        assert "supports" not in values
        assert "refines" not in values
        assert "related_to" not in values

    def test_audit_edges_not_provenance(self):
        assert EdgeType.READ_BY.value == "read_by"
        assert EdgeType.USED_AS_TOOL_PARAM.value == "used_as_tool_param"


class TestMemoryDependencyInput:
    def test_valid(self):
        dep = MemoryDependencyInput(
            target_memory_id="mem_abc",
            edge_type=EdgeType.VERSION_OF,
            strength=0.9,
            reason="test",
        )
        assert dep.target_memory_id == "mem_abc"
        assert dep.edge_type == EdgeType.VERSION_OF

    def test_strength_below_0_raises(self):
        with pytest.raises(Exception):
            MemoryDependencyInput(target_memory_id="x", edge_type=EdgeType.VERSION_OF, strength=-0.1)

    def test_strength_above_1_raises(self):
        with pytest.raises(Exception):
            MemoryDependencyInput(target_memory_id="x", edge_type=EdgeType.VERSION_OF, strength=1.1)

    def test_default_strength_is_1(self):
        dep = MemoryDependencyInput(target_memory_id="x", edge_type=EdgeType.VERSION_OF)
        assert dep.strength == 1.0

    def test_reason_optional(self):
        dep = MemoryDependencyInput(target_memory_id="x", edge_type=EdgeType.DERIVED_FROM)
        assert dep.reason is None

    def test_rejects_conflicts_with_in_write_dependencies(self):
        with pytest.raises(ValueError, match="dependency_edges only accepts provenance edge types"):
            MemoryDependencyInput(target_memory_id="x", edge_type=EdgeType.CONFLICTS_WITH)

    def test_rejects_audit_edges_in_write_dependencies(self):
        with pytest.raises(ValueError, match="dependency_edges only accepts provenance edge types"):
            MemoryDependencyInput(target_memory_id="x", edge_type=EdgeType.READ_BY)


class TestMemoryWriteRequestWithDependencies:
    def test_dependency_edges_field(self):
        req = MemoryWriteRequest(
            org_id="org1",
            source=MemorySource(kind="user"),
            memory_type=MemoryType.USER_PREFERENCE,
            content=MemoryContent(summary="test"),
            user_id="user1",
            trace_id="trace1",
            dependency_edges=[
                MemoryDependencyInput(target_memory_id="mem_x", edge_type=EdgeType.SUMMARIZED_FROM),
            ],
        )
        assert len(req.dependency_edges) == 1
        assert req.dependency_edges[0].target_memory_id == "mem_x"

    def test_dependency_edges_defaults_empty(self):
        req = MemoryWriteRequest(
            org_id="org1",
            source=MemorySource(kind="user"),
            memory_type=MemoryType.USER_PREFERENCE,
            content=MemoryContent(summary="test"),
            user_id="user1",
            trace_id="trace1",
        )
        assert req.dependency_edges == []


class TestExtractEvidenceMemoryIds:
    def test_memory_ids_format(self):
        from app.services.memory_service import MemoryService
        result = MemoryService._extract_evidence_memory_ids({"memory_ids": ["a", "b"]})
        assert result == ["a", "b"]

    def test_memories_format(self):
        from app.services.memory_service import MemoryService
        result = MemoryService._extract_evidence_memory_ids({"memories": ["c", "d"]})
        assert result == ["c", "d"]

    def test_used_memory_ids_format(self):
        from app.services.memory_service import MemoryService
        result = MemoryService._extract_evidence_memory_ids({"used_memory_ids": ["e"]})
        assert result == ["e"]

    def test_cited_memory_ids_format(self):
        from app.services.memory_service import MemoryService
        result = MemoryService._extract_evidence_memory_ids({"cited_memory_ids": ["f"]})
        assert result == ["f"]

    def test_mixed_format_deduplicates(self):
        from app.services.memory_service import MemoryService
        result = MemoryService._extract_evidence_memory_ids({
            "memory_ids": ["a", "b"],
            "memories": ["b", "c"],
        })
        assert result == ["a", "b", "c"]

    def test_none_returns_empty(self):
        from app.services.memory_service import MemoryService
        assert MemoryService._extract_evidence_memory_ids(None) == []

    def test_empty_dict_returns_empty(self):
        from app.services.memory_service import MemoryService
        assert MemoryService._extract_evidence_memory_ids({}) == []

    def test_no_matching_keys_returns_empty(self):
        from app.services.memory_service import MemoryService
        assert MemoryService._extract_evidence_memory_ids({"other": "value"}) == []


class TestConflictRelationMapping:
    def test_contradicts_maps_to_conflicts_with(self):
        assert ConflictRelation.CONTRADICTS.value == "contradicts"
        assert EdgeType.CONFLICTS_WITH.value == "conflicts_with"

    def test_unrelated_not_persisted(self):
        assert ConflictRelation.UNRELATED.value == "unrelated"

    def test_conflict_relation_only_keeps_actionable_values(self):
        assert {relation.value for relation in ConflictRelation} == {
            "contradicts",
            "unrelated",
        }
