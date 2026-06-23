from __future__ import annotations

import pytest

from agent.router.errors import AgentRuntimeError
from agent.subgraphs.common.llm_runtime import run_llm_chat


@pytest.mark.asyncio
async def test_run_llm_chat_wraps_model_failure_as_model_call_failed(monkeypatch):
    class BrokenLLMClient:
        def __init__(self, **kwargs):
            self.trace_id = kwargs.get("trace_id")

        async def chat(self, **_kwargs):
            raise RuntimeError("model gateway down")

    monkeypatch.setattr("agent.subgraphs.common.llm_runtime.LLMClient", BrokenLLMClient)

    with pytest.raises(AgentRuntimeError) as exc_info:
        await run_llm_chat(
            state={"workflow_run_id": "wf-llm-1"},
            messages=[{"role": "user", "content": "hello"}],
            source="quality_analysis.llm_quality_reasoning",
        )

    assert exc_info.value.code == "MODEL_CALL_FAILED"
    assert exc_info.value.category == "model"
    assert exc_info.value.detail["source"] == "quality_analysis.llm_quality_reasoning"
    assert exc_info.value.debug["raw_error"] == "model gateway down"


@pytest.mark.asyncio
async def test_run_llm_chat_accepts_answer_shape(monkeypatch):
    class AnswerLLMClient:
        def __init__(self, **kwargs):
            self.trace_id = kwargs.get("trace_id")

        async def chat(self, **_kwargs):
            return {
                "answer": "final assessment text",
                "model": "quality-model",
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 7,
                    "total_tokens": 18,
                },
            }

    monkeypatch.setattr("agent.subgraphs.common.llm_runtime.LLMClient", AnswerLLMClient)

    content, meta = await run_llm_chat(
        state={"workflow_run_id": "wf-llm-2"},
        messages=[{"role": "user", "content": "inspect"}],
        source="quality_analysis.llm_quality_reasoning",
    )

    assert content == "final assessment text"
    assert meta["model"] == "quality-model"
    assert meta["usage"]["total_tokens"] == 18
