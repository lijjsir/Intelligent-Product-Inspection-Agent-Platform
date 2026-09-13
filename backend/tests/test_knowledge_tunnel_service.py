from __future__ import annotations

from datetime import datetime

from app.schemas.qdl import (
    QDLApplicability,
    QDLClaim,
    QDLDocument,
    QDLEntity,
    QDLEvidence,
    QDLProvenance,
)
from app.services.knowledge_tunnel_service import KnowledgeTunnelService


def _qdl() -> dict:
    return QDLDocument(
        knowledge_level="fact",
        claim=QDLClaim(title="设备状态", text="设备 A 正常", type="quality_fact"),
        entities=[
            QDLEntity(
                entity_type="product",
                value="P001",
                entity_id="P001",
                resolution_status="resolved",
                confidence=0.9,
            )
        ],
        applicability=QDLApplicability(scope_type="meeting_room", scope_id="room-1"),
        evidence=[QDLEvidence(source_type="meeting_message", message_id="message-1")],
        provenance=QDLProvenance(
            room_id="room-1",
            message_ids=["message-1"],
            extraction_method="heuristic",
            generated_at=datetime(2026, 9, 1, 10, 0, 0),
        ),
    ).model_dump(mode="json")


def test_tunnel_requires_explicit_cross_scope_mapping():
    result = KnowledgeTunnelService.transform_qdl(
        _qdl(),
        source_scope_type="meeting_room",
        source_scope_id="room-1",
        target_scope_type="org_space",
        target_scope_id="org-1",
        mapping_version="quality-to-org-v1",
        interpolation_strategy="explicit",
        transform_reason="组织质量复用",
        source_memory_id="memory-1",
    )

    assert result.status == "needs_review"
    assert "entities[0].entity_type" in result.unmapped_fields
    assert "entities[0].value" in result.unmapped_fields
    assert result.transformed_qdl["applicability"] == {
        "scope_type": "org_space",
        "scope_id": "org-1",
        "conditions": [],
        "business_tags": {},
    }


def test_tunnel_applies_mapping_and_forces_target_confirmation():
    result = KnowledgeTunnelService.transform_qdl(
        _qdl(),
        source_scope_type="meeting_room",
        source_scope_id="room-1",
        target_scope_type="org_space",
        target_scope_id="org-1",
        mapping_rules={
            "entity_types": {"product": "other"},
            "entity_values": {"product": {"P001": "ASSET-001"}},
        },
        mapping_version="quality-to-org-v1",
        interpolation_strategy="explicit",
        transform_reason="组织质量复用",
        source_memory_id="memory-1",
    )

    assert result.status == "ready"
    entity = result.transformed_qdl["entities"][0]
    assert entity["entity_type"] == "other"
    assert entity["value"] == "ASSET-001"
    assert result.transformed_qdl["governance"]["status"] == "candidate"
    assert result.transformed_qdl["governance"]["requires_human_confirmation"] is True
    assert result.transformed_qdl["consensus"]["status"] == "candidate"
    assert result.transformed_qdl["lifecycle"]["parent_memory_id"] == "memory-1"
    assert result.transformed_qdl["provenance"]["source_hash"]
    assert any(item["action"] == "map" for item in result.mapping_decisions)


def test_tunnel_identity_strategy_is_explicit_and_reproducible():
    result = KnowledgeTunnelService.transform_qdl(
        _qdl(),
        source_scope_type="meeting_room",
        source_scope_id="room-1",
        target_scope_type="org_space",
        target_scope_id="org-1",
        mapping_version="identity-v1",
        interpolation_strategy="identity",
        transform_reason="保留标准实体标识",
    )

    assert result.status == "ready"
    assert result.transformed_qdl["entities"][0]["value"] == "P001"
    assert result.as_dict()["source_scope"] == {"scope_type": "meeting_room", "scope_id": "room-1"}


def test_tunnel_drop_unmapped_strategy_drops_entities_without_claiming_a_mapping():
    result = KnowledgeTunnelService.transform_qdl(
        _qdl(),
        source_scope_type="meeting_room",
        source_scope_id="room-1",
        target_scope_type="org_space",
        target_scope_id="org-1",
        mapping_version="drop-v1",
        interpolation_strategy="drop_unmapped",
        transform_reason="仅共享不含本地产品标识的结论",
        source_memory_id="memory-1",
    )

    assert result.status == "ready"
    assert result.unmapped_fields == ()
    assert result.transformed_qdl["entities"] == []
    assert any(item["action"] == "drop" for item in result.mapping_decisions)


def test_tunnel_rejects_invalid_qdl_or_missing_reason():
    result = KnowledgeTunnelService.transform_qdl(
        {},
        source_scope_type="meeting_room",
        source_scope_id="room-1",
        target_scope_type="org_space",
        target_scope_id="org-1",
        transform_reason="test",
    )
    assert result.status == "rejected"
    assert result.transformed_qdl is None

    missing_reason = KnowledgeTunnelService.transform_qdl(
        _qdl(),
        source_scope_type="meeting_room",
        source_scope_id="room-1",
        target_scope_type="org_space",
        target_scope_id="org-1",
        interpolation_strategy="identity",
    )
    assert missing_reason.status == "rejected"
    assert "transform_reason is required" in missing_reason.errors
