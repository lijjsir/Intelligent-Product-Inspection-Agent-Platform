from __future__ import annotations

from datetime import datetime
from typing import Any

from agent.graph.state import InspectionState
from agent.llm.client import LLMClient


def _is_valid_conclusion_payload(data: object) -> bool:
    if not isinstance(data, dict):
        return False
    verdict = data.get("verdict")
    if not isinstance(verdict, str) or not verdict.strip():
        return False
    try:
        float(data.get("overall_score"))
    except (TypeError, ValueError):
        return False
    reasoning_chain = data.get("reasoning_chain")
    return reasoning_chain is None or isinstance(reasoning_chain, dict)


async def run_reasoning(state: InspectionState) -> InspectionState:
    now = datetime.utcnow().isoformat()
    defects = state.get("defects") or []
    docs = state.get("knowledge_docs") or []
    prompt = {
        "task_id": state.get("task_id"),
        "defects": defects,
        "docs": [{"id": d.get("id"), "score": d.get("score"), "text": (d.get("text") or "")[:300]} for d in docs],
        "instruction": '输出 JSON: {"verdict":"pass|fail|uncertain","overall_score":0-1,"reasoning_chain":{...}}',
    }
    client = LLMClient(
        api_key=state.get("model_api_key"),
        base_url=state.get("model_base_url"),
        model_id=state.get("model_id"),
        trace_id=state.get("trace_id"),
        task_id=state.get("task_id"),
        org_id=state.get("org_id"),
        provider=state.get("model_provider"),
    )
    try:
        data = await client.chat(
            [{"role": "user", "content": str(prompt)}],
            temperature=0.1,
            observation_name="inspection.reasoning",
            observation_metadata={"stage": "reasoning", "doc_count": len(docs), "defect_count": len(defects)},
        )
        if not _is_valid_conclusion_payload(data):
            raise RuntimeError("reasoning model returned invalid structured payload")
        if isinstance(data, dict):
            meta = data.get("__meta__") or {}
            usage = meta.get("usage") if isinstance(meta, dict) else None
            if isinstance(usage, dict):
                state.setdefault("usage_events", []).append(
                    {
                        "stage": "reasoning",
                        "model_key": str(meta.get("model") or state.get("model_id") or client.model_id),
                        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                        "completion_tokens": int(usage.get("completion_tokens") or 0),
                        "total_tokens": int(usage.get("total_tokens") or 0),
                    }
                )
        verdict = str(data.get("verdict") or "uncertain")
        overall_score = float(data.get("overall_score") or 0.5)
        reasoning_chain = data.get("reasoning_chain") if isinstance(data.get("reasoning_chain"), dict) else {}
        conclusion = {
            "verdict": verdict,
            "overall_score": max(0.0, min(overall_score, 1.0)),
            "reasoning_chain": reasoning_chain,
        }
    except Exception as exc:
        state.setdefault("runtime_errors", []).append(
            {
                "stage": "reasoning",
                "model_id": state.get("model_id"),
                "message": str(exc),
            }
        )
        state.setdefault("timeline", []).append(
            {"stage": "reasoning", "message": f"推理失败: {exc}", "ts": now}
        )
        return state

    state["reasoning_chain"] = conclusion.get("reasoning_chain") or {}
    state["conclusion"] = conclusion
    state.setdefault("timeline", []).append(
        {"stage": "reasoning", "message": f"推理完成，结论 {conclusion['verdict']}", "ts": now}
    )
    return state
