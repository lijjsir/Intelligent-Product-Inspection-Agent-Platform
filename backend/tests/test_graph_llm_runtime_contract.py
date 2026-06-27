from __future__ import annotations

import pytest

from agent.router.errors import AgentRuntimeError
from agent.subgraphs.common.llm_runtime import run_llm_chat
from agent.subgraphs.quality_analysis import QualityAnalysisGraph


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


@pytest.mark.asyncio
async def test_run_llm_chat_accepts_structured_response_and_nested_meta(monkeypatch):
    class StructuredLLMClient:
        def __init__(self, **kwargs):
            self.trace_id = kwargs.get("trace_id")

        async def chat(self, **_kwargs):
            return {
                "verdict": "manual_required",
                "defects": ["surface scratch"],
                "__meta__": {
                    "model": "deepseek-v4-flash",
                    "usage": {
                        "prompt_tokens": 21,
                        "completion_tokens": 9,
                        "total_tokens": 30,
                    },
                },
            }

    monkeypatch.setattr("agent.subgraphs.common.llm_runtime.LLMClient", StructuredLLMClient)

    content, meta = await run_llm_chat(
        state={"workflow_run_id": "wf-llm-structured"},
        messages=[{"role": "user", "content": "inspect"}],
    )

    assert '"verdict": "manual_required"' in content
    assert meta["model"] == "deepseek-v4-flash"
    assert meta["usage"]["total_tokens"] == 30


@pytest.mark.asyncio
async def test_quality_analysis_graph_preserves_database_model_runtime(monkeypatch):
    captured: dict = {}

    class DatabaseModelClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.trace_id = kwargs.get("trace_id")

        async def chat(self, **_kwargs):
            return {
                "answer": "deepseek assessment",
                "model": "deepseek-v4-flash",
                "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            }

    monkeypatch.setattr("agent.subgraphs.common.llm_runtime.LLMClient", DatabaseModelClient)

    result = await QualityAnalysisGraph().run(
        {
            "org_id": "org-1",
            "workflow_run_id": "wf-quality-1",
            "surface": "chat",
            "query": "inspect",
            "capability": "quality.final_analyze",
            "request": {"ext": {}, "metadata": {}},
            "manager_state": {"artifacts": []},
            "manager_model_runtime": {
                "provider": "deepseek",
                "model_id": "deepseek-v4-flash",
                "base_url": "https://api.deepseek.com",
                "api_key": "sk-database",
            },
            "model_runtime": {
                "provider": "deepseek",
                "model_id": "deepseek-v4-flash",
                "base_url": "https://api.deepseek.com",
                "api_key": "sk-database",
            },
        }
    )

    assert result["answer"] == "deepseek assessment"
    assert result["status"] == "success"
    assert result["llm_meta"]["model"] == "deepseek-v4-flash"
    assert result["llm_meta"]["usage"]["total_tokens"] == 8
    assert captured["provider"] == "deepseek"
    assert captured["model_id"] == "deepseek-v4-flash"
    assert captured["api_key"] == "sk-database"
