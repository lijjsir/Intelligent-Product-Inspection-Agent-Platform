from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from agent.contracts.quality_contracts import NormalizedAttachment, NormalizedRequest
from agent.router.manager_loop import ManagerLoop
from agent.router.manager_policy import ManagerPolicy
from agent.subgraphs.quality_analysis.nodes import build_final_assessment, context_assembler
from app.services.agent_local_memory_service import AgentLocalMemoryService
from app.services.agent_long_term_memory_service import AgentLongTermMemoryService
from app.services.memory_candidate_extractor import MemoryCandidateExtractor
from app.services.memory_vector_service import (
    CANDIDATE_MEMORY_COLLECTION,
    MEMORY_COLLECTION,
)
from app.services.task_blackboard_service import TaskBlackboardService


def _fallback_blackboard() -> TaskBlackboardService:
    return TaskBlackboardService(redis_url="redis://127.0.0.1:1/15")


class _MemoryRedis:
    def __init__(self):
        self.values = {}
        self.closed = False

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ex=None):
        self.values[key] = value
        return True

    async def delete(self, key):
        self.values.pop(key, None)
        return 1

    async def ping(self):
        return True

    async def aclose(self):
        self.closed = True


class _LoopAwareRedis(_MemoryRedis):
    instances: list["_LoopAwareRedis"] = []

    def __init__(self):
        super().__init__()
        self.loop = asyncio.get_running_loop()
        type(self).instances.append(self)

    async def ping(self):
        if asyncio.get_running_loop() is not self.loop:
            raise RuntimeError("Future attached to a different loop")
        return True


class _LocalVector:
    def __init__(self):
        self.upserts = []
        self.search_filter = None
        self.scroll_filter = None

    async def ensure_collection(self, vector_size=1536):
        self.vector_size = vector_size

    async def upsert_memory(self, **payload):
        self.upserts.append(payload)

    async def search(self, **payload):
        self.search_filter = payload["filter_conditions"]
        return list(self.search_results)

    async def scroll(self, **payload):
        self.scroll_filter = payload["filter_conditions"]
        return list(self.scroll_results)

    async def delete_memory(self, memory_id):
        self.deleted = memory_id

    search_results = []
    scroll_results = []


@pytest.mark.asyncio
async def test_blackboard_crud_latest_artifact_and_cleanup():
    service = _fallback_blackboard()
    await service.init_blackboard("org-bb", "run-crud", "task-1", 60)
    await service.set_global_plan("org-bb", "run-crud", {"plan_id": "plan-1"})
    await service.update_global_state(
        "org-bb",
        "run-crud",
        {"status": "running", "current_step_id": "s1"},
    )
    for artifact_id, source_count in (("a1", 1), ("a2", 2)):
        await service.append_artifact(
            "org-bb",
            "run-crud",
            {
                "artifact_id": artifact_id,
                "type": "evidence_packet",
                "content": {"source_count": source_count},
            },
        )
    await service.append_observation(
        "org-bb",
        "run-crud",
        {"step_id": "s1", "status": "success"},
    )

    snapshot = await service.snapshot("org-bb", "run-crud")
    latest = await service.get_latest_artifact("org-bb", "run-crud", "evidence_packet")

    assert snapshot["global_plan"]["plan_id"] == "plan-1"
    assert snapshot["global_state"]["current_step_id"] == "s1"
    assert len(snapshot["artifacts"]) == 2
    assert snapshot["observations"][0]["status"] == "success"
    assert latest["artifact_id"] == "a2"

    await service.cleanup("org-bb", "run-crud")
    assert await service.snapshot("org-bb", "run-crud") == {}


@pytest.mark.asyncio
async def test_blackboard_fallback_honors_ttl():
    service = _fallback_blackboard()
    await service.init_blackboard("org-bb", "run-ttl", None, 1)

    assert await service.snapshot("org-bb", "run-ttl")
    await asyncio.sleep(1.05)
    assert await service.snapshot("org-bb", "run-ttl") == {}


def test_blackboard_redis_client_is_rebuilt_across_event_loops(monkeypatch):
    from app.services import task_blackboard_service

    _LoopAwareRedis.instances = []
    task_blackboard_service._REDIS_RETRY_AFTER = 0.0
    service = TaskBlackboardService(redis_url="redis://example.invalid/0")
    monkeypatch.setattr(
        task_blackboard_service.Redis,
        "from_url",
        lambda *_args, **_kwargs: _LoopAwareRedis(),
    )

    async def use_blackboard(run_id: str):
        await service.init_blackboard("org-loop", run_id, None, 60)
        return await service.snapshot("org-loop", run_id)

    first = asyncio.run(use_blackboard("run-loop-1"))
    second = asyncio.run(use_blackboard("run-loop-2"))

    assert first["workflow_run_id"] == "run-loop-1"
    assert second["workflow_run_id"] == "run-loop-2"
    assert len(_LoopAwareRedis.instances) == 2
    assert _LoopAwareRedis.instances[0].closed is True


@pytest.mark.asyncio
async def test_orchestrator_commits_plan_observations_and_artifacts(monkeypatch):
    async def fake_call_model(self, state, request, prompt, **kwargs):
        return "blackboard answer"

    monkeypatch.setattr(
        "agent.router.executors.chat_executor.ChatExecutor._call_model",
        fake_call_model,
    )
    blackboard = _fallback_blackboard()
    request = NormalizedRequest(
        request_id="req-bb-loop",
        workflow_run_id="run-bb-loop",
        org_id="org-bb-loop",
        user_id="user-1",
        query="你好",
        ext={"surface": "chat"},
    )

    output = await ManagerLoop(blackboard=blackboard).run(request)
    snapshot = await blackboard.snapshot("org-bb-loop", "run-bb-loop")

    assert output.status == "completed"
    assert snapshot["global_plan"]["steps"][0]["owner_agent"] == "quality_analysis"
    assert (
        snapshot["global_plan"]["steps"][0]["expected_artifact"]
        == "quality_final_assessment"
    )
    assert snapshot["global_state"]["status"] == "completed"
    assert len(snapshot["observations"]) == 1
    assert {item["type"] for item in snapshot["artifacts"]} == {
        "quality_final_assessment",
        "composed_response",
    }
    assert all(item["workflow_run_id"] == "run-bb-loop" for item in snapshot["artifacts"])


@pytest.mark.asyncio
async def test_quality_task_plan_models_parallel_professional_branches():
    policy = ManagerPolicy()
    state = policy.initialize_state(
        NormalizedRequest(
            request_id="req-plan",
            workflow_run_id="run-plan",
            org_id="org-plan",
            user_id="user-1",
            query="执行正式质量检测",
            attachments=[
                NormalizedAttachment(
                    name="inspection.jpg",
                    kind="image",
                    url="https://example.invalid/inspection.jpg",
                )
            ],
            ext={
                "surface": "quality_task",
                "action_intent": "quality_inspection_execute",
                "lab_context": {"temperature": 25},
            },
        )
    )
    understanding = await policy.understand(state)
    plan = await policy.plan(state, understanding)
    by_capability = {step.capability: step for step in plan.steps}

    assert by_capability["vision.inspect"].depends_on == []
    assert by_capability["lab.early_risk.assess"].depends_on == []
    assert by_capability["vision.inspect"].parallel_group == "professional_assessment"
    assert (
        by_capability["lab.early_risk.assess"].parallel_group
        == "professional_assessment"
    )
    assert set(by_capability["quality.inspection.execute"].depends_on) == {
        "s1",
        "s2",
    }


@pytest.mark.asyncio
async def test_quality_context_merges_blackboard_and_records_consumed_ids():
    assembled = await context_assembler(
        {
            "manager_state": {
                "artifacts": [
                    {
                        "artifact_id": "visual-1",
                        "type": "visual_inspection_result",
                        "content": {"defects": ["scratch"]},
                    }
                ],
                "blackboard_snapshot": {
                    "artifacts": [
                        {
                            "artifact_id": "evidence-1",
                            "type": "evidence_packet",
                            "content": {"source_count": 2},
                        },
                        {
                            "artifact_id": "lab-1",
                            "type": "lab_detection_result",
                            "content": {"risk": "medium"},
                        },
                    ]
                },
            }
        }
    )
    assessment = await build_final_assessment(
        {
            **assembled,
            "response_mode": "inspection_execute",
            "answer": "建议人工复核边缘划痕。",
            "request": {
                "product_id": "line-a",
                "ext": {},
                "metadata": {},
            },
        }
    )

    final = assessment["final_assessment"]
    assert set(final["consumed_artifact_ids"]) == {"evidence-1", "visual-1", "lab-1"}
    assert final["candidate_extractable"] is True
    assert final["product_line"] == "line-a"


@pytest.mark.asyncio
async def test_candidate_extractor_filters_low_value_and_builds_valid_request():
    blackboard = _fallback_blackboard()
    await blackboard.init_blackboard("org-memory", "run-memory", "task-1", 60)
    await blackboard.update_global_state(
        "org-memory",
        "run-memory",
        {"product_line": "line-a"},
    )
    await blackboard.append_artifact(
        "org-memory",
        "run-memory",
        {
            "artifact_id": "quality-high",
            "type": "quality_final_assessment",
            "source_agent": "quality_analysis",
            "status": "success",
            "summary": "边缘毛刺模式需要提高关注权重。",
            "content": {
                "summary": "边缘毛刺模式需要提高关注权重。",
                "final_verdict": "manual_required",
            },
            "candidate_extractable": True,
        },
    )
    await blackboard.append_candidate_source(
        "org-memory",
        "run-memory",
        {
            "source_artifact_id": "quality-high",
            "source_agent": "quality_analysis",
            "candidate_type": "inspection_pattern",
            "share_value_score": 0.86,
            "target_agents": ["vision", "quality_analysis"],
            "evidence_artifact_ids": ["evidence-1", "visual-1"],
        },
    )
    await blackboard.append_artifact(
        "org-memory",
        "run-memory",
        {
            "artifact_id": "visual-low",
            "type": "visual_inspection_result",
            "source_agent": "vision",
            "status": "success",
            "summary": "单次低置信度 bbox",
            "content": {"summary": "单次低置信度 bbox"},
            "candidate_extractable": True,
        },
    )
    await blackboard.append_candidate_source(
        "org-memory",
        "run-memory",
        {
            "source_artifact_id": "visual-low",
            "source_agent": "vision",
            "share_value_score": 0.4,
        },
    )

    extractor = MemoryCandidateExtractor(
        None,
        blackboard=blackboard,
        user_id="user-1",
    )
    requests = await extractor.extract_from_blackboard(
        "org-memory",
        "run-memory",
        "task-1",
    )

    assert len(requests) == 1
    request = requests[0]
    assert request.scope.product_line == "line-a"
    assert request.source.agent_id == "quality_analysis"
    assert request.evidence_pointers["artifact_ids"] == [
        "evidence-1",
        "visual-1",
        "quality-high",
    ]
    memory_service = extractor._build_memory_service(request)
    assert memory_service._vector._collection == MEMORY_COLLECTION
    assert memory_service._candidate_vector._collection == CANDIDATE_MEMORY_COLLECTION


@pytest.mark.asyncio
async def test_agent_local_memory_is_private_and_orchestrator_injects_owner_context(
    monkeypatch,
):
    redis = _MemoryRedis()
    local_memory = AgentLocalMemoryService(redis_client=redis)
    await local_memory.append(
        org_id="org-local",
        agent_id="quality_analysis",
        workflow_run_id="run-local",
        item={
            "memory_id": "private-1",
            "summary": "仅质量分析 Agent 可见的私有经验",
            "shareable": False,
            "status": "active",
        },
    )
    seen_contexts = []

    async def fake_call_model(self, state, request, prompt, **kwargs):
        seen_contexts.append(list(state.agent_local_memory_context))
        return "基于真实输入生成的质量答复"

    monkeypatch.setattr(
        "agent.router.executors.chat_executor.ChatExecutor._call_model",
        fake_call_model,
    )
    request = NormalizedRequest(
        request_id="req-local",
        workflow_run_id="run-local",
        org_id="org-local",
        user_id="user-1",
        query="请分析",
        ext={"surface": "chat"},
    )

    output = await ManagerLoop(
        blackboard=_fallback_blackboard(),
        local_memory=local_memory,
    ).run(request)

    quality_items = await local_memory.snapshot(
        org_id="org-local",
        agent_id="quality_analysis",
        workflow_run_id="run-local",
    )
    vision_items = await local_memory.snapshot(
        org_id="org-local",
        agent_id="vision",
        workflow_run_id="run-local",
    )
    assert output.status == "completed"
    assert seen_contexts[0][0]["memory_id"] == "private-1"
    assert len(quality_items) >= 2
    assert vision_items == []


def test_agent_local_memory_redis_client_is_rebuilt_across_event_loops(monkeypatch):
    from app.services import agent_local_memory_service

    _LoopAwareRedis.instances = []
    service = AgentLocalMemoryService()
    monkeypatch.setattr(
        agent_local_memory_service.Redis,
        "from_url",
        lambda *_args, **_kwargs: _LoopAwareRedis(),
    )

    async def write_and_read(run_id: str):
        await service.append(
            org_id="org-loop",
            agent_id="quality_analysis",
            workflow_run_id=run_id,
            item={"run": run_id},
        )
        return await service.snapshot(
            org_id="org-loop",
            agent_id="quality_analysis",
            workflow_run_id=run_id,
        )

    first = asyncio.run(write_and_read("run-memory-1"))
    second = asyncio.run(write_and_read("run-memory-2"))

    assert first == [{"run": "run-memory-1"}]
    assert second == [{"run": "run-memory-2"}]
    assert len(_LoopAwareRedis.instances) == 2
    assert _LoopAwareRedis.instances[0].closed is True


@pytest.mark.asyncio
async def test_candidate_extractor_only_accepts_explicit_shareable_local_memory():
    local_memory = AgentLocalMemoryService(redis_client=_MemoryRedis())
    common = {
        "product_line": "line-a",
        "share_value_score": 0.82,
        "status": "active",
        "target_agents": ["quality_analysis"],
    }
    await local_memory.append(
        org_id="org-local-candidate",
        agent_id="vision",
        workflow_run_id="run-local-candidate",
        item={
            **common,
            "memory_id": "private",
            "summary": "私有经验不能进入共享候选",
            "shareable": False,
        },
    )
    await local_memory.append(
        org_id="org-local-candidate",
        agent_id="vision",
        workflow_run_id="run-local-candidate",
        item={
            **common,
            "memory_id": "shareable",
            "summary": "边缘区域需要提高视觉检查权重",
            "shareable": True,
            "share_reason": "can_improve_other_agents",
        },
    )

    requests = await MemoryCandidateExtractor(
        None,
        local_memory_service=local_memory,
    ).extract_from_local_memory(
        "org-local-candidate",
        "run-local-candidate",
        ["vision"],
    )

    assert len(requests) == 1
    assert requests[0].content.summary == "边缘区域需要提高视觉检查权重"
    assert requests[0].evidence_pointers["local_memory_id"] == "shareable"


@pytest.mark.asyncio
async def test_candidate_extractor_blocks_raw_artifacts_and_sensitive_content():
    blackboard = _fallback_blackboard()
    await blackboard.init_blackboard("org-filter", "run-filter", "task-filter", 60)
    await blackboard.update_global_state(
        "org-filter",
        "run-filter",
        {"product_line": "line-a"},
    )
    for artifact_id, artifact_type, summary, extra_content in (
        ("raw-1", "raw_image", "原始图像内容", {}),
        ("secret-1", "quality_final_assessment", "api_key=secret-value", {}),
        (
            "conflict-1",
            "quality_final_assessment",
            "与现有共享记忆存在未解决冲突",
            {"conflicts": ["active memory says the opposite"]},
        ),
    ):
        await blackboard.append_artifact(
            "org-filter",
            "run-filter",
            {
                "artifact_id": artifact_id,
                "type": artifact_type,
                "source_agent": "quality_analysis",
                "status": "success",
                "summary": summary,
                "content": {"summary": summary, **extra_content},
                "candidate_extractable": True,
            },
        )
        await blackboard.append_candidate_source(
            "org-filter",
            "run-filter",
            {
                "source_artifact_id": artifact_id,
                "source_agent": "quality_analysis",
                "candidate_type": "inspection_pattern",
                "share_value_score": 0.9,
            },
        )

    requests = await MemoryCandidateExtractor(
        None,
        blackboard=blackboard,
    ).extract_from_blackboard("org-filter", "run-filter", "task-filter")

    assert requests == []


@pytest.mark.asyncio
async def test_long_term_local_memory_enforces_org_agent_status_and_expiry_filters():
    vector = _LocalVector()
    now = datetime.now(timezone.utc)
    vector.search_results = [
        {
            "memory_id": "active-1",
            "payload": {
                "memory_id": "active-1",
                "summary": "有效经验",
                "expires_at": (now + timedelta(days=1)).isoformat(),
            },
        },
        {
            "memory_id": "expired-1",
            "payload": {
                "memory_id": "expired-1",
                "summary": "已过期经验",
                "expires_at": (now - timedelta(days=1)).isoformat(),
            },
        },
    ]
    vector.scroll_results = [
        {
            "memory_id": "shareable-1",
            "payload": {
                "memory_id": "shareable-1",
                "summary": "可共享经验",
                "shareable": True,
                "expires_at": (now + timedelta(days=1)).isoformat(),
            },
        }
    ]
    service = AgentLongTermMemoryService(
        org_id="org-long",
        user_id="user-1",
        vector_service=vector,
    )

    written = await service.write(
        agent_id="vision",
        summary="边缘区域容易出现毛刺",
        product_line="line-a",
        task_type="visual_inspection",
        shareable=True,
        share_reason="can_improve_other_agents",
        target_agents=["quality_analysis"],
        share_value_score=0.84,
        vector=[0.1, 0.2],
    )
    found = await service.search(
        agent_id="vision",
        query="毛刺",
        product_line="line-a",
        vector=[0.1, 0.2],
    )
    shareable = await service.list_shareable(agent_id="vision")

    assert written["memory_type"] == "agent_experience"
    assert vector.upserts[0]["extra_payload"]["agent_id"] == "vision"
    assert len(found) == 1
    assert found[0]["memory_id"] == "active-1"
    assert shareable[0]["memory_id"] == "shareable-1"
    required_filters = vector.search_filter["must"]
    assert {"key": "org_id", "match": {"value": "org-long"}} in required_filters
    assert {"key": "agent_id", "match": {"value": "vision"}} in required_filters
    assert {"key": "status", "match": {"value": "active"}} in required_filters
    assert {
        "key": "shareable",
        "match": {"value": True},
    } in vector.scroll_filter["must"]
