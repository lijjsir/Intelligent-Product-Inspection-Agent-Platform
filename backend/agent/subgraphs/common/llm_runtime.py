from __future__ import annotations

from typing import Any

from agent.llm.client import LLMClient
from agent.router.errors import make_agent_error


def _extract_content(response: Any) -> str:
    if isinstance(response, str):
        return response
    if not isinstance(response, dict):
        return str(response or "")
    if response.get("content"):
        return str(response["content"])
    for key in ("answer", "text"):
        if response.get(key):
            return str(response[key])
    choices = response.get("choices") or []
    if choices:
        message = (choices[0] or {}).get("message") or {}
        content = message.get("content")
        if content:
            return str(content)
    return ""


async def run_llm_chat(
    *,
    state: dict[str, Any],
    messages: list[dict[str, Any]],
    temperature: float = 0.2,
    observation_name: str = "graph.llm",
    source: str = "graph.llm",
) -> tuple[str, dict[str, Any]]:
    runtime = state.get("manager_model_runtime") or state.get("model_runtime") or {}
    trace_id = state.get("trace_id") or state.get("workflow_run_id")

    client = LLMClient(
        api_key=runtime.get("api_key"),
        base_url=runtime.get("base_url"),
        model_id=runtime.get("model_id"),
        provider=runtime.get("provider"),
        trace_id=trace_id,
        org_id=state.get("org_id"),
        input_price_per_million=runtime.get("input_price_per_million"),
        output_price_per_million=runtime.get("output_price_per_million"),
    )

    try:
        response = await client.chat(
            messages=messages,
            temperature=temperature,
            observation_name=observation_name,
            observation_metadata={
                "request_id": state.get("request_id"),
                "workflow_run_id": state.get("workflow_run_id"),
                "source": source,
            },
        )
    except Exception as exc:
        raise make_agent_error(
            "MODEL_CALL_FAILED",
            message="图节点模型调用失败。",
            detail={"source": source},
            debug={"raw_error": str(exc), "error_type": exc.__class__.__name__},
            source=source,
            cause=exc,
        ) from exc

    content = _extract_content(response)
    meta = {
        "model": response.get("model") if isinstance(response, dict) else runtime.get("model_id"),
        "usage": response.get("usage") if isinstance(response, dict) else None,
        "trace_id": client.trace_id,
    }
    return content, meta
