from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.adapters.pipeline_adapter import PipelineAgentAdapter, PipelineAgentResponse
from agent.router.contracts import AgentRouteDecision, AgentRouterOutput


@pytest.mark.asyncio
async def test_pipeline_adapter_builds_normalized_request_and_preserves_audit_metadata():
    captured: dict[str, object] = {}

    class FakeManager:
        async def run(self, request, db_session=None):
            captured["request"] = request
            captured["db_session"] = db_session
            return AgentRouterOutput(
                route_decision=AgentRouteDecision(
                    selected_agent="quality_analysis",
                    sub_route="rag_qa",
                    confidence=0.88,
                    reason="meeting knowledge query",
                    route_source="manager",
                ),
                agent_output={
                    "answer": "依据设备标准，A17 可以放行。",
                    "citations": [{"ref": "memory-1", "source_type": "standard", "source_id": "std-1"}],
                    "capabilities_used": ["evidence.arbitrate", "quality.final_analyze"],
                    "trace_id": "trace-1",
                    "route_trace": {
                        "reason": "meeting knowledge query",
                        "observations": [
                            {
                                "step_id": "s1",
                                "capability_key": "evidence.arbitrate",
                                "status": "success",
                                "summary": "证据已核验",
                                "artifact_ids": ["artifact-1"],
                            }
                        ],
                    },
                },
                status="completed",
            )

    events: list[dict] = []

    async def emit(event: dict):
        events.append(event)

    adapter = PipelineAgentAdapter(manager=FakeManager())
    result = await adapter.invoke(
        room_id="room-1",
        agent_def=SimpleNamespace(id="agent-1", name="知识 Agent", system_prompt="只回答设备标准"),
        query="A17 能否放行？",
        context_messages=[{"role": "user", "username": "alice", "content": "请核对 A17"}],
        emit=emit,
        runtime_model={
            "api_key": "must-not-leak",
            "model_id": "model-1",
            "provider": "local_openai",
            "base_url": "http://model",
        },
        request_context={
            "request_id": "req-1",
            "workflow_run_id": "wf-1",
            "assistant_message_id": "msg-1",
            "org_id": "org-1",
            "user_id": "user-1",
        },
        db_session="db-1",
    )

    assert isinstance(result, PipelineAgentResponse)
    assert str(result) == "依据设备标准，A17 可以放行。"
    assert result.metadata["adapter_type"] == "pipeline"
    assert result.metadata["selected_subgraph"] == "rag_qa"
    assert result.metadata["trust_protocol"]["protocol_version"] == "trust-answer-v1"
    assert result.metadata["citations"][0]["ref"] == "memory-1"
    assert captured["db_session"] == "db-1"
    request = captured["request"]
    assert request.request_id == "req-1"
    assert request.workflow_run_id == "wf-1"
    assert request.org_id == "org-1"
    assert request.ext["pipeline_agent_definition"]["system_prompt"] == "只回答设备标准"
    assert request.ext["history_messages"][0]["content"] == "请核对 A17"
    assert "api_key" not in repr(request)
    assert events[0]["event"] == "agent_pipeline_started"
    assert events[-1]["event"] == "message_delta"
    assert "".join(item["delta"] for item in events if item["event"] == "message_delta") == str(result)


@pytest.mark.asyncio
async def test_pipeline_adapter_converts_timeout_to_unavailable_trust_response():
    class TimeoutManager:
        async def run(self, request, db_session=None):
            raise TimeoutError("upstream timeout")

    adapter = PipelineAgentAdapter(manager=TimeoutManager())
    result = await adapter.invoke(
        room_id="room-1",
        agent_def=SimpleNamespace(name="知识 Agent"),
        query="请查询标准",
        context_messages=[],
        emit=lambda _event: None,
    )

    assert isinstance(result, PipelineAgentResponse)
    assert result.metadata["error"]["code"] == "PIPELINE_TIMEOUT"
    assert result.metadata["trust_protocol"]["status"] == "unavailable"
    assert result.metadata["trust_protocol"]["confidence"] == 0


@pytest.mark.asyncio
async def test_pipeline_adapter_reuses_meeting_participation_policy():
    adapter = PipelineAgentAdapter(manager=object())
    agent_def = SimpleNamespace(
        participation_strategy={
            "auto_reply": True,
            "cooldown_seconds": 10,
            "strategies": {"topic_match": {"enabled": True, "keywords": ["设备"]}},
        }
    )

    assert await adapter.should_participate(
        agent_def=agent_def,
        messages_since_last=1,
        seconds_since_last=11,
        recent_content="请关注设备 A17",
    )
    assert not await adapter.should_participate(
        agent_def=agent_def,
        messages_since_last=1,
        seconds_since_last=2,
        recent_content="请关注设备 A17",
    )
