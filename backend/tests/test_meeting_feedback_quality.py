from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from app.services.feedback_service import FeedbackService
from app.services.quality_report_service import QualityReportService
from app.schemas.memory import MemoryStatus, MemoryWriteResponse


def _feedback(*, source: str, feedback_type: str, created_at: datetime, target_id: str = "message-1"):
    if source in {"chat", "meeting"}:
        return SimpleNamespace(
            target_type=source,
            target_id=target_id,
            feedback_type=feedback_type,
            category=f"{source}_{feedback_type}",
            created_at=created_at,
        )
    return SimpleNamespace(
        source_type="result",
        feedback_type=feedback_type,
        category="wrong_verdict",
        created_at=created_at,
    )


def test_feedback_source_summary_includes_meeting_channel():
    created_at = datetime(2026, 9, 1, 10, 0, 0)
    result_feedbacks = [_feedback(source="inspection", feedback_type="down", created_at=created_at)]
    message_feedbacks = [
        _feedback(source="chat", feedback_type="up", created_at=created_at),
        _feedback(source="meeting", feedback_type="down", created_at=created_at),
    ]

    summary = QualityReportService._build_feedback_source_summary(
        result_feedbacks,
        message_feedbacks,
    )

    assert summary["inspection"]["total_count"] == 1
    assert summary["chat"]["thumbs_up_count"] == 1
    assert summary["meeting"] == {
        "total_count": 1,
        "thumbs_up_count": 0,
        "thumbs_down_count": 1,
        "thumbs_up_share": 0.0,
        "thumbs_down_share": 1.0,
    }


def test_feedback_filter_keeps_meeting_for_unified_report():
    items = [
        _feedback(source="chat", feedback_type="up", created_at=datetime(2026, 9, 1)),
        _feedback(source="meeting", feedback_type="down", created_at=datetime(2026, 9, 1)),
    ]

    assert QualityReportService._filter_message_feedbacks_for_source(items, "all") == items
    assert QualityReportService._filter_message_feedbacks_for_source(items, "chat") == [items[0]]
    assert QualityReportService._filter_message_feedbacks_for_source(items, "inspection") == []


def test_message_feedback_metadata_captures_answer_provenance():
    target = SimpleNamespace(
        id="meeting-answer-1",
        message_type="agent",
        agent_id="agent-1",
        metadata_json={
            "trace_id": "trace-1",
            "workflow_run_id": "run-1",
            "citations": [{"id": "doc-1"}],
            "source_scope_refs": [{"type": "memory", "id": "mem-1"}],
            "conflict_ref_ids": ["conflict-1"],
            "qdl_version": "qdl-v2",
            "knowledge_version": "memory-v7",
        },
    )

    captured = FeedbackService._build_message_feedback_metadata(
        target_type="meeting",
        target=target,
        captured_at=datetime(2026, 9, 1, 10, 0, 0),
    )

    assert captured["trace_id"] == "trace-1"
    assert captured["source_refs"] == [{"type": "memory", "id": "mem-1"}]
    assert captured["citations"] == [{"id": "doc-1"}]
    assert captured["conflict_ref_ids"] == ["conflict-1"]
    assert captured["qdl_version"] == "qdl-v2"
    assert captured["knowledge_version"] == "memory-v7"


@pytest.mark.asyncio
async def test_build_report_reads_chat_and_meeting_feedback_together(monkeypatch):
    meeting_feedback = _feedback(
        source="meeting",
        feedback_type="down",
        created_at=datetime(2026, 9, 1, 10, 0, 0),
    )

    class FeedbackRepo:
        def __init__(self):
            self.message_calls = []

        async def list_by_range(self, *_args, **_kwargs):
            return []

        async def list_message_by_range(self, *args, **kwargs):
            self.message_calls.append((args, kwargs))
            return [meeting_feedback]

    class EmptyRepo:
        async def list_by_range(self, *_args, **_kwargs):
            return []

    class EmptyLedgerRepo:
        async def list_filtered(self, *_args, **_kwargs):
            return []

    class EmptyChatMessageRepo:
        async def list_assistant_for_org(self, *_args, **_kwargs):
            return []

    class DisabledLangfuse:
        enabled = False

    monkeypatch.setattr(
        "app.services.quality_report_service.LangfuseApiClient",
        lambda: DisabledLangfuse(),
    )
    feedback_repo = FeedbackRepo()
    service = QualityReportService(session=object(), org_id="org-1")
    service._feedback_repo = feedback_repo
    service._result_repo = EmptyRepo()
    service._stability_repo = EmptyRepo()
    service._token_ledger_repo = EmptyLedgerRepo()
    service._chat_score_repo = EmptyRepo()
    service._chat_message_repo = EmptyChatMessageRepo()

    report = await service.build_report(
        start_date=datetime(2026, 9, 1).date(),
        end_date=datetime(2026, 9, 1).date(),
    )

    assert report["feedback_total_count"] == 1
    assert report["thumbs_down_count"] == 1
    assert report["feedback_by_source"]["meeting"]["total_count"] == 1
    assert report["feedback_distribution"] == {"meeting_down": 1}
    assert feedback_repo.message_calls
    assert all(call[1]["target_type"] is None for call in feedback_repo.message_calls)


@pytest.mark.asyncio
async def test_positive_agent_feedback_creates_candidate_and_queues_candidate_index(monkeypatch):
    target = SimpleNamespace(
        id="meeting-answer-1",
        room_id="room-1",
        user_id="user-1",
        agent_id="agent-1",
        message_type="agent",
        content="产品 P001 的复测结果需要人工复核，原因是边缘识别置信度不足。",
        metadata_json={
            "trace_id": "trace-1",
            "workflow_run_id": "run-1",
            "trust_protocol": {"status": "trusted", "confidence": 0.82, "trace_id": "trace-1"},
            "citations": [{"ref": "memory-1", "source_type": "standard", "source_id": "std-1"}],
        },
    )

    class ScalarResult:
        def scalar_one_or_none(self):
            return target

    class Session:
        async def execute(self, _stmt):
            return ScalarResult()

        async def flush(self):
            return None

    feedback_row = SimpleNamespace(id="feedback-1", metadata_json={})

    class FeedbackRepo:
        def __init__(self, _session):
            pass

        async def save_message_feedback(self, payload):
            feedback_row.metadata_json = payload["metadata_json"]
            return feedback_row

    captured = {}

    class FakeMemoryService:
        def __init__(self, session, org_id):
            captured["service_args"] = (session, org_id)

        async def write_candidate(self, request):
            captured["request"] = request
            return MemoryWriteResponse(
                memory_id="mem-feedback-1",
                status=MemoryStatus.CANDIDATE,
                confidence=request.confidence,
                trust_score=request.confidence,
            )

    class FakeItemRepo:
        def __init__(self, _session, _org_id):
            pass

        async def get_by_memory_id(self, _memory_id):
            return SimpleNamespace(
                memory_id="mem-feedback-1",
                user_id=None,
                memory_type="agent_ops_memory",
                content_summary=target.content,
                trust_score=0.82,
                confidence=0.82,
                expires_at=None,
                product_line=None,
                rag_space_id=None,
                task_id=None,
                source_task_id=None,
                scope_json={"scope_type": "meeting_room", "scope_id": "room-1"},
                review_status="candidate",
                applicability_json={"meeting_room_id": "room-1"},
            )

    class FakeOutbox:
        def __init__(self, _session, _org_id):
            pass

        async def create_pending(self, **kwargs):
            captured["outbox"] = kwargs
            return SimpleNamespace(**kwargs)

    monkeypatch.setattr("app.services.feedback_service.FeedbackRepository", FeedbackRepo)
    monkeypatch.setattr("app.services.feedback_service.MemoryItemRepository", FakeItemRepo)
    monkeypatch.setattr("app.services.feedback_service.MemorySyncOutboxRepository", FakeOutbox)
    monkeypatch.setattr("app.services.memory_service.MemoryService", FakeMemoryService)

    service = FeedbackService(Session(), "org-1")
    result = await service.submit_message_feedback(
        "meeting",
        target.id,
        "user-1",
        {"feedback_type": "up", "rating": 5, "category": "helpful"},
    )

    update = result.metadata_json["knowledge_update"]
    assert update["status"] == "candidate_created"
    assert update["candidate_memory_id"] == "mem-feedback-1"
    assert update["index_status"] == "queued"
    assert captured["request"].source.kind == "meeting"
    assert captured["request"].scope.meeting_room_id == "room-1"
    assert captured["request"].evidence_pointers["feedback_id"] == "feedback-1"
    assert captured["outbox"]["action"] == "UPSERT_CANDIDATE_VECTOR"
    assert captured["outbox"]["payload"]["collection"] == "piap_candidate_memory"


@pytest.mark.asyncio
async def test_negative_agent_feedback_only_marks_human_review(monkeypatch):
    target = SimpleNamespace(
        id="chat-answer-1",
        user_id="user-1",
        role="assistant",
        message_type="text",
        content="这是一个可供复核的回答。",
        metadata_json={"trust_protocol": {"status": "trusted", "confidence": 0.8}},
    )

    class ScalarResult:
        def scalar_one_or_none(self):
            return target

    class Session:
        async def execute(self, _stmt):
            return ScalarResult()

        async def flush(self):
            return None

    class FeedbackRepo:
        def __init__(self, _session):
            pass

        async def save_message_feedback(self, payload):
            return SimpleNamespace(id="feedback-down", metadata_json=payload["metadata_json"])

    monkeypatch.setattr("app.services.feedback_service.FeedbackRepository", FeedbackRepo)
    service = FeedbackService(Session(), "org-1")
    result = await service.submit_message_feedback(
        "chat",
        target.id,
        "user-1",
        {"feedback_type": "down", "rating": 1, "category": "not_helpful"},
    )

    update = result.metadata_json["knowledge_update"]
    assert update["status"] == "needs_human_review"
    assert update["needs_human_review"] is True
    assert update["candidate_memory_id"] is None
    assert update["reason"] == "negative_feedback_does_not_mutate_active_memory"
