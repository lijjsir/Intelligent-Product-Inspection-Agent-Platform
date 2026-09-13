from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

import app.services.meeting_qdl_extraction_service as extraction_mod
from app.schemas.qdl import QDLDocument, parse_qdl, qdl_v1_to_v2
from app.services.meeting_service import MeetingService


def _valid_qdl() -> dict:
    return {
        "version": "qdl-v2",
        "knowledge_level": "decision",
        "claim": {"title": "复测安排", "text": "B001 批次明天复测", "type": "decision"},
        "properties": {},
        "entities": [
            {
                "entity_type": "batch",
                "value": "B001",
                "entity_id": "B001",
                "resolution_status": "resolved",
                "confidence": 1,
            }
        ],
        "applicability": {
            "scope_type": "meeting_room",
            "scope_id": "room-1",
            "conditions": [],
            "business_tags": {"batch_nos": ["B001"]},
        },
        "evidence": [
            {
                "source_type": "meeting_message",
                "source_id": "msg-1",
                "message_id": "msg-1",
                "quote_text": "B001 批次明天复测",
            }
        ],
        "relations": [],
        "provenance": {
            "org_id": "org-1",
            "room_id": "room-1",
            "message_ids": ["msg-1"],
            "extraction_method": "mixed",
            "generated_at": datetime.utcnow().isoformat(),
        },
        "governance": {"status": "candidate", "requires_human_confirmation": True},
        "consensus": {"status": "candidate", "support_count": 0, "oppose_count": 0},
        "lifecycle": {"revision": 1},
    }


def test_qdl_v2_accepts_valid_candidate() -> None:
    parsed = parse_qdl(_valid_qdl())

    assert parsed.validation_status == "valid"
    assert parsed.schema_version == "qdl-v2"
    assert parsed.document is not None
    assert parsed.document.entities[0].entity_type == "batch"


@pytest.mark.parametrize(
    ("mutate", "expected_error"),
    [
        (lambda payload: payload.update({"unknown_top_level": True}), "unknown_top_level"),
        (lambda payload: payload.update({"evidence": []}), "evidence"),
        (
            lambda payload: payload["applicability"].update({"scope_type": "product"}),
            "applicability.scope_type",
        ),
    ],
)
def test_qdl_v2_rejects_invalid_contract(mutate, expected_error: str) -> None:
    payload = _valid_qdl()
    mutate(payload)

    parsed = parse_qdl(payload)

    assert parsed.validation_status == "invalid"
    assert parsed.document is None
    assert any(expected_error in error for error in parsed.errors)


def test_qdl_v1_is_mapped_without_mutating_source() -> None:
    legacy = {
        "version": "qdl-json-v1",
        "claim": {"title": "历史结论", "text": "继续执行复测", "type": "decision"},
        "evidence": [
            {"type": "meeting_room", "id": "room-1"},
            {"type": "meeting_message", "id": "msg-1"},
        ],
        "consensus": {"status": "confirmed", "confirmed_by": "user-1"},
        "concept": {"tags": {"product_ids": ["P001"]}},
    }

    mapped = qdl_v1_to_v2(legacy)
    parsed = parse_qdl(legacy)

    assert isinstance(mapped, QDLDocument)
    assert mapped.version == "qdl-v2"
    assert mapped.governance.status == "confirmed"
    assert mapped.entities[0].entity_type == "product"
    assert parsed.validation_status == "legacy_mapped"
    assert legacy["version"] == "qdl-json-v1"


@pytest.mark.parametrize(
    ("governance_status", "consensus_status"),
    [
        ("candidate", "candidate"),
        ("confirmed", "confirmed"),
        ("disputed", "disputed"),
        ("rejected", "rejected"),
        ("superseded", "confirmed"),
    ],
)
def test_meeting_qdl_builder_keeps_governance_and_consensus_aligned(
    governance_status: str,
    consensus_status: str,
) -> None:
    service = MeetingService(object(), "org-1", "user-1")
    payload = {
        "source_room_id": "room-1",
        "source_message_id": "msg-1",
        "source_spans": [
            {
                "message_id": "msg-1",
                "start": 0,
                "end": 8,
                "text": "明天安排复测",
            }
        ],
        "recommended_scope": "meeting_room",
        "governance_status": governance_status,
        "confirmed_by": "user-1" if governance_status in {"confirmed", "superseded"} else None,
        "confirmed_at": datetime.utcnow().isoformat() if governance_status in {"confirmed", "superseded"} else None,
        "extraction_method": "heuristic",
    }

    qdl = service._memory_qdl_json("decision", "复测安排", "明天安排复测", payload)
    parsed = parse_qdl(qdl)

    assert parsed.validation_status == "valid"
    assert parsed.document is not None
    assert parsed.document.governance.status == governance_status
    assert parsed.document.consensus.status == consensus_status


@pytest.mark.asyncio
async def test_semantic_extractor_accepts_only_real_public_message_ids(monkeypatch) -> None:
    async def list_models(self):
        return [{"id": "model-1"}]

    async def select_runtime(self, **kwargs):
        return {
            "model_id": "chat-model",
            "base_url": "http://model.test/v1",
            "api_key": "secret",
            "provider": "custom",
        }

    class FakeLLMClient:
        def __init__(self, **kwargs):
            pass

        async def chat(self, *args, **kwargs):
            properties = {
                key: {"level": "unknown", "confidence": None}
                for key in (
                    "abstraction",
                    "environment",
                    "boundary",
                    "dynamic",
                    "social",
                    "tacit",
                    "hierarchy",
                    "stability",
                )
            }
            properties["extensions"] = {}
            base = {
                "knowledge_level": "decision",
                "claim": {"title": "复测安排", "text": "B001 批次明天复测", "type": "decision"},
                "properties": properties,
                "entities": [],
                "applicability_conditions": [],
            }
            return {
                "candidates": [
                    {**base, "evidence_message_ids": ["msg-1"]},
                    {**base, "claim": {**base["claim"], "title": "伪造来源"}, "evidence_message_ids": ["missing"]},
                ],
                "__meta__": {"usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}},
            }

    monkeypatch.setattr(extraction_mod.ModelConfigService, "list_runtime_models", list_models)
    monkeypatch.setattr(extraction_mod.LLMGateway, "select_runtime", select_runtime)
    monkeypatch.setattr(extraction_mod, "LLMClient", FakeLLMClient)

    messages = [
        SimpleNamespace(
            id="msg-1",
            seq_no=1,
            username="专家A",
            content="B001 批次明天复测",
            message_type="user",
            metadata_json={"visibility": "room"},
            private_recipient_user_id=None,
        ),
        SimpleNamespace(
            id="private-1",
            seq_no=2,
            username="专家A",
            content="这是一条私聊",
            message_type="user",
            metadata_json={"visibility": "private"},
            private_recipient_user_id="user-1",
        ),
    ]

    result = await extraction_mod.MeetingQDLExtractionService(object(), "org-1").extract(
        messages,
        max_items=3,
        trace_id="trace-1",
    )

    assert result.status == "success"
    assert len(result.entries) == 1
    assert result.invalid_candidate_count == 1
    assert result.entries[0]["source_message_id"] == "msg-1"
    assert result.entries[0]["extraction_method"] == "mixed"
    assert result.usage == {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
