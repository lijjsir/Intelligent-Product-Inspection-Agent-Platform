from __future__ import annotations

import pytest

from app.schemas.memory import MemoryType
from app.services.memory_candidate_service import MemoryCandidateService


@pytest.mark.asyncio
async def test_chat_preference_becomes_candidate_only_when_reusable():
    service = MemoryCandidateService(org_id="org-1", user_id="user-1")

    candidates = await service.extract_from_chat_result(
        trace_id="trace-1",
        user_message="以后质检报告默认按结论-依据-建议输出。",
        assistant_answer="好的，后续会按这个结构输出。",
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.memory_type == MemoryType.USER_PREFERENCE
    assert candidate.source.kind == "user"
    assert candidate.source.trace_id == "trace-1"
    assert candidate.confidence >= 0.4
    assert candidate.scope is not None
    assert candidate.content.preferences == ["以后质检报告默认按结论-依据-建议输出。"]


@pytest.mark.asyncio
async def test_one_off_chat_request_does_not_become_candidate():
    service = MemoryCandidateService(org_id="org-1", user_id="user-1")

    candidates = await service.extract_from_chat_result(
        trace_id="trace-1",
        user_message="帮我看看这张图。",
        assistant_answer="这次图片看起来没有明显缺陷。",
    )

    assert candidates == []


@pytest.mark.asyncio
async def test_short_term_memory_preference_can_become_candidate_after_success():
    service = MemoryCandidateService(org_id="org-1", user_id="user-1")

    candidates = await service.extract_from_chat_result(
        trace_id="trace-2",
        user_message="继续生成报告。",
        assistant_answer="已完成。",
        short_term_memory={
            "conversation_summary": "用户在配置质检报告输出格式。",
            "session_facts": {"preferred_language": "zh-CN"},
            "recent_messages": [
                {"role": "user", "content": "以后质检报告默认用中文输出。"},
                {"role": "assistant", "content": "好的。"},
            ],
        },
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.memory_type == MemoryType.USER_PREFERENCE
    assert candidate.content.preferences == ["以后质检报告默认用中文输出。"]
    assert candidate.evidence_pointers["extracted_from"] == "short_term_memory.recent_messages"
    assert candidate.evidence_pointers["short_term_fact_keys"] == ["preferred_language"]
