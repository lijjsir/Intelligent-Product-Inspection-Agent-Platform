from __future__ import annotations

import pytest

from app.services.retrieval_conflict_guard import RetrievalConflictGuard
from app.services.conflict_detectors.rag_memory_detector import rule_judge_rag_memory, _roughly_related
from app.services.conflict_detectors.session_memory_detector import SessionMemoryDetector
from app.services.conflict_detectors.tool_memory_detector import ToolMemoryDetector
from app.services.conflict_detectors.memory_memory_detector import MemoryMemoryDetector


# ---- RAG-Memory Rule Tests ----

def test_rule_judge_rag_memory_allow_vs_deny_detects_conflict():
    result = rule_judge_rag_memory(
        "强反光区域可以直接判为划痕",
        "强反光区域不得直接判为划痕，需要复核",
    )
    assert result is not None
    assert result["verdict"] == "conflict"
    assert result["confidence"] >= 0.75


def test_rule_judge_rag_memory_deny_vs_allow_detects_conflict():
    result = rule_judge_rag_memory(
        "该区域禁止直接放行",
        "该区域建议直接放行",
    )
    assert result is not None
    assert result["verdict"] == "conflict"
    assert result["confidence"] >= 0.75


def test_rule_judge_rag_memory_same_opinion_no_conflict():
    result = rule_judge_rag_memory(
        "需要复核后才能放行",
        "必须复检后确定",
    )
    if result:
        assert result["verdict"] != "conflict"


def test_roughly_related_detects_shared_chars():
    assert _roughly_related("强反光区域划痕判断", "强反光区域不得直接判为划痕") is True


def test_roughly_related_unrelated_texts():
    assert _roughly_related("相机阈值设置", "文档格式要求") is False


# ---- Session-Memory Detector Tests ----

def test_session_detector_suppresses_preference_when_contradiction():
    detector = SessionMemoryDetector()
    result = detector.detect(
        session_facts={"explicit_instructions": ["这次不要用之前的偏好"]},
        memory_hits=[{
            "memory_id": "mem-1",
            "memory_type": "user_preference",
            "summary": "用户喜欢详细解释",
            "score": 0.9,
        }],
    )
    assert "mem-1" in result["suppressed_memory_ids"]
    assert len(result["conflicts"]) == 1


def test_session_detector_no_session_facts_returns_empty():
    detector = SessionMemoryDetector()
    result = detector.detect(
        session_facts=None,
        memory_hits=[{"memory_id": "mem-1", "memory_type": "user_preference", "summary": "x"}],
    )
    assert result["suppressed_memory_ids"] == []


def test_session_detector_skips_non_preference_types():
    detector = SessionMemoryDetector()
    result = detector.detect(
        session_facts={"explicit_instructions": ["这次不要"]},
        memory_hits=[{
            "memory_id": "mem-1",
            "memory_type": "rag_usage_memory",
            "summary": "RAG usage pattern",
            "score": 0.9,
        }],
    )
    assert result["suppressed_memory_ids"] == []


# ---- Tool-Memory Detector Tests ----

def test_tool_detector_status_conflict():
    detector = ToolMemoryDetector()
    result = detector.detect(
        tool_results=[{"name": "task_status", "output": "任务状态: failed"}],
        memory_hits=[{
            "memory_id": "mem-1",
            "summary": "该任务已完成",
            "score": 0.9,
        }],
    )
    assert "mem-1" in result["suppressed_memory_ids"]


def test_tool_detector_no_conflict_same_status():
    detector = ToolMemoryDetector()
    result = detector.detect(
        tool_results=[{"name": "task_status", "output": "任务状态: completed"}],
        memory_hits=[{
            "memory_id": "mem-1",
            "summary": "该任务已完成",
            "score": 0.9,
        }],
    )
    assert "mem-1" not in result["suppressed_memory_ids"]


def test_tool_detector_empty_tool_results():
    detector = ToolMemoryDetector()
    result = detector.detect(
        tool_results=[],
        memory_hits=[{"memory_id": "mem-1", "summary": "已完成", "score": 0.9}],
    )
    assert result["suppressed_memory_ids"] == []


# ---- Memory-Memory Detector Tests ----

def test_memory_memory_detector_downranks_low_trust():
    detector = MemoryMemoryDetector("org-1")
    result = detector.detect([
        {"memory_id": "mem-a", "trust_score": 0.9, "confidence": 0.9, "score": 0.9},
        {"memory_id": "mem-b", "trust_score": 0.3, "confidence": 0.3, "score": 0.3},
    ])
    assert "mem-b" in result["downranked_memory_ids"]


def test_memory_memory_single_item_returns_empty():
    detector = MemoryMemoryDetector("org-1")
    result = detector.detect([{"memory_id": "mem-a", "trust_score": 0.9, "confidence": 0.9, "score": 0.9}])
    assert result["conflicts"] == []
    assert result["downranked_memory_ids"] == []


def test_memory_memory_same_task_slot_conflict():
    detector = MemoryMemoryDetector("org-1")
    result = detector.detect([
        {"memory_id": "mem-a", "memory_type": "task_episode", "trust_score": 0.9, "confidence": 0.9, "score": 0.9, "source": {"task_id": "task-1"}},
        {"memory_id": "mem-b", "memory_type": "task_episode", "trust_score": 0.5, "confidence": 0.5, "score": 0.5, "source": {"task_id": "task-1"}},
    ])
    assert "mem-b" in result["downranked_memory_ids"]
    assert any(c["type"] == "memory_vs_memory" for c in result["conflicts"])


# ---- RetrievalConflictGuard Integration Tests ----

@pytest.mark.asyncio
async def test_guard_check_filters_session_conflicts():
    guard = RetrievalConflictGuard("org-1")
    result = await guard.check(
        query="test",
        rag_hits=[],
        memory_hits=[{
            "memory_id": "mem-1",
            "memory_type": "user_preference",
            "summary": "用户喜欢详细解释",
            "score": 0.9,
            "confidence": 0.8,
            "trust_score": 0.8,
            "source": {},
        }],
        session_facts={"explicit_instructions": ["这次不要用之前的偏好"]},
    )
    assert "mem-1" in result["suppressed_memory_ids"]
    assert len(result["memory_hits"]) == 0


@pytest.mark.asyncio
async def test_guard_check_preserves_non_conflicting_memories():
    guard = RetrievalConflictGuard("org-1")
    result = await guard.check(
        query="test",
        rag_hits=[],
        memory_hits=[
            {"memory_id": "mem-1", "memory_type": "task_episode", "summary": "lesson A", "score": 0.9, "confidence": 0.8, "trust_score": 0.8, "source": {}},
            {"memory_id": "mem-2", "memory_type": "user_preference", "summary": "喜欢详细解释", "score": 0.7, "confidence": 0.7, "trust_score": 0.7, "source": {}},
        ],
        session_facts={"explicit_instructions": ["这次不要偏好"]},
    )
    assert "mem-2" in result["suppressed_memory_ids"]
    assert len(result["memory_hits"]) == 1
    assert result["memory_hits"][0]["memory_id"] == "mem-1"


@pytest.mark.asyncio
async def test_guard_downranks_low_trust_memories():
    guard = RetrievalConflictGuard("org-1")
    result = await guard.check(
        query="test",
        rag_hits=[],
        memory_hits=[
            {"memory_id": "mem-a", "trust_score": 0.9, "confidence": 0.9, "score": 0.9, "summary": "A", "memory_type": "task_episode", "source": {}},
            {"memory_id": "mem-b", "trust_score": 0.2, "confidence": 0.2, "score": 0.2, "summary": "B", "memory_type": "task_episode", "source": {}},
        ],
    )
    assert "mem-b" in result["downranked_memory_ids"]
    assert len(result["memory_hits"]) == 2
    assert result["memory_hits"][1]["memory_id"] == "mem-b"


@pytest.mark.asyncio
async def test_guard_sync_check_no_rag():
    guard = RetrievalConflictGuard("org-1")
    result = guard.check_sync(
        query="test",
        memory_hits=[{
            "memory_id": "mem-1",
            "memory_type": "user_preference",
            "summary": "偏好",
            "score": 0.9,
            "confidence": 0.8,
            "trust_score": 0.8,
            "source": {},
        }],
        session_facts={"explicit_instructions": ["忽略偏好"]},
    )
    assert "mem-1" in result["suppressed_memory_ids"]
    assert result["memory_hits"] == []


@pytest.mark.asyncio
async def test_guard_tool_conflict_suppresses_memory():
    guard = RetrievalConflictGuard("org-1")
    result = await guard.check(
        query="test",
        rag_hits=[],
        memory_hits=[{
            "memory_id": "mem-1",
            "memory_type": "task_episode",
            "summary": "任务已完成",
            "score": 0.9,
            "confidence": 0.8,
            "trust_score": 0.8,
            "source": {},
        }],
        tool_results=[{"name": "task_check", "output": "状态: failed"}],
    )
    assert "mem-1" in result["suppressed_memory_ids"]


# ---- RAG vs RAG Tests ----

def test_check_rag_rag_prefers_higher_score():
    guard = RetrievalConflictGuard("org-1")
    conflicts = guard._check_rag_rag([
        {"id": "chunk-1", "score": 0.95, "quote": "权威标准A"},
        {"id": "chunk-2", "score": 0.40, "quote": "低分片段B"},
    ])
    assert len(conflicts) == 1
    assert conflicts[0]["type"] == "rag_vs_rag"
    assert conflicts[0]["preferred_chunk_id"] == "chunk-1"
    assert conflicts[0]["downranked_chunk_id"] == "chunk-2"


def test_check_rag_rag_single_chunk_no_conflict():
    guard = RetrievalConflictGuard("org-1")
    conflicts = guard._check_rag_rag([
        {"id": "chunk-1", "score": 0.9},
    ])
    assert conflicts == []


def test_check_rag_rag_similar_scores_no_conflict():
    guard = RetrievalConflictGuard("org-1")
    conflicts = guard._check_rag_rag([
        {"id": "chunk-1", "score": 0.85},
        {"id": "chunk-2", "score": 0.80},
    ])
    assert conflicts == []


@pytest.mark.asyncio
async def test_guard_check_includes_rag_rag_conflicts():
    guard = RetrievalConflictGuard("org-1")
    result = await guard.check(
        query="标准查询",
        rag_hits=[
            {"id": "r1", "score": 0.95, "quote": "高权威标准"},
            {"id": "r2", "score": 0.30, "quote": "低分标准"},
        ],
        memory_hits=[],
    )
    assert any(c["type"] == "rag_vs_rag" for c in result["conflicts"])
