from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas.meeting import MeetingBusinessContext, MeetingRoomCreateRequest, MeetingRoomUpdateRequest
from app.services.meeting_auto_participation_service import (
    MeetingAutoParticipationService,
    _DECISION_REF_TYPE,
)
from app.services.meeting_service import MeetingService


class FakeAuditRepo:
    def __init__(self, decisions=None):
        self.decisions = decisions or []

    async def list_agent_query_audits(self, **kwargs):
        return [
            SimpleNamespace(source_refs=[{"type": _DECISION_REF_TYPE, **item}])
            for item in self.decisions
        ]


def context(*, messages=None, tasks=None, memories=None, conflicts=None, roles=None):
    return {
        "messages": messages
        if messages is not None
        else [
            {
                "id": "msg-1",
                "seq_no": 1,
                "user_id": "user-1",
                "username": "alice",
                "system_role": "user",
                "content": "这个结论还缺少检测依据。",
            }
        ],
        "members": [],
        "present_roles": roles if roles is not None else ["user", "expert"],
        "business_context": {"standard_ids": ["STD-1"]},
        "quality_context": {
            "tasks": tasks if tasks is not None else [{"task_id": "task-1", "status": "succeeded"}]
        },
        "active_memories": memories if memories is not None else [{"type": "memory", "id": "mem-1", "status": "active"}],
        "unresolved_conflicts": conflicts if conflicts is not None else [{"type": "conflict", "id": "conflict-1"}],
    }


def decision(**overrides):
    value = {
        "decision": "participate",
        "trigger_type": "evidence_gap",
        "action_type": "evidence_query",
        "target_role": "expert",
        "confidence": 0.9,
        "resource_key": "task:task-1:evidence",
        "reason": "放行结论缺少检测依据",
        "human_is_handling": False,
        "evidence_refs": [{"type": "inspection_task", "id": "task-1"}],
        "suppression_reasons": [],
    }
    value.update(overrides)
    return value


def service(previous=None):
    instance = MeetingAutoParticipationService(
        None,
        org_id="org-1",
        user_id="user-1",
        user_role="user",
    )
    instance._repo = FakeAuditRepo(previous)
    return instance


def test_room_request_defaults_to_off_and_validates_modes():
    assert MeetingRoomCreateRequest(title="demo").auto_participation_mode == "off"
    assert MeetingRoomUpdateRequest(auto_participation_mode="live").auto_participation_mode == "live"
    with pytest.raises(ValidationError):
        MeetingRoomUpdateRequest(auto_participation_mode="shadow")
    with pytest.raises(ValueError):
        MeetingRoomUpdateRequest(auto_participation_mode="always")


def test_message_eligibility_excludes_private_system_and_attachment_only():
    assert MeetingAutoParticipationService._eligible_message(
        SimpleNamespace(message_type="user", content="公开讨论", metadata_json={})
    )
    assert not MeetingAutoParticipationService._eligible_message(
        SimpleNamespace(message_type="user", content="私聊", metadata_json={"visibility": "private"})
    )
    assert not MeetingAutoParticipationService._eligible_message(
        SimpleNamespace(message_type="system", content="系统消息", metadata_json={})
    )
    assert not MeetingAutoParticipationService._eligible_message(
        SimpleNamespace(message_type="user", content="", metadata_json={"attachment_echo": [{"id": "a"}]})
    )


@pytest.mark.asyncio
async def test_first_non_urgent_issue_is_observed():
    result = await service()._apply_hard_suppression(
        context=context(),
        decision=decision(),
        room_id="room-1",
        trigger_message=SimpleNamespace(seq_no=1),
    )
    assert result["decision"] == "observe"
    assert result["suppression_reasons"] == []


@pytest.mark.asyncio
async def test_second_related_turn_participates_after_observe():
    previous = [{
        "resource_key": "task:task-1:evidence",
        "decision": "observe",
        "trigger_seq_no": 1,
        "evidence_keys": ["inspection_task:task-1"],
    }]
    messages = [
        {"id": "msg-1", "seq_no": 1, "content": "证据呢"},
        {"id": "msg-2", "seq_no": 2, "content": "先继续定结论"},
    ]
    result = await service(previous)._apply_hard_suppression(
        context=context(messages=messages),
        decision=decision(),
        room_id="room-1",
        trigger_message=SimpleNamespace(seq_no=2),
    )
    assert result["decision"] == "participate"


@pytest.mark.asyncio
async def test_missing_resource_key_is_derived_from_project_evidence():
    result = await service()._apply_hard_suppression(
        context=context(),
        decision=decision(resource_key=""),
        room_id="room-1",
        trigger_message=SimpleNamespace(seq_no=1),
    )
    assert result["decision"] == "observe"
    assert result["resource_key"] == "inspection_task:task-1"
    assert "missing_resource_key" not in result["suppression_reasons"]


@pytest.mark.asyncio
async def test_message_only_resource_key_connects_related_turns():
    previous = [{
        "resource_key": "meeting_message:msg-1",
        "decision": "observe",
        "trigger_seq_no": 1,
        "evidence_keys": [],
        "evidence_refs": [{"type": "meeting_message", "id": "msg-1"}],
    }]
    messages = [
        {"id": "msg-1", "seq_no": 1, "content": "失败规则未核对，但要求直接放行。"},
        {"id": "msg-2", "seq_no": 2, "content": "仍不核对，直接确认放行。"},
    ]
    result = await service(previous)._apply_hard_suppression(
        context=context(messages=messages, tasks=[]),
        decision=decision(
            resource_key="",
            evidence_refs=[
                {"type": "meeting_message", "id": "msg-1"},
                {"type": "meeting_message", "id": "msg-2"},
            ],
        ),
        room_id="room-1",
        trigger_message=SimpleNamespace(seq_no=2),
    )
    assert result["decision"] == "participate"
    assert result["resource_key"] == "meeting_message:msg-1"


@pytest.mark.asyncio
async def test_legacy_missing_resource_key_audit_resumes_as_observation():
    previous = [{
        "resource_key": "",
        "decision": "silent",
        "trigger_seq_no": 1,
        "evidence_keys": [],
        "evidence_refs": [{"type": "meeting_message", "id": "msg-1"}],
        "suppression_reasons": ["missing_resource_key"],
    }]
    messages = [
        {"id": "msg-1", "seq_no": 1, "content": "失败规则未核对，但要求直接放行。"},
        {"id": "msg-2", "seq_no": 2, "content": "仍不核对，直接确认放行。"},
    ]
    result = await service(previous)._apply_hard_suppression(
        context=context(messages=messages, tasks=[]),
        decision=decision(
            resource_key="",
            evidence_refs=[
                {"type": "meeting_message", "id": "msg-1"},
                {"type": "meeting_message", "id": "msg-2"},
            ],
        ),
        room_id="room-1",
        trigger_message=SimpleNamespace(seq_no=2),
    )
    assert result["decision"] == "participate"
    assert result["resource_key"] == "meeting_message:msg-1"


@pytest.mark.asyncio
async def test_human_handling_cancels_observation():
    result = await service()._apply_hard_suppression(
        context=context(),
        decision=decision(human_is_handling=True),
        room_id="room-1",
        trigger_message=SimpleNamespace(seq_no=1),
    )
    assert result["decision"] == "silent"
    assert "human_is_handling" in result["suppression_reasons"]


@pytest.mark.asyncio
async def test_duplicate_participation_is_suppressed_for_three_human_turns():
    previous = [{
        "resource_key": "task:task-1:evidence",
        "decision": "participate",
        "trigger_seq_no": 1,
        "evidence_keys": ["inspection_task:task-1"],
    }]
    messages = [
        {"id": "msg-1", "seq_no": 1, "content": "缺证据"},
        {"id": "msg-2", "seq_no": 2, "content": "还是先这样"},
        {"id": "msg-3", "seq_no": 3, "content": "继续"},
    ]
    result = await service(previous)._apply_hard_suppression(
        context=context(messages=messages),
        decision=decision(),
        room_id="room-1",
        trigger_message=SimpleNamespace(seq_no=3),
    )
    assert result["decision"] == "silent"
    assert "duplicate_without_new_evidence" in result["suppression_reasons"]


@pytest.mark.asyncio
async def test_new_discussion_message_does_not_count_as_new_evidence():
    previous = [{
        "resource_key": "task:task-1:evidence",
        "decision": "participate",
        "trigger_seq_no": 1,
        "evidence_keys": ["inspection_task:task-1"],
    }]
    messages = [
        {"id": "msg-1", "seq_no": 1, "content": "缺证据"},
        {"id": "msg-2", "seq_no": 2, "content": "还是先按原结论走"},
    ]
    result = await service(previous)._apply_hard_suppression(
        context=context(messages=messages),
        decision=decision(evidence_refs=[
            {"type": "inspection_task", "id": "task-1"},
            {"type": "meeting_message", "id": "msg-2"},
        ]),
        room_id="room-1",
        trigger_message=SimpleNamespace(seq_no=2),
    )
    assert result["decision"] == "silent"
    assert "duplicate_without_new_evidence" in result["suppression_reasons"]


@pytest.mark.asyncio
async def test_active_history_conflict_can_participate_immediately():
    result = await service()._apply_hard_suppression(
        context=context(),
        decision=decision(
            trigger_type="history_conflict",
            action_type="standard_remind",
            evidence_refs=[{"type": "memory", "id": "mem-1"}],
            resource_key="memory:mem-1",
        ),
        room_id="room-1",
        trigger_message=SimpleNamespace(seq_no=1),
    )
    assert result["decision"] == "participate"
    assert result["immediate"] is True


@pytest.mark.asyncio
async def test_disputed_memory_cannot_be_used_as_active_history_basis():
    disputed = [{"type": "memory", "id": "mem-disputed", "status": "disputed"}]
    result = await service()._apply_hard_suppression(
        context=context(memories=[], conflicts=disputed),
        decision=decision(
            trigger_type="history_conflict",
            action_type="standard_remind",
            evidence_refs=[{"type": "memory", "id": "mem-disputed"}],
            resource_key="memory:mem-disputed",
        ),
        room_id="room-1",
        trigger_message=SimpleNamespace(seq_no=1),
    )
    assert result["decision"] == "silent"
    assert result["immediate"] is False
    assert "no_active_history_basis" in result["suppression_reasons"]


@pytest.mark.asyncio
async def test_missing_evidence_low_confidence_and_absent_target_force_silence():
    result = await service()._apply_hard_suppression(
        context=context(roles=["user"]),
        decision=decision(confidence=0.7, evidence_refs=[]),
        room_id="room-1",
        trigger_message=SimpleNamespace(seq_no=1),
    )
    assert result["decision"] == "silent"
    assert set(result["suppression_reasons"]) >= {
        "confidence_below_threshold",
        "no_valid_evidence",
        "target_role_not_present",
    }


@pytest.mark.asyncio
async def test_high_risk_release_conflict_participates_immediately():
    messages = [
        {"id": "msg-1", "seq_no": 1, "content": "任务虽然失败了，这批先放行。"},
    ]
    tasks = [{"task_id": "task-1", "status": "succeeded", "verdict": "fail", "risk_level": "high"}]
    result = await service()._apply_hard_suppression(
        context=context(messages=messages, tasks=tasks),
        decision=decision(),
        room_id="room-1",
        trigger_message=SimpleNamespace(seq_no=1),
    )
    assert result["decision"] == "participate"
    assert result["immediate"] is True


def test_evidence_validation_rejects_unknown_and_superseded_refs():
    refs = MeetingAutoParticipationService._valid_evidence_refs(
        context(memories=[]),
        [
            {"type": "memory", "id": "superseded-memory"},
            {"type": "task", "id": "task-1"},
            {"type": "message", "id": "msg-1"},
        ],
    )
    assert refs == [
        {"type": "inspection_task", "id": "task-1"},
        {"type": "meeting_message", "id": "msg-1"},
    ]


def test_action_routes_reuse_existing_general_agent_modes():
    assert MeetingAutoParticipationService._agent_mode(decision()) == "evidence_query"
    assert MeetingAutoParticipationService._agent_mode(
        decision(
            trigger_type="history_conflict",
            evidence_refs=[{"type": "standard", "id": "STD-1"}],
        )
    ) == "standard_explain"
    assert MeetingAutoParticipationService._agent_mode(
        decision(trigger_type="unresolved_conflict")
    ) == "auto"


@pytest.mark.asyncio
async def test_room_create_persists_mode_in_existing_audit_policy():
    captured = {}

    class Session:
        commits = 0

        async def commit(self):
            self.commits += 1

    class Repo:
        async def get_room_by_code(self, org_id, access_code):
            return None

        async def create_room(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(id="room-1")

    session = Session()
    meeting = MeetingService(session, "org-1", "user-1")
    meeting._repo = Repo()

    async def normalize_context(value):
        return MeetingBusinessContext()

    async def serialize_rooms(rows):
        return rows

    meeting._normalize_business_context = normalize_context
    meeting._serialize_rooms = serialize_rooms

    await meeting.create_room("研究会议", auto_participation_mode="shadow")

    assert captured["audit_policy"]["auto_participation_mode"] == "off"
    assert captured["audit_policy"]["record_agent_queries"] is True
    assert session.commits == 1


@pytest.mark.asyncio
async def test_room_update_merges_mode_without_losing_existing_audit_policy():
    room = SimpleNamespace(
        id="room-1",
        audit_policy={"enabled": True, "record_agent_queries": True},
        memory_policy={},
    )
    captured = {}

    class Repo:
        async def get_room(self, org_id, room_id):
            return room

        async def update_room(self, org_id, room_id, **kwargs):
            captured.update(kwargs)
            room.audit_policy = kwargs.get("audit_policy") or room.audit_policy
            return room

    meeting = MeetingService(None, "org-1", "user-1")
    meeting._repo = Repo()

    async def no_op(*args, **kwargs):
        return None

    async def serialize_rooms(rows):
        return rows

    meeting._ensure_host = no_op
    meeting._publish_system_message = no_op
    meeting._serialize_rooms = serialize_rooms

    await meeting.update_room_settings("room-1", auto_participation_mode="live")

    assert captured["audit_policy"] == {
        "enabled": True,
        "record_agent_queries": True,
        "auto_participation_mode": "live",
    }
